import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';

class AuthState extends ChangeNotifier {
  AuthState._();
  static final AuthState instance = AuthState._();
  Map<String, dynamic>? me;
  Map<String, dynamic>? config;
  Locale locale = const Locale('ar');

  bool get signedIn => me != null;
  bool hasRole(List<String> roles) =>
      ((me?['roles'] as List?) ?? []).any((r) => roles.contains((r as Map)['role']) && r['active'] == true);

  Future<void> refresh() async {
    final prefs = await SharedPreferences.getInstance();
    locale = Locale(prefs.getString('lang') ?? 'ar');
    Api.instance.lang = locale.languageCode;
    try {
      config = await Api.instance.get('/config') as Map<String, dynamic>;
    } catch (_) {}
    if (Api.instance.signedIn) {
      try {
        me = await Api.instance.get('/me') as Map<String, dynamic>;
      } on ApiException {
        me = null;
      } on OfflineException {
        // keep the session while offline
      }
    }
    notifyListeners();
  }

  Future<void> setLocale(String code) async {
    locale = Locale(code);
    Api.instance.lang = code;
    (await SharedPreferences.getInstance()).setString('lang', code);
    notifyListeners();
  }

  Future<void> signIn(String access, String refresh) async {
    await Api.instance.setTokens(access, refresh);
    await this.refresh();
  }

  Future<void> signOut() async {
    try {
      await Api.instance.post('/auth/logout', {});
    } catch (_) {}
    await Api.instance.setTokens(null, null);
    me = null;
    notifyListeners();
  }
}
