from django.conf import settings
from django.contrib.gis.db import models
from django.utils import timezone

from apps.core.models import DemoFlag


class RoadAlert(DemoFlag):
    """الطريق توّا — temporary road alerts. Congestion here is *reported* congestion only: the platform
    never fabricates speeds, travel times or computed alternative routes."""
    ACCIDENT, CONGESTION, CLOSURE, OBSTACLE = "accident", "congestion", "closure", "obstacle"
    TYPES = [(ACCIDENT, "حادث"), (CONGESTION, "ازدحام مبلّغ عنه"), (CLOSURE, "إغلاق"), (OBSTACLE, "عائق")]
    SRC_CITIZEN, SRC_AMBASSADOR, SRC_AGENCY, SRC_INTEGRATION = "citizen", "ambassador", "agency", "integration"
    SOURCES = [(SRC_CITIZEN, "مواطن"), (SRC_AMBASSADOR, "سفير"), (SRC_AGENCY, "جهة رسمية"), (SRC_INTEGRATION, "تكامل")]
    UNVERIFIED, COMMUNITY, OFFICIAL = "unverified", "community_confirmed", "official"
    VERIFICATION = [(UNVERIFIED, "غير مؤكد"), (COMMUNITY, "مؤكد من عدة مستخدمين"), (OFFICIAL, "مؤكد من جهة رسمية")]
    ACTIVE, EXPIRED, CLEARED, HISTORICAL = "active", "expired", "cleared", "historical"
    STATUSES = [(ACTIVE, "قائم"), (EXPIRED, "انتهت صلاحيته"), (CLEARED, "الطريق فتح"),
                (HISTORICAL, "رصد متأخر (غير مباشر)")]

    type = models.CharField(max_length=20, choices=TYPES)
    point = models.PointField(srid=4326)
    area = models.ForeignKey("geo.Area", null=True, blank=True, on_delete=models.SET_NULL)
    description = models.CharField(max_length=500, blank=True)
    direction = models.CharField(max_length=80, blank=True)
    observed_at = models.DateTimeField()
    reported_at = models.DateTimeField(default=timezone.now)
    last_confirmed_at = models.DateTimeField()
    expires_at = models.DateTimeField(db_index=True)
    source = models.CharField(max_length=20, choices=SOURCES, default=SRC_CITIZEN)
    verification = models.CharField(max_length=24, choices=VERIFICATION, default=UNVERIFIED)
    status = models.CharField(max_length=12, choices=STATUSES, default=ACTIVE, db_index=True)
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    client_id = models.UUIDField(null=True, blank=True)
    still_there_count = models.PositiveIntegerField(default=0)
    cleared_count = models.PositiveIntegerField(default=0)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_confirmed_at"]
        constraints = [models.UniqueConstraint(fields=["reporter", "client_id"], name="uniq_alert_client_id")]


class RoadAlertVote(models.Model):
    STILL_THERE, CLEARED = "still_there", "cleared"
    alert = models.ForeignKey(RoadAlert, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    vote = models.CharField(max_length=12, choices=[(STILL_THERE, "ما زال موجود"), (CLEARED, "الطريق فتح")])
    created_at = models.DateTimeField(default=timezone.now)
