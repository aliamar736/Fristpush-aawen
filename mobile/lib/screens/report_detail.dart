import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../api.dart';
import '../l10n.dart';
import '../theme.dart';
import '../widgets.dart';
import 'login.dart';

class ReportDetail extends StatefulWidget {
  const ReportDetail({super.key, required this.id});
  final int id;
  @override
  State<ReportDetail> createState() => _ReportDetailState();
}

class _ReportDetailState extends State<ReportDetail> {
  Key _k = UniqueKey();

  Future<void> _act(Future<void> Function() fn, String ok) async {
    try {
      await fn();
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(ok)));
      setState(() => _k = UniqueKey());
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
    }
  }

  Future<String?> _ask(String title, {bool photo = false}) async {
    final c = TextEditingController();
    File? img;
    final ok = await showDialog<bool>(context: context, builder: (ctx) => StatefulBuilder(builder: (ctx, set) => AlertDialog(
      title: Text(title),
      content: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: c, maxLines: 3),
        if (photo) TextButton.icon(onPressed: () async {
          final x = await ImagePicker().pickImage(source: ImageSource.camera, imageQuality: 75, maxWidth: 1600);
          if (x != null) set(() => img = File(x.path));
        }, icon: const Icon(Icons.photo_camera), label: Text(img == null ? tr(context, 'أرفق صورة حديثة', 'Attach a recent photo') : '✓')),
      ]),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx, true), child: Text(tr(context, 'أرسل', 'Send')))],
    )));
    if (ok != true) return null;
    if (photo) {
      if (img == null) return null;
      _photoUid = await Api.instance.uploadMedia(img!, 'image');
    }
    return c.text;
  }

  String? _photoUid;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(tr(context, 'تفاصيل البلاغ', 'Report'))),
        body: Loader(key: _k, path: '/reports/${widget.id}/', builder: (context, data, reload) {
          final r = data as Map<String, dynamic>;
          final viewer = (r['viewer'] as Map?) ?? {};
          final status = r['status'] as String;
          return ListView(padding: const EdgeInsets.all(16), children: [
            Row(children: [Expanded(child: Text(r['category']['name'] as String, style: Theme.of(context).textTheme.headlineSmall)),
              DemoChip(show: r['is_demo'] == true)]),
            Row(children: [StatusChip(status), const SizedBox(width: 8), Text('${r['tracking_number'] ?? ''}', textDirection: TextDirection.ltr)]),
            const SizedBox(height: 12),
            if (status == 'referred' && r['referral']?['acknowledged_at'] == null)
              Container(color: Brand.tealWash, padding: const EdgeInsets.all(10), child: Text(tr(context,
                  'أُحيل إلى ${r['referral']['agency']}. لم تؤكد الجهة الاستلام بعد — البلاغ يبقى مفتوحًا.', 'Referred; not yet acknowledged.'))),
            Card(child: Padding(padding: const EdgeInsets.all(12), child: Text((r['description'] as String?) ??
                tr(context, 'يظهر الوصف بعد مراجعته وحجب البيانات الشخصية.', 'Description shown after review.')))),
            for (final m in (r['media'] as List).where((m) => m['kind'] == 'image'))
              Padding(padding: const EdgeInsets.only(bottom: 8), child: Image.network('${apiBase.replaceAll('/api/v1', '')}${m['url']}', height: 200, fit: BoxFit.cover,
                  semanticLabel: tr(context, 'صورة البلاغ', 'Report photo'))),
            Text(tr(context, 'مسار المعالجة', 'Progress'), style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            StatusPath(events: (r['events'] as List?) ?? [], status: status),
            const Divider(),
            if (viewer['is_owner'] != true && ['submitted', 'under_review', 'verified', 'referred', 'acknowledged', 'in_progress', 'reopened'].contains(status) && viewer['confirmed'] != true)
              FilledButton(onPressed: () async { final ok = tr(context, 'سُجّل تأكيدك', 'Confirmed'); if (await LoginScreen.ensure(context)) _act(() => Api.instance.post('/reports/${widget.id}/confirm/'), ok); },
                  child: Text(tr(context, 'المشكلة موجودة، أؤكدها', 'I see it too'))),
            if (status == 'done_pending_verification' && viewer['is_executor'] != true && viewer['checked'] != true)
              Wrap(spacing: 8, children: [
                FilledButton(onPressed: () async { final ok = tr(context, 'شكرًا', 'Thanks'); if (await LoginScreen.ensure(context)) _act(() => Api.instance.post('/reports/${widget.id}/check/', {'verdict': 'fixed'}), ok); },
                    child: Text(tr(context, 'تأكدت: اتصلحت', 'Verified fixed'))),
                OutlinedButton(onPressed: () async { final ok = tr(context, 'شكرًا', 'Thanks'); if (await LoginScreen.ensure(context)) _act(() => Api.instance.post('/reports/${widget.id}/check/', {'verdict': 'not_fixed'}), ok); },
                    child: Text(tr(context, 'لم تُصلح', 'Not fixed'))),
              ]),
            if (status == 'resolved') Wrap(spacing: 8, children: [
              OutlinedButton(onPressed: () async {
                final q = tr(context, 'لماذا تعترض؟', 'Why do you object?'), ok = tr(context, 'وصل اعتراضك', 'Objection sent');
                if (!await LoginScreen.ensure(context) || !mounted) return;
                final reason = await _ask(q);
                if (reason != null && reason.isNotEmpty) _act(() => Api.instance.post('/reports/${widget.id}/object/', {'reason': reason}), ok);
              }, child: Text(tr(context, 'أعترض على الإغلاق', 'Object'))),
              OutlinedButton(onPressed: () async {
                final q = tr(context, 'ماذا رجع؟ (صورة حديثة مطلوبة)', 'What came back? (photo required)'), ok = tr(context, 'أعيد فتح البلاغ', 'Reopened');
                if (!await LoginScreen.ensure(context) || !mounted) return;
                final note = await _ask(q, photo: true);
                if (note != null && _photoUid != null) {
                  _act(() => Api.instance.post('/reports/${widget.id}/recurrence/', {'note': note, 'media': [_photoUid]}), ok);
                }
              }, child: Text(tr(context, 'المشكلة رجعت', 'It came back'))),
            ]),
          ]);
        }),
      );
}
