from django.conf import settings
from django.db import models


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=40)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class DeviceToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="devices")
    token = models.CharField(max_length=400, unique=True)
    platform = models.CharField(max_length=10, choices=[("android", "Android"), ("ios", "iOS"), ("web", "Web")])
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)


class Delivery(models.Model):
    """Outbound message log (push / SMS) — records simulated deliveries explicitly as 'simulated'."""
    channel = models.CharField(max_length=10)  # push | sms
    provider = models.CharField(max_length=20)  # simulated | console | fcm | http | disabled
    to = models.CharField(max_length=400)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20)  # sent | simulated | failed | skipped
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
