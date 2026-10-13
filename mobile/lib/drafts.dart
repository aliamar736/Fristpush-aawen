import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:uuid/uuid.dart';

import 'api.dart';

/// A report draft stored on the device. Photos are compressed copies in the app's documents dir.
/// The `clientId` is sent with every attempt, so retries after a lost connection never duplicate.
class Draft {
  Draft({
    required this.clientId,
    this.status = 'draft',
    this.category,
    this.description = '',
    this.lat,
    this.lng,
    this.locationEdited = false,
    this.landmarkText = '',
    DateTime? observedAt,
    this.dangerLevel = 1,
    List<String>? photos,
    this.audio,
    List<String>? uploaded,
    this.error,
    this.reportId,
    this.trackingNumber,
    DateTime? updatedAt,
  })  : observedAt = observedAt ?? DateTime.now(),
        photos = photos ?? [],
        uploaded = uploaded ?? [],
        updatedAt = updatedAt ?? DateTime.now();

  factory Draft.create() => Draft(clientId: const Uuid().v4());

  final String clientId;
  String status; // draft | queued | sending | failed | sent
  int? category;
  String description;
  double? lat;
  double? lng;
  bool locationEdited;
  String landmarkText;
  DateTime observedAt;
  int dangerLevel;
  List<String> photos; // local file paths
  String? audio;
  List<String> uploaded; // server media uids already uploaded (in order photos..., audio)
  String? error;
  int? reportId;
  String? trackingNumber;
  DateTime updatedAt;

  Map<String, dynamic> toJson() => {
        'clientId': clientId, 'status': status, 'category': category, 'description': description, 'lat': lat,
        'lng': lng, 'locationEdited': locationEdited, 'landmarkText': landmarkText,
        'observedAt': observedAt.toIso8601String(), 'dangerLevel': dangerLevel, 'photos': photos, 'audio': audio,
        'uploaded': uploaded, 'error': error, 'reportId': reportId, 'trackingNumber': trackingNumber,
        'updatedAt': updatedAt.toIso8601String(),
      };

  factory Draft.fromJson(Map<String, dynamic> j) => Draft(
        clientId: j['clientId'] as String,
        status: j['status'] as String? ?? 'draft',
        category: j['category'] as int?,
        description: j['description'] as String? ?? '',
        lat: (j['lat'] as num?)?.toDouble(),
        lng: (j['lng'] as num?)?.toDouble(),
        locationEdited: j['locationEdited'] as bool? ?? false,
        landmarkText: j['landmarkText'] as String? ?? '',
        observedAt: DateTime.parse(j['observedAt'] as String),
        dangerLevel: j['dangerLevel'] as int? ?? 1,
        photos: (j['photos'] as List?)?.cast<String>(),
        audio: j['audio'] as String?,
        uploaded: (j['uploaded'] as List?)?.cast<String>(),
        error: j['error'] as String?,
        reportId: j['reportId'] as int?,
        trackingNumber: j['trackingNumber'] as String?,
        updatedAt: DateTime.tryParse(j['updatedAt'] as String? ?? ''),
      );
}

class DraftStore {
  DraftStore._();
  static final DraftStore instance = DraftStore._();
  Directory? _dir;

  Future<Directory> dir() async {
    if (_dir != null) return _dir!;
    final base = await getApplicationDocumentsDirectory();
    _dir = Directory('${base.path}/drafts');
    await _dir!.create(recursive: true);
    return _dir!;
  }

  Future<void> save(Draft d) async {
    d.updatedAt = DateTime.now();
    final f = File('${(await dir()).path}/${d.clientId}.json');
    await f.writeAsString(jsonEncode(d.toJson()));
  }

  Future<List<Draft>> list() async {
    final files = (await dir()).listSync().whereType<File>().where((f) => f.path.endsWith('.json'));
    final out = <Draft>[];
    for (final f in files) {
      try {
        out.add(Draft.fromJson(jsonDecode(await f.readAsString()) as Map<String, dynamic>));
      } catch (_) {/* skip corrupt */}
    }
    out.sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    return out;
  }

  Future<void> delete(Draft d) async {
    final f = File('${(await dir()).path}/${d.clientId}.json');
    if (await f.exists()) await f.delete();
    for (final p in [...d.photos, if (d.audio != null) d.audio!]) {
      final pf = File(p);
      if (await pf.exists()) await pf.delete();
    }
  }

  /// Sends one draft. Network failures leave it queued; validation errors mark it failed.
  Future<Draft> send(Draft d, {Api? api}) async {
    final client = api ?? Api.instance;
    d.status = 'sending';
    d.error = null;
    await save(d);
    try {
      final files = [...d.photos.map((p) => (p, 'image')), if (d.audio != null) (d.audio!, 'audio')];
      for (var i = d.uploaded.length; i < files.length; i++) {
        final (path, kind) = files[i];
        d.uploaded = [...d.uploaded, await client.uploadMedia(File(path), kind)];
        await save(d); // remember progress → never re-upload after reconnecting
      }
      final r = await client.post('/reports/', {
        'client_id': d.clientId, 'category': d.category, 'description': d.description, 'lat': d.lat, 'lng': d.lng,
        'location_edited': d.locationEdited, 'landmark_text': d.landmarkText,
        'observed_at': d.observedAt.toUtc().toIso8601String(), 'danger_level': d.dangerLevel, 'media': d.uploaded,
      }, d.clientId) as Map<String, dynamic>;
      d.status = 'sent';
      d.reportId = r['id'] as int;
      d.trackingNumber = r['tracking_number'] as String?;
    } on OfflineException {
      d.status = 'queued';
      d.error = 'بانتظار الاتصال';
    } on ApiException catch (e) {
      if (e.status >= 500 || e.status == 429) {
        d.status = 'queued';
        d.error = e.message;
      } else {
        d.status = 'failed';
        d.error = e.message;
      }
    }
    await save(d);
    return d;
  }

  bool _flushing = false;
  Future<int> flush() async {
    if (_flushing) return 0;
    _flushing = true;
    var sent = 0;
    try {
      for (final d in await list()) {
        if (d.status == 'queued' || d.status == 'sending') {
          final out = await send(d);
          if (out.status == 'sent') {
            sent++;
          } else if (out.status == 'queued') {
            break;
          }
        }
      }
    } finally {
      _flushing = false;
    }
    return sent;
  }
}
