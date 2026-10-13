import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_image_compress/flutter_image_compress.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:image_picker/image_picker.dart';
import 'package:latlong2/latlong.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import '../api.dart';
import '../auth.dart';
import '../drafts.dart';
import '../l10n.dart';
import '../theme.dart';
import '../widgets.dart';
import 'login.dart';
import 'map.dart';
import 'report_detail.dart';

/// بلّغ: location → problem → time → nearby similar → send.
/// The draft is saved on the device at every step; sending offline queues it for automatic, idempotent retry.
class ReportWizard extends StatefulWidget {
  const ReportWizard({super.key, this.draft});
  final Draft? draft;
  @override
  State<ReportWizard> createState() => _ReportWizardState();
}

class _ReportWizardState extends State<ReportWizard> {
  late Draft d;
  int step = 0;
  List<Map<String, dynamic>> cats = [];
  List<Map<String, dynamic>>? similar;
  Map<String, dynamic>? aiHint;
  final _desc = TextEditingController();
  final _landmark = TextEditingController();
  final _rec = AudioRecorder();
  bool _recording = false, _sending = false;
  String? _err;

  @override
  void initState() {
    super.initState();
    d = widget.draft ?? Draft.create();
    _desc.text = d.description;
    _landmark.text = d.landmarkText;
    Api.instance.getCached('/categories/').then((c) => setState(() => cats = ((c.data as Map)['results'] as List).cast()));
  }

  Future<void> _save() => DraftStore.instance.save(d);

  Future<void> _locate() async {
    var perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) perm = await Geolocator.requestPermission();
    if (perm == LocationPermission.denied || perm == LocationPermission.deniedForever) {
      setState(() => _err = tr(context, 'لم نحصل على إذن الموقع. اضغط على الخريطة لتحديد المكان.', 'Location denied — tap the map.'));
      return;
    }
    final p = await Geolocator.getCurrentPosition(locationSettings: const LocationSettings(accuracy: LocationAccuracy.high));
    setState(() { d.lat = p.latitude; d.lng = p.longitude; d.locationEdited = false; });
    _save();
  }

  Future<void> _addPhoto(ImageSource src) async {
    final x = await ImagePicker().pickImage(source: src);
    if (x == null) return;
    final dir = await getApplicationDocumentsDirectory();
    final out = '${dir.path}/drafts/${d.clientId}-${d.photos.length}.jpg';
    // Compress before storing/uploading (weak connections). EXIF is dropped; the server strips metadata again.
    final res = await FlutterImageCompress.compressAndGetFile(x.path, out, quality: 75, minWidth: 1600, minHeight: 1600, keepExif: false);
    setState(() { d.photos = [...d.photos, res?.path ?? x.path]; d.uploaded = []; });
    _save();
  }

  Future<void> _toggleRecord() async {
    if (_recording) {
      final path = await _rec.stop();
      setState(() { _recording = false; d.audio = path; d.uploaded = []; });
      _save();
      return;
    }
    if (!await _rec.hasPermission()) {
      setState(() => _err = tr(context, 'لم نحصل على إذن الميكروفون. اكتب الوصف بدلًا من التسجيل.', 'Microphone denied — type instead.'));
      return;
    }
    final dir = await getApplicationDocumentsDirectory();
    await _rec.start(const RecordConfig(encoder: AudioEncoder.aacLc, bitRate: 48000), path: '${dir.path}/drafts/${d.clientId}.m4a');
    setState(() => _recording = true);
  }

  Future<void> _hint() async {
    if (_desc.text.trim().length < 6) return;
    try {
      aiHint = await Api.instance.post('/reports/suggest-category/', {'text': _desc.text}) as Map<String, dynamic>;
      setState(() {});
    } catch (_) {/* AI is optional */}
  }

  bool _validate() {
    _err = null;
    if (step == 0 && d.lat == null) _err = tr(context, 'حدد مكان المشكلة.', 'Choose the location.');
    if (step == 1 && d.category == null) _err = tr(context, 'اختر نوع المشكلة.', 'Choose a category.');
    if (step == 1 && d.description.trim().isEmpty && d.photos.isEmpty && d.audio == null) {
      _err = tr(context, 'اكتب وصفًا أو أرفق صورة أو تسجيلًا.', 'Add a description, photo or voice note.');
    }
    setState(() {});
    return _err == null;
  }

  Future<void> _next() async {
    d.description = _desc.text;
    d.landmarkText = _landmark.text;
    if (!_validate()) return;
    await _save();
    if (step == 2) {
      similar = null;
      try {
        similar = (((await Api.instance.get('/reports/similar/?lat=${d.lat}&lng=${d.lng}&category=${d.category}')) as Map)['results'] as List).cast();
      } catch (_) {
        similar = [];
      }
    }
    setState(() => step++);
  }

  Future<void> _confirmExisting(int id) async {
    if (!await LoginScreen.ensure(context)) return;
    try {
      await Api.instance.post('/reports/$id/confirm/');
      await DraftStore.instance.delete(d);
      if (mounted) Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => ReportDetail(id: id)));
    } catch (e) {
      setState(() => _err = e.toString());
    }
  }

  Future<void> _send() async {
    if (!await LoginScreen.ensure(context)) return;
    setState(() => _sending = true);
    d.status = 'queued';
    d = await DraftStore.instance.send(d);
    setState(() => _sending = false);
    if (d.status == 'sent' && mounted) {
      await DraftStore.instance.delete(d);
      if (mounted) Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => ReportDetail(id: d.reportId!)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final titles = [tr(context, 'المكان', 'Where'), tr(context, 'المشكلة', 'What'), tr(context, 'الوقت', 'When'),
      tr(context, 'بلاغات قريبة', 'Nearby'), tr(context, 'إرسال', 'Send')];
    final notice = AuthState.instance.config?['emergency_notice']?['ar'] as String?;
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'بلّغ عن مشكلة', 'Report a problem'))),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Container(padding: const EdgeInsets.all(10), color: Brand.yellowWash,
            child: Text(notice ?? 'بلاغ الخريطة لا يرسل إسعافًا.', style: const TextStyle(color: Brand.yellowInk))),
        const SizedBox(height: 12),
        Row(children: List.generate(5, (i) => Expanded(child: Container(margin: const EdgeInsets.symmetric(horizontal: 2), height: 6,
            decoration: BoxDecoration(borderRadius: BorderRadius.circular(3), color: i < step ? Brand.teal : i == step ? Brand.petrol : Brand.line))))),
        Padding(padding: const EdgeInsets.symmetric(vertical: 8),
            child: Semantics(header: true, child: Text('${step + 1}/5 — ${titles[step]}', style: Theme.of(context).textTheme.titleLarge))),
        if (_err != null) Text(_err!, style: const TextStyle(color: Brand.danger)),
        ..._stepBody(),
      ]),
      bottomNavigationBar: SafeArea(child: Padding(padding: const EdgeInsets.all(12), child: Row(children: [
        if (step > 0) OutlinedButton(onPressed: () => setState(() => step--), child: Text(tr(context, 'السابق', 'Back'))),
        const Spacer(),
        if (step < 4) FilledButton(onPressed: _next, child: Text(tr(context, 'التالي', 'Next')))
        else FilledButton(style: FilledButton.styleFrom(backgroundColor: Brand.teal, foregroundColor: Brand.petrol),
            onPressed: _sending ? null : _send, child: Text(tr(context, 'أرسل البلاغ', 'Send report'))),
      ]))),
    );
  }

  List<Widget> _stepBody() {
    switch (step) {
      case 0:
        return [
          Text(tr(context, 'اضغط على الخريطة لمكان المشكلة بالضبط.', 'Tap the map at the exact spot.')),
          const SizedBox(height: 8),
          SizedBox(height: 300, child: ClipRRect(borderRadius: BorderRadius.circular(16), child: FlutterMap(
            options: MapOptions(initialCenter: d.lat != null ? LatLng(d.lat!, d.lng!) : tripoli, initialZoom: d.lat != null ? 16 : 13,
                onTap: (_, p) { setState(() { d.lat = p.latitude; d.lng = p.longitude; d.locationEdited = true; }); _save(); }),
            children: [
              TileLayer(urlTemplate: tileUrl, userAgentPackageName: 'ly.aawen.app'),
              if (d.lat != null) MarkerLayer(markers: [Marker(point: LatLng(d.lat!, d.lng!), width: 40, height: 40,
                  child: const Icon(Icons.location_on, color: Brand.yellow, size: 40))]),
            ],
          ))),
          TextButton.icon(onPressed: _locate, icon: const Icon(Icons.my_location), label: Text(tr(context, 'استخدم موقعي الحالي', 'Use my location'))),
          TextField(controller: _landmark, decoration: InputDecoration(labelText: tr(context, 'معلم قريب', 'Nearby landmark'),
              hintText: tr(context, 'مثال: قدام مخبز النور', 'e.g. in front of the bakery'))),
        ];
      case 1:
        return [
          Wrap(spacing: 8, runSpacing: 8, children: [for (final c in cats)
            ChoiceChip(label: Text(c['name_ar'] as String), selected: d.category == c['id'], onSelected: (_) { setState(() => d.category = c['id'] as int); _save(); })]),
          const SizedBox(height: 12),
          TextField(controller: _desc, maxLines: 4, maxLength: 2000, onEditingComplete: _hint, onChanged: (_) => d.description = _desc.text,
              decoration: InputDecoration(labelText: tr(context, 'وصف المشكلة', 'Description'),
                  helperText: tr(context, 'لا تكتب أسماء أو أرقام هواتف أو لوحات سيارات.', 'No names, phone numbers or plates.'))),
          if (aiHint?['suggestion'] != null)
            ListTile(leading: const Icon(Icons.auto_awesome), title: Text(tr(context, 'اقتراح فئة', 'Suggested category')),
                trailing: TextButton(onPressed: () => setState(() => d.category = aiHint!['suggestion']['category_id'] as int), child: Text(tr(context, 'اختر', 'Use')))),
          if ((aiHint?['sensitive_flags'] as List?)?.isNotEmpty ?? false)
            Container(color: Brand.yellowWash, padding: const EdgeInsets.all(8), child: Text(tr(context, 'يبدو أن النص يحتوي بيانات شخصية؛ احذفها لحماية الخصوصية.', 'Please remove personal data.'))),
          Wrap(spacing: 8, children: [
            OutlinedButton.icon(onPressed: () => _addPhoto(ImageSource.camera), icon: const Icon(Icons.photo_camera), label: Text(tr(context, 'التقط صورة', 'Take photo'))),
            OutlinedButton.icon(onPressed: () => _addPhoto(ImageSource.gallery), icon: const Icon(Icons.photo), label: Text(tr(context, 'من المعرض', 'Gallery'))),
            OutlinedButton.icon(onPressed: _toggleRecord, icon: Icon(_recording ? Icons.stop : Icons.mic),
                label: Text(_recording ? tr(context, 'إيقاف', 'Stop') : tr(context, 'تسجيل صوتي', 'Voice note'))),
          ]),
          Text(tr(context, 'الصور تُراجع قبل نشرها. لا تصوّر الوجوه أو المصابين.', 'Photos are reviewed before publishing.'), style: const TextStyle(color: Brand.muted, fontSize: 12)),
          Wrap(spacing: 6, children: [for (final p in d.photos) Image.file(File(p), width: 80, height: 80, fit: BoxFit.cover,
              semanticLabel: tr(context, 'صورة مرفقة', 'Attached photo'))]),
          if (d.audio != null) Text(tr(context, 'تسجيل صوتي مرفق ✓', 'Voice note attached ✓')),
          const SizedBox(height: 8),
          Text(tr(context, 'هل تشكل خطرًا؟', 'Is it dangerous?')),
          Wrap(spacing: 6, children: [for (final (v, a, e) in [(0, 'لا خطر', 'None'), (1, 'إزعاج', 'Nuisance'), (2, 'خطر محتمل', 'Possible'), (3, 'خطر مباشر', 'Immediate')])
            ChoiceChip(label: Text(tr(context, a, e)), selected: d.dangerLevel == v, onSelected: (_) => setState(() => d.dangerLevel = v))]),
        ];
      case 2:
        return [
          Text(tr(context, 'متى شفت المشكلة؟ يُسجل وقت الرصد منفصلًا عن وقت الإرسال.', 'When did you see it?')),
          Wrap(spacing: 6, children: [
            ActionChip(label: Text(tr(context, 'الآن', 'Now')), onPressed: () => setState(() => d.observedAt = DateTime.now())),
            ActionChip(label: Text(tr(context, 'قبل ساعة', 'An hour ago')), onPressed: () => setState(() => d.observedAt = DateTime.now().subtract(const Duration(hours: 1)))),
            ActionChip(label: Text(tr(context, 'أمس', 'Yesterday')), onPressed: () => setState(() => d.observedAt = DateTime.now().subtract(const Duration(days: 1)))),
          ]),
          ListTile(title: Text(tr(context, 'وقت الرصد', 'Observed at')), subtitle: Text(d.observedAt.toLocal().toString().substring(0, 16)),
              trailing: const Icon(Icons.edit_calendar), onTap: () async {
                final day = await showDatePicker(context: context, initialDate: d.observedAt, firstDate: DateTime.now().subtract(const Duration(days: 90)), lastDate: DateTime.now());
                if (day == null || !mounted) return;
                final t = await showTimePicker(context: context, initialTime: TimeOfDay.fromDateTime(d.observedAt));
                final when = DateTime(day.year, day.month, day.day, t?.hour ?? 12, t?.minute ?? 0);
                setState(() => d.observedAt = when.isAfter(DateTime.now()) ? DateTime.now() : when);
              }),
        ];
      case 3:
        if (similar == null) return [const Center(child: CircularProgressIndicator())];
        if (similar!.isEmpty) return [Text(tr(context, 'لا توجد بلاغات مشابهة قريبة. بلاغك جديد.', 'No similar reports nearby.'))];
        return [
          Text(tr(context, 'إن كانت نفس المشكلة، أكدها بدل إرسال بلاغ جديد.', 'If it is the same problem, confirm it instead.')),
          for (final r in similar!) Card(child: ListTile(
            title: Row(children: [Flexible(child: Text(r['category']['name'] as String)), const SizedBox(width: 6), StatusChip(r['status'] as String)]),
            subtitle: Text('${(r['distance_m'] as num).round()} ${tr(context, 'متر', 'm')} — ${r['confirmations_count']} ${tr(context, 'تأكيد', 'confirmations')}'),
            trailing: TextButton(onPressed: () => _confirmExisting(r['id'] as int), child: Text(tr(context, 'أؤكدها', 'Confirm'))),
          )),
        ];
      default:
        return [
          ListTile(title: Text(tr(context, 'الفئة', 'Category')), subtitle: Text((cats.firstWhere((c) => c['id'] == d.category, orElse: () => {'name_ar': '—'})['name_ar']) as String)),
          ListTile(title: Text(tr(context, 'المرفقات', 'Attachments')), subtitle: Text('${d.photos.length} ${tr(context, 'صورة', 'photos')}${d.audio != null ? ' + 🎙' : ''}')),
          Text(tr(context, 'هويتك لا تظهر للعامة.', 'Your identity is never public.'), style: const TextStyle(color: Brand.muted)),
          if (d.status == 'queued') Container(color: Brand.yellowWash, padding: const EdgeInsets.all(8),
              child: Text(tr(context, 'محفوظ وبانتظار الاتصال — سيُرسل تلقائيًا دون تكرار.', 'Saved — will be sent automatically without duplicates.'))),
          if (d.status == 'failed') Text(d.error ?? '', style: const TextStyle(color: Brand.danger)),
        ];
    }
  }
}
