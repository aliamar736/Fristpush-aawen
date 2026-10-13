import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../api.dart';
import '../l10n.dart';
import '../theme.dart';
import '../widgets.dart';
import 'login.dart';

/// عاون: initiatives (with «شن ناقص؟»), take a task, goodwill store, care points.
class AawenTab extends StatelessWidget {
  const AawenTab({super.key});
  @override
  Widget build(BuildContext context) => DefaultTabController(
        length: 4,
        child: Column(children: [
          TabBar(isScrollable: true, tabs: [
            Tab(text: tr(context, 'المبادرات', 'Initiatives')), Tab(text: tr(context, 'خُذ مهمة', 'Take a task')),
            Tab(text: tr(context, 'مخزن الخير', 'Goodwill store')), Tab(text: tr(context, 'نقاط العناية', 'Care points')),
          ]),
          Expanded(child: TabBarView(children: [_Initiatives(), _Tasks(), _Store(), _Care()])),
        ]),
      );
}

Future<void> _act(BuildContext context, Future<void> Function() fn, String ok) async {
  if (!await LoginScreen.ensure(context)) return;
  try {
    await fn();
    if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(ok)));
  } catch (e) {
    if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
  }
}

class _Initiatives extends StatelessWidget {
  @override
  Widget build(BuildContext context) => Loader(path: '/initiatives/?page_size=50', builder: (context, d, _) {
        final list = (d as Map)['results'] as List;
        if (list.isEmpty) return EmptyView(icon: Icons.groups_outlined, title: tr(context, 'لا مبادرات بعد', 'No initiatives yet'));
        return ListView(padding: const EdgeInsets.all(12), children: [
          for (final i in list) Card(child: ExpansionTile(
            title: Row(children: [Expanded(child: Text(i['title'] as String)), DemoChip(show: i['is_demo'] == true)]),
            subtitle: Text(i['summary'] as String),
            children: [for (final n in i['needs'] as List) ListTile(
              leading: Icon(n['is_blocking'] == true ? Icons.warning_amber : Icons.inventory_2_outlined, color: n['is_blocking'] == true ? Brand.yellowInk : Brand.tealInk),
              title: Text(n['title'] as String),
              subtitle: Text('${n['kind_label']} — ${n['quantity_fulfilled']}/${n['quantity_needed']} ${n['unit']}'),
              trailing: n['status'] == 'met' || n['kind'] == 'funding' ? null : TextButton(
                onPressed: () => _act(context, () => Api.instance.post('/needs/${n['id']}/offer/', {'message': tr(context, 'أقدر أساعد في هذا', 'I can help')}),
                    tr(context, 'وصل عرضك لمسؤول المبادرة', 'Offer sent')),
                child: Text(tr(context, 'عندي هذا', 'I can help'))),
            )],
          )),
        ]);
      });
}

class _Tasks extends StatelessWidget {
  @override
  Widget build(BuildContext context) => Loader(path: '/tasks/?page_size=50', builder: (context, d, reload) {
        final list = (d as Map)['results'] as List;
        if (list.isEmpty) return EmptyView(icon: Icons.volunteer_activism_outlined, title: tr(context, 'لا مهام قادمة', 'No upcoming tasks'));
        return ListView(padding: const EdgeInsets.all(12), children: [
          for (final t in list) Card(child: ListTile(
            title: Text(t['title'] as String),
            subtitle: Text('${DateTime.parse(t['starts_at'] as String).toLocal().toString().substring(0, 16)} — ${t['booked']}/${t['capacity']} ${t['skill_name'] ?? ''}'),
            trailing: t['my_booking'] != null && t['my_booking']['status'] != 'cancelled'
                ? StatusChip('in_progress', label: tr(context, 'محجوزة', 'Booked'))
                : FilledButton(onPressed: (t['booked'] as int) >= (t['capacity'] as int) ? null : () async {
                    await _act(context, () => Api.instance.post('/tasks/${t['id']}/book/', {}, const Uuid().v4()), tr(context, 'حُجزت المهمة', 'Booked'));
                    reload();
                  }, child: Text(tr(context, 'خُذها', 'Take'))),
          )),
        ]);
      });
}

class _Store extends StatelessWidget {
  @override
  Widget build(BuildContext context) => Loader(path: '/resources/?page_size=100', builder: (context, d, reload) {
        final list = (d as Map)['results'] as List;
        if (list.isEmpty) return EmptyView(icon: Icons.store_outlined, title: tr(context, 'المخزن فاضي', 'Store is empty'));
        return ListView(padding: const EdgeInsets.all(12), children: [
          for (final r in list) Card(child: ListTile(
            title: Text(r['title'] as String),
            subtitle: Text('${r['kind_label']} — ${tr(context, 'متاح', 'available')} ${r['available_quantity']} / ${tr(context, 'محجوز', 'reserved')} ${r['reserved_quantity']}\n${r['pickup_location']}'),
            isThreeLine: true,
            trailing: FilledButton(onPressed: (r['available_quantity'] as int) < 1 ? null : () async {
              final key = const Uuid().v4();
              await _act(context, () => Api.instance.post('/resources/${r['id']}/reserve/', {'quantity': 1, 'client_id': key}, key), tr(context, 'تم الحجز', 'Reserved'));
              reload();
            }, child: Text(tr(context, 'احجز', 'Reserve'))),
          )),
        ]);
      });
}

class _Care extends StatelessWidget {
  @override
  Widget build(BuildContext context) => Loader(path: '/care-points/?page_size=100', builder: (context, d, _) {
        final list = (d as Map)['results'] as List;
        if (list.isEmpty) return EmptyView(icon: Icons.health_and_safety_outlined, title: tr(context, 'لا نقاط عناية موثقة بعد', 'No verified care points'));
        return ListView(children: [for (final c in list) ListTile(
          leading: const Icon(Icons.health_and_safety_outlined),
          title: Text('${c['name']} — ${c['host_type']}'),
          subtitle: Text('${(c['services'] as List).join('، ')}\n${c['hours']}'),
          isThreeLine: true,
        )]);
      });
}
