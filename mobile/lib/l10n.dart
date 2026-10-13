import 'package:flutter/widgets.dart';

/// Arabic is the source language. `tr(context, 'عربي', 'English')` picks by the active locale.
String tr(BuildContext context, String ar, [String? en]) {
  final lang = Localizations.maybeLocaleOf(context)?.languageCode ?? 'ar';
  return lang == 'en' && en != null ? en : ar;
}

const statusLabels = <String, List<String>>{
  'draft': ['مسودة', 'Draft'],
  'submitted': ['مقدّم', 'Submitted'],
  'under_review': ['تحت المراجعة', 'Under review'],
  'needs_info': ['يحتاج معلومات', 'Needs info'],
  'verified': ['موثّق', 'Verified'],
  'referred': ['محال للجهة', 'Referred'],
  'acknowledged': ['استلام مؤكد', 'Acknowledged'],
  'in_progress': ['قيد التنفيذ', 'In progress'],
  'waiting_resource': ['بانتظار مورد أو تصريح', 'Waiting for resource/permit'],
  'done_pending_verification': ['إنجاز بانتظار التحقق', 'Done, awaiting verification'],
  'resolved': ['محلول', 'Resolved'],
  'disputed': ['معترض عليه', 'Disputed'],
  'reopened': ['معاد فتحه', 'Reopened'],
  'unresolvable': ['تعذّر الحل', 'Could not be resolved'],
};

String statusLabel(BuildContext context, String s) {
  final l = statusLabels[s];
  return l == null ? s : tr(context, l[0], l[1]);
}
