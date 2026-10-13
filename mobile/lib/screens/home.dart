import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api.dart';
import '../l10n.dart';
import '../theme.dart';
import '../widgets.dart';
import 'report_detail.dart';

class HomeTab extends StatefulWidget {
  const HomeTab({super.key});
  @override
  State<HomeTab> createState() => _HomeTabState();
}

class _HomeTabState extends State<HomeTab> {
  int? _area;
  List<Map<String, dynamic>> _areas = [];
  String? _msg;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    final prefs = await SharedPreferences.getInstance();
    try {
      final r = await Api.instance.getCached('/areas/?page_size=200');
      _areas = ((r.data as Map)['results'] as List).cast<Map<String, dynamic>>();
    } catch (_) {}
    setState(() => _area = prefs.getInt('area'));
  }

  Future<void> _setArea(int? id) async {
    final prefs = await SharedPreferences.getInstance();
    if (id == null) {
      await prefs.remove('area');
    } else {
      await prefs.setInt('area', id);
    }
    setState(() => _area = id);
  }

  /// One-off location only — the app never tracks location continuously.
  Future<void> _locate() async {
    setState(() => _msg = null);
    var perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) perm = await Geolocator.requestPermission();
    if (perm == LocationPermission.denied || perm == LocationPermission.deniedForever) {
      if (mounted) setState(() => _msg = tr(context, 'لم نحصل على إذن الموقع. اختر حومتك من القائمة.', 'Location denied — pick from the list.'));
      return;
    }
    final p = await Geolocator.getCurrentPosition(locationSettings: const LocationSettings(accuracy: LocationAccuracy.medium));
    final a = await Api.instance.get('/areas/locate/?lat=${p.latitude}&lng=${p.longitude}');
    if (a == null) {
      if (mounted) setState(() => _msg = tr(context, 'موقعك خارج المناطق المغطاة.', 'Outside covered areas.'));
    } else {
      await _setArea((a as Map)['id'] as int);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(padding: const EdgeInsets.all(16), children: [
      Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(color: Brand.petrol, borderRadius: BorderRadius.circular(16)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(tr(context, 'حومتي', 'My area'), style: const TextStyle(color: Brand.ivory)),
          Text(_areas.firstWhere((a) => a['id'] == _area, orElse: () => {'name_ar': tr(context, 'اختر حومتك', 'Choose your area')})['name_ar'] as String,
              style: const TextStyle(color: Brand.ivory, fontSize: 28, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          DropdownButtonFormField<int>(
            value: _area,
            decoration: InputDecoration(labelText: tr(context, 'المنطقة المتابعة', 'Followed area')),
            items: _areas.map((a) => DropdownMenuItem(value: a['id'] as int, child: Text(a['name_ar'] as String))).toList(),
            onChanged: _setArea,
          ),
          const SizedBox(height: 8),
          FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: Brand.teal, foregroundColor: Brand.petrol),
            onPressed: _locate, icon: const Icon(Icons.my_location), label: Text(tr(context, 'حدد حومتي', 'Use my location'))),
          if (_msg != null) Text(_msg!, style: const TextStyle(color: Brand.yellow)),
        ]),
      ),
      if (_area != null) SizedBox(height: 900, child: Loader(key: ValueKey(_area), path: '/areas/$_area/summary/', builder: (context, d, reload) => _Summary(d as Map<String, dynamic>)))
      else EmptyView(icon: Icons.place_outlined, title: tr(context, 'اختر الحومة اللي تهمك', 'Pick your area')),
    ]);
  }
}

class _Summary extends StatelessWidget {
  const _Summary(this.s);
  final Map<String, dynamic> s;
  @override
  Widget build(BuildContext context) {
    final rep = s['reports'] as Map;
    Widget stat(Object n, String l) => Expanded(child: Card(child: Padding(padding: const EdgeInsets.all(12), child: Column(children: [
          Text('$n', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)), Text(l, style: const TextStyle(color: Brand.muted, fontSize: 12))]))));
    return ListView(physics: const NeverScrollableScrollPhysics(), padding: const EdgeInsets.only(top: 12), children: [
      Row(children: [stat(rep['open'], tr(context, 'مفتوح', 'open')), stat(rep['resolved'], tr(context, 'اتحلّت', 'resolved')),
        stat((s['initiatives'] as List).length, tr(context, 'مبادرة', 'initiatives'))]),
      _section(context, tr(context, 'تنبيهات الجهات', 'Agency notices')),
      for (final a in s['announcements'] as List) ListTile(leading: const Icon(Icons.notifications_outlined), title: Text(a['title'] as String), subtitle: Text('${a['body']}\n${a['agency__name']}')),
      _section(context, tr(context, 'اتحلّت مؤخرًا', 'Recently fixed')),
      for (final r in s['recently_resolved'] as List)
        ListTile(leading: const Icon(Icons.check_circle_outline), title: Text(r['category'] as String), subtitle: Text(r['tracking_number'] as String),
            onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => ReportDetail(id: r['id'] as int)))),
      _section(context, tr(context, 'دليل الخدمات الموثّق', 'Verified services')),
      for (final d in s['services'] as List) ListTile(leading: const Icon(Icons.phone_outlined), title: Text('${d['name']} — ${d['service']}'), subtitle: Text('${d['phone']}  ${d['hours']}')),
    ]);
  }

  Widget _section(BuildContext context, String t) => Padding(padding: const EdgeInsets.only(top: 16, bottom: 4),
      child: Text(t, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)));
}
