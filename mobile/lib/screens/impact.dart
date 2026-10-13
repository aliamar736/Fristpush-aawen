import 'package:flutter/material.dart';

import '../api.dart';
import '../auth.dart';
import '../drafts.dart';
import '../l10n.dart';
import '../widgets.dart';
import 'login.dart';
import 'report_detail.dart';
import 'report_wizard.dart';

/// أثري: my reports, drafts on this device, notifications and account (sign-out, deletion request).
class ImpactTab extends StatelessWidget {
  const ImpactTab({super.key});
  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: AuthState.instance,
        builder: (context, _) {
          if (!AuthState.instance.signedIn) {
            return EmptyView(icon: Icons.person_outline, title: tr(context, 'سجّل الدخول لمتابعة أثرك', 'Sign in to see your impact'),
                action: FilledButton(onPressed: () => LoginScreen.ensure(context), child: Text(tr(context, 'تسجيل الدخول', 'Sign in'))));
          }
          return DefaultTabController(length: 4, child: Column(children: [
            TabBar(isScrollable: true, tabs: [Tab(text: tr(context, 'بلاغاتي', 'My reports')), Tab(text: tr(context, 'المسودات', 'Drafts')),
              Tab(text: tr(context, 'الإشعارات', 'Notifications')), Tab(text: tr(context, 'حسابي', 'Account'))]),
            Expanded(child: TabBarView(children: [_Mine(), _Drafts(), _Notifs(), _Account()])),
          ]));
        });
}

class _Mine extends StatelessWidget {
  @override
  Widget build(BuildContext context) => Loader(path: '/reports/mine/?page_size=100', builder: (context, d, _) {
        final list = (d as Map)['results'] as List;
        if (list.isEmpty) return EmptyView(icon: Icons.place_outlined, title: tr(context, 'لم تقدم بلاغات بعد', 'No reports yet'));
        return ListView(children: [for (final r in list) ListTile(
          title: Row(children: [Flexible(child: Text(r['category']['name'] as String)), const SizedBox(width: 6), StatusChip(r['status'] as String)]),
          subtitle: Text(r['tracking_number'] as String? ?? ''),
          onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => ReportDetail(id: r['id'] as int))),
        )]);
      });
}

class _Drafts extends StatefulWidget {
  @override
  State<_Drafts> createState() => _DraftsState();
}

class _DraftsState extends State<_Drafts> {
  @override
  Widget build(BuildContext context) => FutureBuilder<List<Draft>>(
        future: DraftStore.instance.list(),
        builder: (context, s) {
          final list = (s.data ?? []).where((d) => d.status != 'sent').toList();
          if (list.isEmpty) return EmptyView(icon: Icons.drafts_outlined, title: tr(context, 'لا مسودات على هذا الجهاز', 'No drafts'));
          return ListView(children: [for (final d in list) ListTile(
            title: Text(d.description.isEmpty ? tr(context, 'بلاغ بدون وصف', 'Untitled') : d.description),
            subtitle: Text({'draft': tr(context, 'مسودة', 'Draft'), 'queued': tr(context, 'بانتظار الاتصال', 'Waiting for connection'),
              'failed': d.error ?? '', 'sending': tr(context, 'جارٍ الإرسال', 'Sending')}[d.status] ?? d.status),
            onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => ReportWizard(draft: d))).then((_) => setState(() {})),
            trailing: IconButton(tooltip: tr(context, 'احذف', 'Delete'), icon: const Icon(Icons.delete_outline),
                onPressed: () async { await DraftStore.instance.delete(d); setState(() {}); }),
          )]);
        });
}

class _Notifs extends StatelessWidget {
  @override
  Widget build(BuildContext context) => Loader(path: '/notifications/?page_size=100', builder: (context, d, _) {
        final list = (d as Map)['results'] as List;
        if (list.isEmpty) return EmptyView(icon: Icons.notifications_none, title: tr(context, 'لا إشعارات', 'No notifications'));
        return ListView(children: [for (final n in list) ListTile(
          leading: Icon(n['read_at'] == null ? Icons.notifications_active : Icons.notifications_none),
          title: Text(n['title'] as String), subtitle: Text(n['body'] as String),
          onTap: n['data']?['report_id'] == null ? null : () => Navigator.push(context, MaterialPageRoute(builder: (_) => ReportDetail(id: n['data']['report_id'] as int))),
        )]);
      });
}

class _Account extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final me = AuthState.instance.me ?? {};
    return ListView(padding: const EdgeInsets.all(16), children: [
      ListTile(title: Text(tr(context, 'الهاتف', 'Phone')), subtitle: Text('${me['phone'] ?? ''}', textDirection: TextDirection.ltr)),
      ListTile(title: Text(tr(context, 'اللغة', 'Language')), trailing: TextButton(
          onPressed: () => AuthState.instance.setLocale(AuthState.instance.locale.languageCode == 'ar' ? 'en' : 'ar'),
          child: Text(AuthState.instance.locale.languageCode == 'ar' ? 'English' : 'العربية'))),
      OutlinedButton(onPressed: AuthState.instance.signOut, child: Text(tr(context, 'تسجيل الخروج', 'Sign out'))),
      const SizedBox(height: 24),
      Text(tr(context, 'حذف الحساب: تُزال بياناتك الشخصية بعد 7 أيام وتبقى البلاغات بلا هوية.', 'Account deletion: personal data removed after 7 days.')),
      TextButton(onPressed: () async {
        await Api.instance.post('/me/deletion');
        await AuthState.instance.refresh();
        if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(tr(context, 'سُجّل طلب الحذف', 'Deletion requested'))));
      }, child: Text(tr(context, 'اطلب حذف حسابي', 'Request account deletion'))),
    ]);
  }
}
