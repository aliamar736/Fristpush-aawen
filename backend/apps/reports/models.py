import uuid

from django.conf import settings
from django.contrib.gis.db import models
from django.utils import timezone

from apps.core.models import DemoFlag, MediaAsset, TimeStamped

User = settings.AUTH_USER_MODEL


class Category(TimeStamped):
    LAYER_SERVICES, LAYER_ROAD, LAYER_PEDESTRIAN = "services", "road", "pedestrian"
    LAYERS = [(LAYER_SERVICES, "مشاكل الخدمات"), (LAYER_ROAD, "الطريق"), (LAYER_PEDESTRIAN, "سهولة حركة المشاة")]
    slug = models.SlugField(unique=True)
    name_ar = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80, blank=True)
    layer = models.CharField(max_length=20, choices=LAYERS, default=LAYER_SERVICES)
    hazard_weight = models.PositiveSmallIntegerField(default=2, help_text="0..5 خطورة الفئة")
    followup_days = models.PositiveSmallIntegerField(null=True, blank=True)
    icon = models.CharField(max_length=40, blank=True)
    keywords = models.JSONField(default=list, blank=True, help_text="كلمات تساعد اقتراح الفئة")
    sort_order = models.PositiveSmallIntegerField(default=100)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name_ar


class Status:
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    NEEDS_INFO = "needs_info"
    VERIFIED = "verified"
    REFERRED = "referred"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting_resource"
    DONE_PENDING = "done_pending_verification"
    RESOLVED = "resolved"
    DISPUTED = "disputed"
    REOPENED = "reopened"
    UNRESOLVABLE = "unresolvable"

    LABELS = {
        DRAFT: "مسودة", SUBMITTED: "مقدّم", UNDER_REVIEW: "تحت المراجعة", NEEDS_INFO: "يحتاج معلومات",
        VERIFIED: "موثّق", REFERRED: "محال للجهة", ACKNOWLEDGED: "استلام مؤكد من الجهة",
        IN_PROGRESS: "قيد التنفيذ", WAITING: "بانتظار مورد أو تصريح",
        DONE_PENDING: "إنجاز بانتظار التحقق", RESOLVED: "محلول", DISPUTED: "معترض عليه",
        REOPENED: "معاد فتحه", UNRESOLVABLE: "تعذّر الحل",
    }
    CHOICES = list(LABELS.items())
    ACTIVE = {SUBMITTED, UNDER_REVIEW, NEEDS_INFO, VERIFIED, REFERRED, ACKNOWLEDGED, IN_PROGRESS, WAITING,
              DONE_PENDING, DISPUTED, REOPENED}
    PUBLIC = set(LABELS) - {DRAFT}
    # Description becomes public only after a human reviewer verified the report
    DESCRIPTION_PUBLIC = {VERIFIED, REFERRED, ACKNOWLEDGED, IN_PROGRESS, WAITING, DONE_PENDING, RESOLVED,
                          DISPUTED, REOPENED, UNRESOLVABLE}


class Report(DemoFlag, TimeStamped):
    ROUTING_PENDING, ROUTING_AUTO, ROUTING_REVIEW, ROUTING_MANUAL = "pending", "auto", "needs_review", "manual"
    ROUTING = [(ROUTING_PENDING, "لم يُوجّه"), (ROUTING_AUTO, "توجيه آلي"), (ROUTING_REVIEW, "يحتاج مراجعة توجيه"),
               (ROUTING_MANUAL, "توجيه يدوي")]
    DANGER = [(0, "لا خطر"), (1, "إزعاج"), (2, "خطر محتمل"), (3, "خطر مباشر")]

    tracking_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    reporter = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="reports")
    client_id = models.UUIDField(null=True, blank=True)  # set by the client for idempotent retries
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="reports")
    description = models.TextField(max_length=2000, blank=True)
    point = models.PointField(srid=4326)
    location_edited = models.BooleanField(default=False)
    landmark = models.ForeignKey("geo.Landmark", null=True, blank=True, on_delete=models.SET_NULL)
    landmark_text = models.CharField(max_length=160, blank=True)
    area = models.ForeignKey("geo.Area", null=True, blank=True, on_delete=models.SET_NULL, related_name="reports")
    observed_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=Status.CHOICES, default=Status.DRAFT, db_index=True)
    status_changed_at = models.DateTimeField(default=timezone.now)
    status_reason = models.CharField(max_length=500, blank=True)
    needs_info_question = models.CharField(max_length=500, blank=True)
    danger_level = models.PositiveSmallIntegerField(choices=DANGER, default=1)
    agency = models.ForeignKey("agencies.Agency", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="reports")
    routing_status = models.CharField(max_length=20, choices=ROUTING, default=ROUTING_PENDING, db_index=True)
    routing_notes = models.CharField(max_length=300, blank=True)
    routing_candidates = models.JSONField(default=list, blank=True)
    follow_up_owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    field_assignee = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name="field_reports")
    priority_score = models.FloatField(default=0, db_index=True)
    priority_breakdown = models.JSONField(default=dict, blank=True)
    confirmations_count = models.PositiveIntegerField(default=0)
    reopen_count = models.PositiveSmallIntegerField(default=0)
    resolution_round = models.PositiveSmallIntegerField(default=1)
    resolved_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    sensitive_flags = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-priority_score", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["reporter", "client_id"], name="uniq_report_client_id")]
        indexes = [models.Index(fields=["status", "category"])]

    def __str__(self):
        return self.tracking_number or f"draft#{self.pk}"

    @property
    def status_label(self):
        return Status.LABELS.get(self.status, self.status)

    def assign_tracking_number(self):
        if not self.tracking_number and self.pk:
            year = (self.submitted_at or timezone.now()).year
            self.tracking_number = f"AW-{year}-{self.pk:06d}"


class ReportEvent(models.Model):
    KINDS = ["status", "comment", "evidence", "assignment", "routing", "confirmation", "escalation",
             "objection", "recurrence", "completion_check", "ai_suggestion", "bundle", "info"]
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="events")
    at = models.DateTimeField(default=timezone.now, db_index=True)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor_role = models.CharField(max_length=30, blank=True)
    kind = models.CharField(max_length=30, default="status")
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30, blank=True)
    note = models.TextField(blank=True)
    data = models.JSONField(default=dict, blank=True)
    is_public = models.BooleanField(default=True)

    class Meta:
        ordering = ["at", "id"]


class ReportMedia(models.Model):
    ROLES = [("initial", "دليل البلاغ"), ("additional", "معلومات إضافية"), ("completion_proof", "إثبات إنجاز"),
             ("completion_check", "تأكيد مستقل"), ("recurrence", "دليل رجوع المشكلة"), ("progress", "تقدم العمل")]
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="media")
    asset = models.ForeignKey(MediaAsset, on_delete=models.CASCADE, related_name="report_links")
    role = models.CharField(max_length=30, choices=ROLES, default="initial")
    event = models.ForeignKey(ReportEvent, null=True, blank=True, on_delete=models.SET_NULL)
    added_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    added_at = models.DateTimeField(default=timezone.now)


class Confirmation(models.Model):
    """'المشكلة موجودة' — a resident confirms an existing report instead of filing a duplicate."""
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="confirmations")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        constraints = [models.UniqueConstraint(fields=["report", "user"], name="uniq_confirmation")]


class Referral(models.Model):
    """Referral (إحالة) is separate from the agency's acknowledgement (استلام)."""
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="referrals")
    agency = models.ForeignKey("agencies.Agency", on_delete=models.PROTECT, related_name="referrals")
    referred_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    referred_at = models.DateTimeField(default=timezone.now)
    channel = models.CharField(max_length=30, default="portal")  # portal | email | letter | phone
    acknowledged_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    agency_reference = models.CharField(max_length=60, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-referred_at"]


class CompletionProof(models.Model):
    """شاهد الإنجاز — the executor's proof of completion."""
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="completion_proofs")
    round = models.PositiveSmallIntegerField(default=1)
    submitted_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CompletionCheck(models.Model):
    """Independent confirmation by someone other than the executor."""
    FIXED, NOT_FIXED, PARTIAL = "fixed", "not_fixed", "partial"
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="completion_checks")
    round = models.PositiveSmallIntegerField(default=1)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    verdict = models.CharField(max_length=12, choices=[(FIXED, "تم الإصلاح"), (NOT_FIXED, "لم يُصلح"),
                                                       (PARTIAL, "إصلاح جزئي")])
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["report", "round", "user"], name="uniq_check_per_round")]


class Objection(models.Model):
    OPEN, ACCEPTED, REJECTED = "open", "accepted", "rejected"
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="objections")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="objections")
    reason = models.TextField(max_length=1000)
    status = models.CharField(max_length=10, default=OPEN,
                              choices=[(OPEN, "مفتوح"), (ACCEPTED, "مقبول"), (REJECTED, "مرفوض")])
    decided_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class Recurrence(models.Model):
    """'المشكلة رجعت' — reopening linked to the previous fix, with new evidence."""
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="recurrences")
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    previous_round = models.PositiveSmallIntegerField()
    previous_resolved_at = models.DateTimeField(null=True)
    previous_proof = models.ForeignKey(CompletionProof, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)


class FollowUpReview(models.Model):
    PENDING, OK, RETURNED, CANCELLED = "pending", "ok", "problem_returned", "cancelled"
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="followups")
    round = models.PositiveSmallIntegerField()
    due_at = models.DateTimeField(db_index=True)
    assigned_to = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=20, default=PENDING,
                              choices=[(PENDING, "بانتظار المراجعة"), (OK, "الحل مستمر"),
                                       (RETURNED, "المشكلة رجعت"), (CANCELLED, "ملغاة")])
    done_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-id"]
        constraints = [models.UniqueConstraint(fields=["report", "round"], name="uniq_followup_round")]


class ReportBundle(DemoFlag, TimeStamped):
    """حزمة حل للحومة — groups nearby reports into one campaign/visit; each report keeps its own status."""
    PLANNED, ACTIVE, DONE, CANCELLED = "planned", "active", "done", "cancelled"
    title = models.CharField(max_length=160)
    kind = models.CharField(max_length=20, default="visit", choices=[("visit", "زيارة"), ("campaign", "حملة")])
    area = models.ForeignKey("geo.Area", null=True, blank=True, on_delete=models.SET_NULL)
    agency = models.ForeignKey("agencies.Agency", null=True, blank=True, on_delete=models.SET_NULL)
    coordinator = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    scheduled_for = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, default=PLANNED,
                              choices=[(PLANNED, "مخطط"), (ACTIVE, "جارٍ"), (DONE, "منتهٍ"), (CANCELLED, "ملغى")])
    reports = models.ManyToManyField(Report, related_name="bundles", blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-id"]

