"""Periodic jobs. NOTE: none of these change a report's status — time passing never closes a report."""
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.config import get_setting

from . import priority
from .models import FollowUpReview, Report, ReportEvent, Status
from .services import schedule_followup


@shared_task
def schedule_followups():
    n = 0
    for r in Report.objects.filter(status=Status.RESOLVED).select_related("category"):
        if not FollowUpReview.objects.filter(report=r, round=r.resolution_round).exists():
            schedule_followup(r)
            n += 1
    return n


@shared_task
def recompute_priorities():
    n = 0
    for r in Report.objects.filter(status__in=Status.ACTIVE).select_related("category"):
        priority.update(r)
        n += 1
    return n


@shared_task
def escalate_unacknowledged(now=None):
    """Referred but not acknowledged after N days → flag + notify coordinators. The report stays open."""
    from apps.notifications.services import notify_role
    now = now or timezone.now()
    days = int(get_setting("referral_escalation_days"))
    qs = Report.objects.filter(status=Status.REFERRED, status_changed_at__lt=now - timedelta(days=days),
                               escalated_at__isnull=True)
    n = 0
    for r in qs:
        r.escalated_at = now
        r.save(update_fields=["escalated_at"])
        ReportEvent.objects.create(report=r, kind="escalation", is_public=True,
                                   note=f"لم تؤكد الجهة الاستلام خلال {days} أيام؛ رُفع للمنسق للمتابعة. البلاغ يبقى مفتوحًا.")
        notify_role(Role.COORDINATOR, "escalation", f"إحالة بلا استلام: {r.tracking_number}", "",
                    {"report_id": r.pk}, area_id=r.area_id)
        n += 1
    return n
