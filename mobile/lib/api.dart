import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// Base URL of the AAWEN API. Override at build time:
///   flutter run --dart-define=AAWEN_API=https://api.aawen.ly/api/v1
const apiBase = String.fromEnvironment('AAWEN_API', defaultValue: 'http://10.0.2.2:8000/api/v1');

class ApiException implements Exception {
  ApiException(this.status, this.code, this.message, [this.fields]);
  final int status;
  final String code;
  final String message;
  final Map<String, dynamic>? fields;
  @override
  String toString() => message;
}

class OfflineException implements Exception {
  @override
  String toString() => 'لا يوجد اتصال بالإنترنت.';
}

class Cached<T> {
  Cached(this.data, this.savedAt, this.stale);
  final T data;
  final DateTime savedAt;
  final bool stale;
}

/// JWT client with silent refresh; tokens live in the platform secure storage (Keychain / Keystore).
class Api {
  Api._();
  static final Api instance = Api._();
  final _storage = const FlutterSecureStorage();
  String? _access;
  String? _refresh;
  Future<bool>? _refreshing;
  String lang = 'ar';

  Future<void> loadTokens() async {
    _access = await _storage.read(key: 'access');
    _refresh = await _storage.read(key: 'refresh');
  }

  bool get signedIn => _refresh != null;

  Future<void> setTokens(String? access, String? refresh) async {
    _access = access;
    _refresh = refresh;
    if (access == null) {
      await _storage.deleteAll();
    } else {
      await _storage.write(key: 'access', value: access);
      await _storage.write(key: 'refresh', value: refresh);
    }
  }

  Map<String, String> _headers({bool json = true, String? idempotencyKey}) => {
        'Accept': 'application/json',
        'Accept-Language': lang,
        if (json) 'Content-Type': 'application/json',
        if (_access != null) 'Authorization': 'Bearer $_access',
        if (idempotencyKey != null) 'Idempotency-Key': idempotencyKey,
      };

  Future<bool> _doRefresh() {
    return _refreshing ??= () async {
      try {
        final r = await http.post(Uri.parse('$apiBase/auth/refresh'),
            headers: {'Content-Type': 'application/json'}, body: jsonEncode({'refresh': _refresh}));
        if (r.statusCode != 200) {
          await setTokens(null, null);
          return false;
        }
        final d = jsonDecode(r.body) as Map<String, dynamic>;
        await setTokens(d['access'] as String, (d['refresh'] ?? _refresh) as String);
        return true;
      } catch (_) {
        return false;
      } finally {
        _refreshing = null;
      }
    }();
  }

  Future<dynamic> request(String method, String path, {Object? body, String? idempotencyKey}) async {
    Future<http.Response> send() {
      final uri = Uri.parse('$apiBase$path');
      final h = _headers(idempotencyKey: idempotencyKey);
      final b = body == null ? null : jsonEncode(body);
      switch (method) {
        case 'GET':
          return http.get(uri, headers: h).timeout(const Duration(seconds: 20));
        case 'POST':
          return http.post(uri, headers: h, body: b ?? '{}').timeout(const Duration(seconds: 30));
        case 'PATCH':
          return http.patch(uri, headers: h, body: b).timeout(const Duration(seconds: 30));
        case 'PUT':
          return http.put(uri, headers: h, body: b).timeout(const Duration(seconds: 30));
        default:
          return http.delete(uri, headers: h, body: b).timeout(const Duration(seconds: 30));
      }
    }

    http.Response res;
    try {
      res = await send();
      if (res.statusCode == 401 && _refresh != null && await _doRefresh()) res = await send();
    } on SocketException {
      throw OfflineException();
    } on TimeoutException {
      throw OfflineException();
    } on http.ClientException {
      throw OfflineException();
    }
    return _decode(res);
  }

  dynamic _decode(http.Response res) {
    if (res.statusCode == 204) return null;
    final data = res.body.isEmpty ? null : jsonDecode(utf8.decode(res.bodyBytes));
    if (res.statusCode >= 400) {
      final err = (data is Map ? data['error'] : null) as Map<String, dynamic>?;
      throw ApiException(res.statusCode, (err?['code'] ?? '${res.statusCode}') as String,
          (err?['message'] ?? (res.statusCode >= 500 ? 'حدث خطأ في الخادم. حاول بعد قليل.' : 'تعذر تنفيذ الطلب.')) as String,
          err?['fields'] as Map<String, dynamic>?);
    }
    return data;
  }

  Future<dynamic> get(String p) => request('GET', p);
  Future<dynamic> post(String p, [Object? b, String? key]) => request('POST', p, body: b ?? {}, idempotencyKey: key);

  /// GET with offline fallback — returns the last saved copy and its age when there is no connection.
  Future<Cached<dynamic>> getCached(String path) async {
    final prefs = await SharedPreferences.getInstance();
    try {
      final data = await get(path);
      await prefs.setString('cache:$path', jsonEncode({'t': DateTime.now().toIso8601String(), 'd': data}));
      return Cached(data, DateTime.now(), false);
    } on OfflineException {
      final raw = prefs.getString('cache:$path');
      if (raw == null) rethrow;
      final m = jsonDecode(raw) as Map<String, dynamic>;
      return Cached(m['d'], DateTime.parse(m['t'] as String), true);
    }
  }

  Future<String> uploadMedia(File file, String kind, {String contentType = 'image/jpeg'}) async {
    final req = http.MultipartRequest('POST', Uri.parse('$apiBase/media/'))
      ..headers.addAll(_headers(json: false))
      ..fields['kind'] = kind
      ..files.add(await http.MultipartFile.fromPath('file', file.path));
    try {
      var streamed = await req.send().timeout(const Duration(seconds: 60));
      var res = await http.Response.fromStream(streamed);
      if (res.statusCode == 401 && await _doRefresh()) {
        final retry = http.MultipartRequest('POST', req.url)
          ..headers.addAll(_headers(json: false))
          ..fields.addAll(req.fields)
          ..files.add(await http.MultipartFile.fromPath('file', file.path));
        res = await http.Response.fromStream(await retry.send());
      }
      return (_decode(res) as Map<String, dynamic>)['uid'] as String;
    } on SocketException {
      throw OfflineException();
    } on TimeoutException {
      throw OfflineException();
    }
  }
}
