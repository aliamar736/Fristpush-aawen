"""Report state machine. The only place where Report.status changes.

Rules enforced here (server side):
- every transition has an explicit allowed-actor set, checked against role + area/agency scope;
- referral (إحالة) and agency acknowledgement (استلام) are separate steps;
- resolution needs executor proof AND an independent confirmation; conflicts go to a human reviewer;
- nothing closes a report because time passed or an agency did not answer (no 'system' actor can resolve);
- AI helpers never call this module.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Role
from apps.accounts.permissions import has_role
from apps.core.audit import audit
from apps.core.exceptions import InvalidTransition

from .models import (CompletionCheck, CompletionProof, Referral, Report, ReportEvent, Status)

S = Status
OWNER, REVIEWER, COORD, AGENCY, FIELD, PUBLIC = "owner", "reviewer", "coordinator", "agency", "field", "public"

# (from, to) -> actors allowed
TRANSITIONS = {
    (S.DRAFT, S.SUBMITTED): {OWNER},
    (S.SUBMITTED, S.UNDER_REVIEW): {REVIEWER, COORD},
    (S.UNDER_REVIEW, S.NEEDS_INFO): {REVIEWER, COORD},
    (S.NEEDS_INFO, S.UNDER_REVIEW): {OWNER, REVIEWER, COORD},
    (S.UNDER_REVIEW, S.VERIFIED): {REVIEWER, COORD},
    (S.VERIFIED, S.REFERRED): {REVIEWER, COORD},
    (S.REFERRED, S.ACKNOWLEDGED): {AGENCY, COORD},  # coordinator only to record an off-portal acknowledgement
    (S.ACKNOWLEDGED, S.IN_PROGRESS): {AGENCY, COORD, FIELD},
    (S.ACKNOWLEDGED, S.WAITING): {AGENCY, COORD},
    (S.IN_PROGRESS, S.WAITING): {AGENCY, COORD},
    (S.WAITING, S.IN_PROGRESS): {AGENCY, COORD, FIELD},
    (S.IN_PROGRESS, S.DONE_PENDING): {AGENCY, COORD, FIELD},
    (S.WAITING, S.DONE_PENDING): {AGENCY, COORD, FIELD},
    (S.DONE_PENDING, S.RESOLVED): {REVIEWER, COORD},
    (S.DONE_PENDING, S.IN_PROGRESS): {REVIEWER, COORD},
    (S.RESOLVED, S.DISPUTED): {OWNER, PUBLIC},
    (S.DISPUTED, S.RESOLVED): {REVIEWER, COORD},
    (S.DISPUTED, S.REOPENED): {REVIEWER, COORD},
    (S.RESOLVED, S.REOPENED): {OWNER, PUBLIC, REVIEWER, COORD},
    (S.REOPENED, S.UNDER_REVIEW): {REVIEWER, COORD},
    (S.REOPENED, S.REFERRED): {REVIEWER, COORD},
    (S.UNRESOLVABLE, S.REOPENED): {COORD},
}
for _src in S.ACTIVE:
    TRANSITIONS.setdefault((_src, S.UNRESOLVABLE), set()).add(COORD)

REASON_REQUIRED = {S.NEEDS_INFO, S.WAITING, S.UNRESOLVABLE, S.DISPUTED, S.REOPENED}


def allowed_targets(report):
    return sorted({to for (frm, to) in TRANSITIONS if frm == report.status})


def actor_kinds(user, report):
    kinds = set()
    if not user or not user.is_authenticated:
        return kinds
    kinds.add(PUBLIC)
    if report.reporter_id and report.reporter_id == user.pk:
        kinds.add(OWNER)
    if has_role(user, Role.REVIEWER, Role.COORDINATOR, area=report.area_id):
        kinds.add(REVIEWER)
    if has_role(user, Role.COORDINATOR, area=report.area_id):
        kinds.add(COORD)
    if report.agency_id and has_role(user, Role.AGENCY_STAFF, agency=report.agency_id):
        kinds.add(AGENCY)
    if report.field_assignee_id and report.field_assignee_id == user.pk:
        kinds.add(FIELD)
    return kinds


def available_actions(user, report):
    kinds = actor_kinds(user, report)
    return [to for (frm, to), who in TRANSITIONS.items() if frm == report.status and who & kinds]


def _primary_role(kinds):
    for k in (COORD, REVIEWER, AGENCY, FIELD, OWNER, PUBLIC):
        if k in kinds:
            return k
    return ""


@transaction.atomic
def transition(report, to, user, *, reason="", note="", data=None, agency=None, is_public=True):
    """Move `report` to status `to` on behalf of `user`. Raises on invalid transition / permission."""
    report = Report.objects.select_for_update().get(pk=report.pk)
    frm = report.status
    allowed = TRANSITIONS.get((frm, to))
    if allowed is None:
        raise InvalidTransition(f"لا يمكن الانتقال من «{S.LABELS.get(frm)}» إلى «{S.LABELS.get(to)}».")
    kinds = actor_kinds(user, report)
    if not (allowed & kinds):
        raise PermissionDenied("ليس لديك صلاحية لتنفيذ هذا الانتقال على هذا البلاغ.")
    if to in REASON_REQUIRED and not reason.strip():
        raise ValidationError({"reason": "يجب ذكر السبب."})
    now = timezone.now()
    extra = dict(data or {})

    if to == S.SUBMITTED:
        _validate_for_submission(report)
        report.submitted_at = report.submitted_at or now
        report.assign_tracking_number()
    elif to == S.NEEDS_INFO:
        report.needs_info_question = reason
    elif to == S.REFERRED:
        target = agency or report.agency
        if target is None:
            raise ValidationError({"agency": "حدد الجهة المختصة قبل الإحالة (لا توجد قاعدة توجيه لهذا الموقع والفئة)."})
        Referral.objects.filter(report=report, active=True).update(active=False)
        Referral.objects.create(report=report, agency=target, referred_by=user,
                                channel=extra.get("channel", "portal"))
        if report.agency_id != target.pk:
            report.agency = target
            report.routing_status = Report.ROUTING_MANUAL
        extra["agency"] = target.name
    elif to == S.ACKNOWLEDGED:
        ref = Referral.objects.filter(report=report, active=True).first()
        if ref is None:
            raise InvalidTransition("لا توجد إحالة فعالة لتأكيد استلامها.")
        if AGENCY not in kinds:  # coordinator recording an off-portal acknowledgement must explain the evidence
            if not note.strip():
                raise ValidationError({"note": "اذكر وسيلة تأكيد الاستلام من الجهة (رسالة، اتصال، كتاب رسمي)."})
            extra["recorded_by_coordinator"] = True
        ref.acknowledged_by = user
        ref.acknowledged_at = now
        ref.agency_reference = extra.get("agency_reference", "")[:60]
        ref.save()
    elif to == S.DONE_PENDING:
        if not CompletionProof.objects.filter(report=report, round=report.resolution_round).exists():
            raise ValidationError({"proof": "إثبات الإنجاز مطلوب (صورة وملاحظة) قبل طلب التحقق."})
    elif to == S.RESOLVED and frm == S.DONE_PENDING:
        _check_independent_confirmation(report, note)
        report.resolved_at = now
    elif to == S.RESOLVED and frm == S.DISPUTED:
        report.resolved_at = report.resolved_at or now
    elif to == S.REOPENED:
        report.reopen_count += 1
        report.resolution_round += 1
        report.resolved_at = None

    report.status = to
    report.status_changed_at = now
    if reason:
        report.status_reason = reason[:500]
    report.save()
    actor_role = _primary_role(allowed & kinds)
    event = ReportEvent.objects.create(report=report, actor=user, actor_role=actor_role, kind="status",
                                       from_status=frm, to_status=to, note=(note or reason)[:2000], data=extra,
                                       is_public=is_public)
    audit(user, "report.transition", report, frm=frm, to=to, reason=reason, role=actor_role)
    from .services import after_transition  # local import to avoid cycles
    transaction.on_commit(lambda: after_transition(report.pk, frm, to, event.pk))
    return report, event


def _validate_for_submission(report):
    errs = {}
    if not report.category_id:
        errs["category"] = "اختر الفئة."
    if not report.point:
        errs["point"] = "حدد الموقع."
    if report.observed_at and report.observed_at > timezone.now() + timedelta(minutes=5):
        errs["observed_at"] = "وقت الرصد لا يمكن أن يكون في المستقبل."
    if errs:
        raise ValidationError(errs)


def _check_independent_confirmation(report, note):
    proofs = CompletionProof.objects.filter(report=report, round=report.resolution_round)
    executors = set(proofs.values_list("submitted_by_id", flat=True))
    checks = CompletionCheck.objects.filter(report=report, round=report.resolution_round).exclude(user_id__in=executors)
    if report.agency_id:
        from apps.accounts.models import RoleAssignment
        agency_staff = RoleAssignment.objects.filter(role=Role.AGENCY_STAFF, agency_id=report.agency_id,
                                                     active=True).values_list("user_id", flat=True)
        checks = checks.exclude(user_id__in=list(agency_staff))
    if not checks.filter(verdict=CompletionCheck.FIXED).exists():
        raise ValidationError({"confirmation": "يلزم تأكيد مستقل (من غير المنفذ) بأن المشكلة حُلّت."})
    if checks.exclude(verdict=CompletionCheck.FIXED).exists() and not note.strip():
        raise ValidationError({"note": "يوجد تعارض بين التأكيدات؛ اكتب نتيجة مراجعة التعارض قبل الاعتماد."})
