import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:intl/intl.dart';

import 'api.dart';
import 'l10n.dart';
import 'theme.dart';

class BrandLogo extends StatelessWidget {
  const BrandLogo({super.key, this.height = 36});
  final double height;
  @override
  Widget build(BuildContext context) =>
      SvgPicture.asset('assets/brand/aawen-lockup.svg', height: height, semanticsLabel: 'عاون — مع بعض نعاونوا');
}

Color _tone(String s) => switch (s) {
      'resolved' => Brand.ok,
      'disputed' || 'reopened' || 'unresolvable' => Brand.danger,
      'needs_info' || 'waiting_resource' || 'done_pending_verification' => Brand.yellowInk,
      'verified' || 'referred' || 'acknowledged' || 'in_progress' => Brand.tealInk,
      _ => Brand.petrol,
    };

class StatusChip extends StatelessWidget {
  const StatusChip(this.status, {super.key, this.label});
  final String status;
  final String? label;
  @override
  Widget build(BuildContext context) {
    final c = _tone(status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
      decoration: BoxDecoration(color: c.withValues(alpha: .12), borderRadius: BorderRadius.circular(99)),
      child: Text(label ?? statusLabel(context, status), style: TextStyle(color: c, fontWeight: FontWeight.w600, fontSize: 12)),
    );
  }
}

class DemoChip extends StatelessWidget {
  const DemoChip({super.key, required this.show});
  final bool show;
  @override
  Widget build(BuildContext context) => show
      ? Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 1),
          decoration: BoxDecoration(color: Brand.yellow, borderRadius: BorderRadius.circular(99)),
          child: Text(tr(context, 'تجريبي', 'Demo'), style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Brand.petrol)),
        )
      : const SizedBox.shrink();
}

/// The report journey: past steps on a teal line, the current step marked with the brand's yellow dot.
class StatusPath extends StatelessWidget {
  const StatusPath({super.key, required this.events, required this.status});
  final List events;
  final String status;
  static const happy = ['submitted', 'under_review', 'verified', 'referred', 'acknowledged', 'in_progress', 'done_pending_verification', 'resolved'];

  @override
  Widget build(BuildContext context) {
    final steps = events.where((e) => (e as Map)['kind'] == 'status').toList();
    final idx = happy.indexOf(status);
    final future = idx >= 0 ? happy.sublist(idx + 1) : <String>[];
    final fmt = DateFormat.yMMMd(Localizations.localeOf(context).languageCode).add_jm();
    final rows = <Widget>[];
    for (var i = 0; i < steps.length; i++) {
      final e = steps[i] as Map;
      final now = i == steps.length - 1;
      rows.add(_row(context, statusLabel(context, e['to_status'] as String),
          '${e['actor']} — ${fmt.format(DateTime.parse(e['at'] as String).toLocal())}', now ? 'now' : 'past', e['note'] as String?));
    }
    for (final s in future) {
      rows.add(_row(context, statusLabel(context, s), null, 'future', null));
    }
    return Semantics(label: tr(context, 'مسار البلاغ', 'Report journey'), child: Column(children: rows));
  }

  Widget _row(BuildContext context, String title, String? sub, String kind, String? note) {
    final dot = switch (kind) {
      'now' => Container(width: 18, height: 18, decoration: BoxDecoration(color: Brand.yellow, shape: BoxShape.circle, border: Border.all(color: Brand.petrol, width: 3))),
      'past' => Container(width: 14, height: 14, decoration: BoxDecoration(color: Colors.white, shape: BoxShape.circle, border: Border.all(color: Brand.teal, width: 3))),
      _ => Container(width: 14, height: 14, decoration: BoxDecoration(color: Colors.white, shape: BoxShape.circle, border: Border.all(color: Brand.line, width: 3))),
    };
    return IntrinsicHeight(
      child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        SizedBox(width: 24, child: Column(children: [dot, Expanded(child: Container(width: 3, color: kind == 'future' ? Brand.line : Brand.teal))])),
        const SizedBox(width: 10),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(bottom: 16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: TextStyle(fontWeight: kind == 'now' ? FontWeight.w700 : FontWeight.w600, color: kind == 'future' ? Brand.muted : Brand.petrol)),
              if (sub != null) Text(sub, style: const TextStyle(fontSize: 12, color: Brand.muted)),
              if (note != null && note.isNotEmpty) Text(note, style: const TextStyle(fontSize: 13)),
            ]),
          ),
        ),
      ]),
    );
  }
}

class EmptyView extends StatelessWidget {
  const EmptyView({super.key, required this.icon, required this.title, this.body, this.action});
  final IconData icon;
  final String title;
  final String? body;
  final Widget? action;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.all(32),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 52, color: Brand.tealInk),
          const SizedBox(height: 8),
          Text(title, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700), textAlign: TextAlign.center),
          if (body != null) Text(body!, style: const TextStyle(color: Brand.muted), textAlign: TextAlign.center),
          if (action != null) Padding(padding: const EdgeInsets.only(top: 12), child: action),
        ]),
      );
}

class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.error, this.onRetry});
  final Object error;
  final VoidCallback? onRetry;
  @override
  Widget build(BuildContext context) {
    final offline = error is OfflineException;
    final forbidden = error is ApiException && (error as ApiException).status == 403;
    return EmptyView(
      icon: offline ? Icons.wifi_off : forbidden ? Icons.lock_outline : Icons.error_outline,
      title: offline ? tr(context, 'لا يوجد اتصال', 'You are offline') : forbidden ? tr(context, 'ليس لديك صلاحية', 'No access') : tr(context, 'تعذر التحميل', "Couldn't load"),
      body: offline ? tr(context, 'لا توجد نسخة محفوظة من هذه الصفحة على جهازك.', 'No saved copy on this device.') : error.toString(),
      action: onRetry == null ? null : OutlinedButton(onPressed: onRetry, child: Text(tr(context, 'حاول مرة أخرى', 'Try again'))),
    );
  }
}

class StaleBanner extends StatelessWidget {
  const StaleBanner({super.key, required this.savedAt});
  final DateTime savedAt;
  @override
  Widget build(BuildContext context) {
    final mins = DateTime.now().difference(savedAt).inMinutes;
    final age = mins < 60 ? tr(context, '$mins دقيقة', '$mins min') : tr(context, '${mins ~/ 60} ساعة', '${mins ~/ 60} h');
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      color: Brand.yellowWash,
      child: Text(tr(context, 'نسخة محفوظة على جهازك منذ $age — قد لا تكون محدّثة.', 'Saved copy from $age ago — may be out of date.'),
          style: const TextStyle(color: Brand.yellowInk)),
    );
  }
}

/// FutureBuilder wrapper with loading / error / stale states.
class Loader extends StatefulWidget {
  const Loader({super.key, required this.path, required this.builder});
  final String path;
  final Widget Function(BuildContext context, dynamic data, VoidCallback reload) builder;
  @override
  State<Loader> createState() => _LoaderState();
}

class _LoaderState extends State<Loader> {
  late Future<Cached<dynamic>> _f;
  @override
  void initState() {
    super.initState();
    _f = Api.instance.getCached(widget.path);
  }

  void _reload() => setState(() => _f = Api.instance.getCached(widget.path));

  @override
  Widget build(BuildContext context) => FutureBuilder<Cached<dynamic>>(
        future: _f,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return Semantics(label: tr(context, 'جارٍ التحميل', 'Loading'), child: const Center(child: Padding(padding: EdgeInsets.all(24), child: CircularProgressIndicator())));
          }
          if (snap.hasError) return ErrorView(error: snap.error!, onRetry: _reload);
          final c = snap.data!;
          return Column(children: [if (c.stale) StaleBanner(savedAt: c.savedAt), Expanded(child: widget.builder(context, c.data, _reload))]);
        },
      );
}
