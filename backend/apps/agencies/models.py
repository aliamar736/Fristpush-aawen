from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import DemoFlag, TimeStamped


class Agency(DemoFlag, TimeStamped):
    """A service authority or partner (e.g. municipality cleaning, water & sewage, electricity)."""
    KINDS = [("municipality", "بلدية"), ("utility", "شركة خدمية"), ("ministry", "وزارة/إدارة"),
             ("partner", "شريك"), ("ngo", "منظمة")]
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=20, choices=KINDS, default="municipality")
    city = models.ForeignKey("geo.City", null=True, blank=True, on_delete=models.SET_NULL)
    contact_phone = models.CharField(max_length=40, blank=True)
    contact_email = models.EmailField(blank=True)
    is_linked = models.BooleanField(default=False, help_text="الجهة تستخدم البوابة فعليًا وتؤكد الاستلام")
    active = models.BooleanField(default=True)


    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.name

class JurisdictionRule(TimeStamped):
    """Routing directory: (area or whole city) × category → responsible agency."""
    category = models.ForeignKey("reports.Category", on_delete=models.CASCADE, related_name="rules")
    area = models.ForeignKey("geo.Area", null=True, blank=True, on_delete=models.CASCADE, related_name="rules")
    city = models.ForeignKey("geo.City", null=True, blank=True, on_delete=models.CASCADE, related_name="rules")
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="rules")
    priority = models.PositiveSmallIntegerField(default=100, help_text="الأصغر يُطبّق أولًا")
    note = models.CharField(max_length=200, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["priority", "id"]


class AgencyAnnouncement(DemoFlag, TimeStamped):
    """تنبيهات الجهات: planned outages, works, closures published by an agency for areas."""
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="announcements")
    areas = models.ManyToManyField("geo.Area", related_name="announcements", blank=True)
    title = models.CharField(max_length=160)
    body = models.TextField()
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    published = models.BooleanField(default=True)

    class Meta:
        ordering = ["-starts_at"]


class ServiceDirectoryEntry(DemoFlag, TimeStamped):
    """دليل خدمات موثق: verified contact points; shows when it was last verified."""
    name = models.CharField(max_length=160)
    service = models.CharField(max_length=120)
    agency = models.ForeignKey(Agency, null=True, blank=True, on_delete=models.SET_NULL)
    area = models.ForeignKey("geo.Area", null=True, blank=True, on_delete=models.SET_NULL, related_name="services")
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=200, blank=True)
    hours = models.CharField(max_length=120, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-id"]

