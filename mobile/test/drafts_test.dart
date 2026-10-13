import 'package:aawen/drafts.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('draft survives JSON round-trip with its client id and upload progress', () {
    final d = Draft.create()
      ..category = 3
      ..lat = 32.88
      ..lng = 13.19
      ..photos = ['/tmp/a.jpg']
      ..uploaded = ['u1']
      ..status = 'queued';
    final back = Draft.fromJson(d.toJson());
    expect(back.clientId, d.clientId);
    expect(back.uploaded, ['u1']);
    expect(back.status, 'queued');
    expect(back.observedAt, d.observedAt);
  });
}
