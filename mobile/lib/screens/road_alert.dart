import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import 'package:uuid/uuid.dart';

import '../api.dart';
import '../l10n.dart';
import '../theme.dart';
import '../widgets.dart';
import 'login.dart';
import 'map.dart';

class RoadAlertNew extends StatefulWidget {
  const RoadAlertNew({super.key});
  @override
  State<RoadAlertNew> createState() => _RoadAlertNewState();
}

class _RoadAlertNewState extends State<RoadAlertNew> {
  String type = 'accident';
  LatLng? pos;
  final desc = TextEditingController();
  final clientId = const Uuid().v4();
  bool busy = false;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(tr(context, 'تنبيه طريق', 'Road alert'))),
        body: ListView(padding: const EdgeInsets.all(16), children: [
          Container(color: const Color(0xFFFBE5E2), padding: const EdgeInsets.all(10),
              child: Text(tr(context, 'هذا ليس طلب نجدة. إذا كان هناك خطر على الحياة اتصل بخدمات الطوارئ الرسمية مباشرة.',
                  'This is not an emergency call. If life is at risk, call official emergency services.'), style: const TextStyle(color: Brand.danger))),
          const SizedBox(height: 8),
          Wrap(spacing: 6, children: [for (final (k, a, e) in [('accident', 'حادث', 'Accident'), ('closure', 'إغلاق', 'Closure'), ('obstacle', 'عائق', 'Obstacle'), ('congestion', 'ازدحام مبلّغ عنه', 'Reported congestion')])
            ChoiceChip(label: Text(tr(context, a, e)), selected: type == k, onSelected: (_) => setState(() => type = k))]),
          const SizedBox(height: 8),
          SizedBox(height: 260, child: FlutterMap(options: MapOptions(initialCenter: pos ?? tripoli, initialZoom: 14, onTap: (_, p) => setState(() => pos = p)), children: [
            TileLayer(urlTemplate: tileUrl, userAgentPackageName: 'ly.aawen.app'),
            if (pos != null) MarkerLayer(markers: [Marker(point: pos!, child: const Icon(Icons.warning_rounded, color: Brand.danger, size: 36))]),
          ])),
          TextButton.icon(onPressed: () async {
            if (await Geolocator.requestPermission() == LocationPermission.denied) return;
            final p = await Geolocator.getCurrentPosition();
            setState(() => pos = LatLng(p.latitude, p.longitude));
          }, icon: const Icon(Icons.my_location), label: Text(tr(context, 'موقعي الحالي', 'My location'))),
          TextField(controller: desc, decoration: InputDecoration(labelText: tr(context, 'تفاصيل قصيرة (اختياري)', 'Details (optional)'))),
          const SizedBox(height: 12),
          FilledButton(onPressed: pos == null || busy ? null : () async {
            if (!await LoginScreen.ensure(context)) return;
            setState(() => busy = true);
            try {
              final r = await Api.instance.post('/road-alerts/', {'type': type, 'lat': pos!.latitude, 'lng': pos!.longitude,
                'description': desc.text, 'observed_at': DateTime.now().toUtc().toIso8601String(), 'client_id': clientId}, clientId) as Map;
              if (mounted) Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => RoadAlertDetail(id: r['id'] as int)));
            } catch (e) {
              if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
              setState(() => busy = false);
            }
          }, child: Text(tr(context, 'انشر التنبيه', 'Post alert'))),
        ]),
      );
}

class RoadAlertDetail extends StatefulWidget {
  const RoadAlertDetail({super.key, required this.id});
  final int id;
  @override
  State<RoadAlertDetail> createState() => _RoadAlertDetailState();
}

class _RoadAlertDetailState extends State<RoadAlertDetail> {
  Key k = UniqueKey();
  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(tr(context, 'الطريق توّا', 'Road now'))),
        body: Loader(key: k, path: '/road-alerts/${widget.id}/', builder: (context, data, _) {
          final a = data as Map<String, dynamic>;
          Future<void> vote(String v) async {
            if (!await LoginScreen.ensure(context)) return;
            try {
              await Api.instance.post('/road-alerts/${widget.id}/vote/', {'vote': v});
              setState(() => k = UniqueKey());
            } catch (e) {
              if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
            }
          }
          return ListView(padding: const EdgeInsets.all(16), children: [
            Text(a['type_label'] as String, style: Theme.of(context).textTheme.headlineSmall),
            Wrap(spacing: 6, children: [StatusChip(a['is_live'] == true ? 'in_progress' : 'submitted', label: a['is_live'] == true ? tr(context, 'قائم الآن', 'Live') : a['status_label'] as String),
              StatusChip('waiting_resource', label: a['verification_label'] as String), DemoChip(show: a['is_demo'] == true)]),
            ListTile(title: Text(tr(context, 'المصدر', 'Source')), subtitle: Text(a['source_label'] as String)),
            ListTile(title: Text(tr(context, 'آخر تأكيد', 'Last confirmed')), subtitle: Text(tr(context, 'قبل ${a['minutes_since_confirmed']} دقيقة', '${a['minutes_since_confirmed']} min ago'))),
            Text(tr(context, 'لا نعرض سرعات أو مدد رحلات أو طرقًا بديلة محسوبة.', "We don't show speeds, travel times or computed detours."), style: const TextStyle(color: Brand.muted, fontSize: 12)),
            if (a['is_live'] == true) Wrap(spacing: 8, children: [
              FilledButton(onPressed: () => vote('still_there'), child: Text(tr(context, 'ما زال موجود', 'Still there'))),
              OutlinedButton(onPressed: () => vote('cleared'), child: Text(tr(context, 'الطريق فتح', 'Road is open'))),
            ]),
          ]);
        }),
      );
}
