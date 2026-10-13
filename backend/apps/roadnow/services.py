from datetime import timedelta

from django.contrib.gis.geos import Point
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Role
from apps.accounts.permissions import has_role
from apps.core.audit import audit
from apps.core.config import get_setting
from apps.core.exceptions import Conflict

from .models import RoadAlert, RoadAlertVote

VOTE_COOLDOWN = timedelta(minutes=10)


def rules_for(alert_type):
    return get_setting("road_rules")[alert_type]


def _cap(alert, candidate):
    rule = rules_for(alert.type)
    return min(candidate, alert.observed_at + timedelta(minutes=rule["max_lifetime"]))


@transaction.atomic
def create_alert(user, data, now=None):
    now = now or timezone.now()
    t = data.get("type")
    if t not in dict(RoadAlert.TYPES):
        raise ValidationError({"type": "نوع غير صحيح."})
    observed = data.get("observed_at") or now
    if observed > now + timedelta(minutes=2):
        raise ValidationError({"observed_at": "وقت الرصد لا يمكن أن يكون في المستقبل."})
    client_id = data.get("client_id")
    if client_id:
        existing = RoadAlert.objects.filter(reporter=user, client_id=client_id).first()
        if existing:
            return existing, False
    rule = rules_for(t)
    source = RoadAlert.SRC_CITIZEN
    verification = RoadAlert.UNVERIFIED
    if has_role(user, Role.AGENCY_STAFF, any_scope=True) and data.get("official"):
        source, verification = RoadAlert.SRC_AGENCY, RoadAlert.OFFICIAL
    elif has_role(user, Role.AMBASSADOR, any_scope=True):
        source = RoadAlert.SRC_AMBASSADOR
    alert = RoadAlert(type=t, point=Point(float(data["lng"]), float(data["lat"]), srid=4326),
                      description=(data.get("description") or "")[:500], direction=(data.get("direction") or "")[:80],
                      observed_at=observed, reported_at=now, last_confirmed_at=observed, reporter=user,
                      client_id=client_id, source=source, verification=verification)
    age = now - observed
    if age > timedelta(minutes=rule["stale_after"]):
        # Delayed submission (e.g. sent after reconnecting): never published as a live event.
        alert.status = RoadAlert.HISTORICAL
        alert.expires_at = observed + timedelta(minutes=rule["ttl"])
    else:
        alert.expires_at = _cap(alert, observed + timedelta(minutes=rule["ttl"]))
        if alert.expires_at <= now:
            alert.status = RoadAlert.HISTORICAL
    from apps.reports.routing import locate
    inside, _ = locate(alert.point)
    alert.area_id = inside[0] if inside else None
    try:
        with transaction.atomic():
            alert.save()
    except IntegrityError:
        return RoadAlert.objects.get(reporter=user, client_id=client_id), False
    return alert, True


@transaction.atomic
def vote(alert, user, value, now=None):
    now = now or timezone.now()
    alert = RoadAlert.objects.select_for_update().get(pk=alert.pk)
    if alert.status != RoadAlert.ACTIVE:
        raise Conflict("هذا التنبيه لم يعد قائمًا.")
    if value not in (RoadAlertVote.STILL_THERE, RoadAlertVote.CLEARED):
        raise ValidationError({"vote": "قيمة غير صحيحة."})
    recent = RoadAlertVote.objects.filter(alert=alert, user=user, created_at__gte=now - VOTE_COOLDOWN).exists()
    if recent:
        raise Conflict("سجلت رأيك مؤخرًا. حاول بعد دقائق.")
    RoadAlertVote.objects.create(alert=alert, user=user, vote=value, created_at=now)
    rule = rules_for(alert.type)
    official = has_role(user, Role.AGENCY_STAFF, any_scope=True)
    if value == RoadAlertVote.STILL_THERE:
        alert.still_there_count += 1
        alert.last_confirmed_at = now
        alert.expires_at = _cap(alert, max(alert.expires_at, now + timedelta(minutes=rule["extend"])))
        distinct = RoadAlertVote.objects.filter(alert=alert, vote=RoadAlertVote.STILL_THERE).values("user").distinct().count()
        if alert.verification == RoadAlert.UNVERIFIED and distinct >= 2:
            alert.verification = RoadAlert.COMMUNITY
        if official:
            alert.verification = RoadAlert.OFFICIAL
    else:
        alert.cleared_count += 1
        recent_cleared = RoadAlertVote.objects.filter(alert=alert, vote=RoadAlertVote.CLEARED,
                                                      created_at__gt=alert.last_confirmed_at).values("user").distinct().count()
        if official or recent_cleared >= rule["clear_votes"]:
            alert.status = RoadAlert.CLEARED
            alert.closed_at = now
    alert.save()
    if official:
        audit(user, "roadalert.official_vote", alert, vote=value)
    return alert


def expire_alerts(now=None):
    now = now or timezone.now()
    return RoadAlert.objects.filter(status=RoadAlert.ACTIVE, expires_at__lte=now).update(
        status=RoadAlert.EXPIRED, closed_at=now)
