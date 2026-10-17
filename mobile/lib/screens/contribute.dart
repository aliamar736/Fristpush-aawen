import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../api.dart';
import '../auth.dart';
import '../l10n.dart';
import '../theme.dart';
import '../widgets.dart';
import 'login.dart';

/// ساهم: needs of approved initiatives. A pledge is not a payment; payment is confirmed only by the provider
/// (or by an accountant matching a bank transfer). Real collection stays disabled until configured & authorised.
class ContributeTab extends StatelessWidget {
  const ContributeTab({super.key});

  Future<void> _pledge(BuildContext context, Map ini, Map need) async {
    if (!await LoginScreen.ensure(context)) return;
    if (!context.mounted) return;
    final amount = TextEditingController();
    final ok = await showDialog<bool>(context: context, builder: (ctx) => AlertDialog(
      title: Text('${tr(context, 'ساهم في', 'Contribute to')} ${ini['title']}'),
      content: Column(mainAxisSize: MainAxisSize.min, children: [
        Text((AuthState.instance.config?['payments']?['message'] ?? '') as String, style: const TextStyle(color: Brand.yellowInk)),
        TextField(controller: amount, keyboardType: TextInputType.number, decoration: InputDecoration(labelText: tr(context, 'المبلغ (د.ل)', 'Amount (LYD)'))),
      ]),
      actions: [FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(tr(context, 'سجّل التعهد', 'Pledge')))],
    ));
    if (ok != true) return;
    final key = const Uuid().v4();
    try {
      await Api.instance.post('/pledges/', {'initiative': ini['id'], 'need': need['id'], 'amount': amount.text, 'method': 'bank_transfer', 'client_id': key}, key);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(tr(context,
            'سُجّل تعهدك. ارفع إيصال التحويل من الموقع؛ يُحتسب بعد مطابقة المحاسب.', 'Pledge recorded; upload the transfer receipt later.'))));
      }
    } catch (e) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
    }
  }

  @override
  Widget build(BuildContext context) => Loader(path: '/initiatives/?page_size=100', builder: (context, d, _) {
        final inis = ((d as Map)['results'] as List).where((i) => ['approved', 'active'].contains(i['status'])).toList();
        final needs = [for (final i in inis) for (final n in i['needs'] as List) if (n['status'] != 'met') (i as Map, n as Map)];
        if (needs.isEmpty) return EmptyView(icon: Icons.savings_outlined, title: tr(context, 'لا احتياجات مفتوحة', 'No open needs'));
        return ListView(padding: const EdgeInsets.all(12), children: [
          Text(tr(context, 'كل مساهمة مربوطة بمبادرة معتمدة واحتياج محدد. لا تحويلات بين الأفراد.', 'Every contribution goes to an approved initiative.'),
              style: const TextStyle(color: Brand.muted)),
          for (final (i, n) in needs) Card(child: ListTile(
            title: Text(n['title'] as String),
            subtitle: Text('${n['kind_label']} — ${i['title']}'),
            trailing: n['kind'] == 'funding'
                ? FilledButton(onPressed: () => _pledge(context, i, n), child: Text(tr(context, 'ساهم', 'Give')))
                : OutlinedButton(onPressed: () async {
                    final offer = tr(context, 'أقدر أوفر هذا', 'I can provide this'), sent = tr(context, 'وصل عرضك', 'Offer sent');
                    if (!await LoginScreen.ensure(context)) return;
                    await Api.instance.post('/needs/${n['id']}/offer/', {'message': offer});
                    if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(sent)));
                  }, child: Text(tr(context, 'عندي', 'I have it'))),
          )),
        ]);
      });
}
