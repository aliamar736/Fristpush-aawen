from datetime import timedelta

from django.contrib.gis.geos import Point
from django.db import IntegrityError, connection, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Role
from apps.accounts.permissions import has_role
from apps.core.config import get_setting
from apps.core.exceptions import Conflict, InvalidTransition
from apps.core.models import MediaAsset

from . import priority, routing, workflow
from .models import (CompletionCheck, CompletionProof, Confirmation, FollowUpReview, Objection, Recurrence,
                     Report, ReportEvent, ReportMedia, Status)


def _attach_media(report, user, media_ids, role, event=None):
    if not media_ids:
        return []
    assets = list(MediaAsset.objects.filter(uid__in=media_ids, owner=user))
    if len(assets) != len(set(map(str, media_ids))):
        raise ValidationError({"media": "بعض الملفات غير موجودة أو لا تخصك."})
    links = []
    for a in assets:
        links.append(ReportMedia.objects.create(report=report, asset=a, role=role, event=event, added_by=user))
    return links


def similar_reports(point, category_id=None, exclude_id=None, limit=5):
    radius = float(get_setting("similar_radius_m"))
    since = timezone.now() - timedelta(days=int(get_setting("similar_window_days")))
    qs = Report.objects.filter(status__in=Status.ACTIVE | {Status.RESOLVED}, submitted_at__gte=since)
    if category_id:
        qs = qs.filter(category_id=category_id)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    ids_dist = []
    with connection.cursor() as cur:
        sql_ids = list(qs.values_list("id", flat=True)[:2000])
        if not sql_ids:
            return []
        cur.execute(
            "SELECT id, ST_Distance(point::geography, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography) d "
            "FROM reports_report WHERE id = ANY(%s) AND "
            "ST_DWithin(point::geography, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s) ORDER BY d LIMIT %s",
            [point.x, point.y, sql_ids, point.x, point.y, radius, limit])
        ids_dist = cur.fetchall()
    by_id = {r.pk: r for r in Report.objects.filter(pk__in=[i for i, _ in ids_dist]).select_related("category")}
    out = []
    for rid, dist in ids_dist:
        r = by_id[rid]
        r.distance_m = round(dist, 1)
        out.append(r)
    return out


@transaction.atomic
def create_report(user, data, submit=True):
    """Creates (and by default submits) a report. Idempotent per (user, client_id)."""
    client_id = data.get("client_id")
    if client_id:
        existing = Report.objects.filter(reporter=user, client_id=client_id).first()
        if existing:
            return existing, False
    point = Point(float(data["lng"]), float(data["lat"]), srid=4326)
    observed = data.get("observed_at") or timezone.now()
    from apps.ai import services as ai
    text = data.get("description", "")
    report = Report(reporter=user, client_id=client_id, category_id=data["category"], description=text,
                    point=point, location_edited=bool(data.get("location_edited")),
                    landmark_id=data.get("landmark"), landmark_text=data.get("landmark_text", "")[:160],
                    observed_at=observed, danger_level=int(data.get("danger_level", 1)))
    report.sensitive_flags = ai.detect_sensitive(text)
    try:
        with transaction.atomic():
            report.save()
    except IntegrityError:
        existing = Report.objects.get(reporter=user, client_id=client_id)
        return existing, False
    ReportEvent.objects.create(report=report, actor=user, actor_role="owner", kind="status", from_status="",
                               to_status=Status.DRAFT, note="أُنشئت المسودة", is_public=False)
    _attach_media(report, user, data.get("media", []), "initial")
    routing.route(report)
    if submit:
        report, _ = workflow.transition(report, Status.SUBMITTED, user)
    priority.update(report)
    report.refresh_from_db()
    return report, True


@transaction.atomic
def confirm_existing(report, user, note=""):
    if report.status not in Status.ACTIVE:
        raise InvalidTransition("لا يمكن تأكيد بلاغ مغلق. إذا رجعت المشكلة استخدم «المشكلة رجعت».")
    if report.reporter_id == user.pk:
        raise Conflict("أنت صاحب هذا البلاغ.")
    try:
        with transaction.atomic():
            Confirmation.objects.create(report=report, user=user, note=note[:300])
    except IntegrityError:
        raise Conflict("سبق أن أكدت هذا البلاغ.")
    Report.objects.filter(pk=report.pk).update(confirmations_count=F("confirmations_count") + 1)
    report.refresh_from_db()
    ReportEvent.objects.create(report=report, actor=user, actor_role="public", kind="confirmation",
                               note="أكّد أحد السكان وجود المشكلة")
    priority.update(report)
    return report


@transaction.atomic
def add_info(report, user, note, media_ids=()):
    """Owner answers a 'needs info' request (or adds evidence) — moves back to review."""
    if report.reporter_id != user.pk and not has_role(user, Role.REVIEWER, Role.COORDINATOR, area=report.area_id):
        raise PermissionDenied()
    event = ReportEvent.objects.create(report=report, actor=user, kind="info", note=note[:2000], is_public=False)
    _attach_media(report, user, media_ids, "additional", event)
    if report.status == Status.NEEDS_INFO and report.reporter_id == user.pk:
        workflow.transition(report, Status.UNDER_REVIEW, user, note="أضاف المبلّغ المعلومات المطلوبة")
    return report


@transaction.atomic
def submit_completion_proof(report, user, note, media_ids):
    kinds = workflow.actor_kinds(user, report)
    if not kinds & {workflow.AGENCY, workflow.COORD, workflow.FIELD}:
        raise PermissionDenied("إثبات الإنجاز من المنفذ فقط.")
    if report.status not in (Status.IN_PROGRESS, Status.WAITING):
        raise InvalidTransition("إثبات الإنجاز يكون أثناء التنفيذ.")
    if not media_ids:
        raise ValidationError({"media": "أرفق صورة واحدة على الأقل بعد الإنجاز."})
    proof = CompletionProof.objects.create(report=report, round=report.resolution_round, submitted_by=user, note=note)
    event = ReportEvent.objects.create(report=report, actor=user, kind="evidence", note=note[:2000],
                                       data={"proof_id": proof.pk})
    _attach_media(report, user, media_ids, "completion_proof", event)
    workflow.transition(report, Status.DONE_PENDING, user, note=note)
    report.refresh_from_db()
    return proof


@transaction.atomic
def completion_check(report, user, verdict, note="", media_ids=()):
    if report.status != Status.DONE_PENDING:
        raise InvalidTransition("التأكيد المستقل متاح عندما يكون الإنجاز بانتظار التحقق.")
    if CompletionProof.objects.filter(report=report, round=report.resolution_round, submitted_by=user).exists():
        raise PermissionDenied("لا يمكن للمنفذ تأكيد عمله بنفسه.")
    if verdict not in (CompletionCheck.FIXED, CompletionCheck.NOT_FIXED, CompletionCheck.PARTIAL):
        raise ValidationError({"verdict": "قيمة غير صحيحة."})
    try:
        with transaction.atomic():
            check = CompletionCheck.objects.create(report=report, round=report.resolution_round, user=user,
                                                   verdict=verdict, note=note[:500])
    except IntegrityError:
        raise Conflict("سبق أن سجلت تأكيدك لهذه الجولة.")
    event = ReportEvent.objects.create(report=report, actor=user, kind="completion_check", note=note[:500],
                                       data={"verdict": verdict})
    _attach_media(report, user, media_ids, "completion_check", event)
    return check


@transaction.atomic
def object_to_resolution(report, user, reason):
    if report.status != Status.RESOLVED:
        raise InvalidTransition("الاعتراض متاح على البلاغات المحلولة.")
    if not reason.strip():
        raise ValidationError({"reason": "اكتب سبب الاعتراض."})
    obj = Objection.objects.create(report=report, user=user, reason=reason)
    workflow.transition(report, Status.DISPUTED, user, reason=reason, data={"objection_id": obj.pk})
    return obj


@transaction.atomic
def decide_objection(objection, user, accept, note):
    report = objection.report
    if not has_role(user, Role.REVIEWER, Role.COORDINATOR, area=report.area_id):
        raise PermissionDenied()
    if objection.status != Objection.OPEN:
        raise Conflict("تم البت في هذا الاعتراض.")
    if not note.strip():
        raise ValidationError({"note": "اكتب نتيجة المراجعة."})
    objection.status = Objection.ACCEPTED if accept else Objection.REJECTED
    objection.decided_by, objection.decided_at, objection.decision_note = user, timezone.now(), note[:500]
    objection.save()
    if accept:
        workflow.transition(report, Status.REOPENED, user, reason="قُبل الاعتراض: " + note)
    else:
        workflow.transition(report, Status.RESOLVED, user, note="رُفض الاعتراض: " + note)
    return objection


@transaction.atomic
def report_recurrence(report, user, note, media_ids):
    """'المشكلة رجعت': links the reopening to the previous fix and requires new evidence."""
    if report.status != Status.RESOLVED:
        raise InvalidTransition("«المشكلة رجعت» متاحة للبلاغات المحلولة فقط.")
    if not media_ids:
        raise ValidationError({"media": "أرفق دليلًا جديدًا (صورة حديثة) يُظهر رجوع المشكلة."})
    if not note.strip():
        raise ValidationError({"note": "صف ما الذي رجع."})
    proof = CompletionProof.objects.filter(report=report, round=report.resolution_round).order_by("-created_at").first()
    rec = Recurrence.objects.create(report=report, user=user, previous_round=report.resolution_round,
                                    previous_resolved_at=report.resolved_at, previous_proof=proof, note=note)
    event = ReportEvent.objects.create(report=report, actor=user, kind="recurrence", note=note[:1000],
                                       data={"recurrence_id": rec.pk, "previous_round": rec.previous_round})
    _attach_media(report, user, media_ids, "recurrence", event)
    FollowUpReview.objects.filter(report=report, status=FollowUpReview.PENDING).update(
        status=FollowUpReview.RETURNED, done_at=timezone.now(), note="بلّغ أحد السكان برجوع المشكلة")
    workflow.transition(report, Status.REOPENED, user, reason="المشكلة رجعت: " + note,
                        data={"recurrence_id": rec.pk})
    priority.update(report)
    return rec


def schedule_followup(report):
    days = report.category.followup_days or int(get_setting("followup_days_default"))
    FollowUpReview.objects.get_or_create(
        report=report, round=report.resolution_round,
        defaults={"due_at": (report.resolved_at or timezone.now()) + timedelta(days=days),
                  "assigned_to": report.follow_up_owner})


@transaction.atomic
def complete_followup(followup, user, ok, note, media_ids=()):
    report = followup.report
    if not (has_role(user, Role.REVIEWER, Role.COORDINATOR, Role.AMBASSADOR, area=report.area_id)
            or followup.assigned_to_id == user.pk):
        raise PermissionDenied()
    if followup.status != FollowUpReview.PENDING:
        raise Conflict("تمت هذه المراجعة.")
    if ok:
        followup.status, followup.done_at, followup.note = FollowUpReview.OK, timezone.now(), note[:500]
        followup.save()
        ReportEvent.objects.create(report=report, actor=user, kind="info", note="مراجعة لاحقة: الحل مستمر. " + note)
        return followup
    return report_recurrence(report, user, note, media_ids)


def after_transition(report_id, frm, to, event_id):
    """Side effects after commit: notifications, follow-up scheduling, priority refresh."""
    from apps.notifications.services import notify, notify_role
    report = Report.objects.select_related("category", "agency").get(pk=report_id)
    label = Status.LABELS.get(to, to)
    if report.reporter_id:
        notify(report.reporter, "report_status", f"بلاغك {report.tracking_number}: {label}",
               report.status_reason or "", {"report_id": report.pk, "status": to})
    for uid in report.confirmations.values_list("user_id", flat=True)[:200]:
        from apps.accounts.models import User
        u = User.objects.filter(pk=uid).first()
        if u:
            notify(u, "report_status", f"بلاغ أكدته: {label}", "", {"report_id": report.pk, "status": to})
    if to == Status.REFERRED and report.agency_id:
        notify_role(Role.AGENCY_STAFF, "referral", f"إحالة جديدة {report.tracking_number}",
                    report.category.name_ar, {"report_id": report.pk}, agency_id=report.agency_id)
    if to == Status.RESOLVED:
        schedule_followup(report)
    if to in (Status.SUBMITTED, Status.REOPENED):
        notify_role(Role.REVIEWER, "review_queue", f"بلاغ يحتاج مراجعة {report.tracking_number}",
                    report.category.name_ar, {"report_id": report.pk}, area_id=report.area_id)
    if report.follow_up_owner_id and report.follow_up_owner_id != report.reporter_id:
        notify(report.follow_up_owner, "report_status", f"بلاغ تتابعه {report.tracking_number}: {label}", "",
               {"report_id": report.pk, "status": to})
    priority.update(report)
