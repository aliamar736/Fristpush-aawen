import hashlib
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DemoFlag(models.Model):
    """Rows created by the demo seeder carry is_demo=True so they can be filtered out and purged.
    Demo seeding is refused in production (settings.DEMO_DATA_ALLOWED)."""
    is_demo = models.BooleanField(default=False, db_index=True)

    class Meta:
        abstract = True


class AuditLog(models.Model):
    """Append-only log of sensitive changes (roles, transitions, finance, moderation, settings)."""
    at = models.DateTimeField(default=timezone.now, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+")
    action = models.CharField(max_length=80, db_index=True)
    target_type = models.CharField(max_length=60, blank=True)
    target_id = models.CharField(max_length=64, blank=True, db_index=True)
    data = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-at"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("AuditLog is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AuditLog is append-only")


class SystemSetting(models.Model):
    """Admin-tunable configuration (JSON values). Defaults live in apps.core.config.DEFAULTS."""
    key = models.CharField(max_length=80, unique=True)
    value = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    def __str__(self):
        return self.key


class IdempotencyRecord(models.Model):
    """Stores the first response for (user, key, scope) so client retries after a dropped connection
    never create duplicates."""
    key = models.CharField(max_length=80)
    scope = models.CharField(max_length=80)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    request_hash = models.CharField(max_length=64)
    status_code = models.PositiveSmallIntegerField()
    response = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "scope", "key"], name="uniq_idempotency")]


def media_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"{instance.kind}/{timezone.now():%Y/%m}/{uuid.uuid4().hex}.{ext}"


class MediaAsset(TimeStamped):
    """Uploaded evidence (photo / audio / document). Private by default: the public only ever sees
    media that a moderator approved (and possibly blurred)."""
    KIND_IMAGE, KIND_AUDIO, KIND_DOC = "image", "audio", "document"
    KINDS = [(KIND_IMAGE, "صورة"), (KIND_AUDIO, "تسجيل صوتي"), (KIND_DOC, "مستند")]
    PENDING, APPROVED, REJECTED = "pending_review", "approved", "rejected"
    STATUSES = [(PENDING, "بانتظار المراجعة"), (APPROVED, "معتمد للنشر"), (REJECTED, "مرفوض للنشر")]

    uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="media")
    kind = models.CharField(max_length=10, choices=KINDS)
    file = models.FileField(upload_to=media_path)
    public_file = models.FileField(upload_to=media_path, blank=True)  # blurred / approved derivative
    content_type = models.CharField(max_length=80)
    size_bytes = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    sha256 = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=20, choices=STATUSES, default=PENDING, db_index=True)
    sensitive_flags = models.JSONField(default=list, blank=True)  # e.g. ["possible_injured_person", "plate"]
    moderated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    moderated_at = models.DateTimeField(null=True, blank=True)
    moderation_note = models.CharField(max_length=300, blank=True)
    blurred_regions = models.JSONField(default=list, blank=True)
    transcript = models.TextField(blank=True)  # audio transcription (AI-assisted, editable)

    @property
    def is_public(self):
        return self.status == self.APPROVED

    @staticmethod
    def hash_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()
