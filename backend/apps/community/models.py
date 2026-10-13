from django.conf import settings
from django.contrib.gis.db import models
from django.utils import timezone

from apps.core.models import DemoFlag, TimeStamped

User = settings.AUTH_USER_MODEL


class Initiative(DemoFlag, TimeStamped):
    """A community initiative (مبادرة). Contributions are only accepted once approved."""
    DRAFT, PENDING, APPROVED, ACTIVE, COMPLETED, CANCELLED = ("draft", "pending_approval", "approved", "active",
                                                              "completed", "cancelled")
    STATUSES = [(DRAFT, "مسودة"), (PENDING, "بانتظار الاعتماد"), (APPROVED, "معتمدة"), (ACTIVE, "جارية"),
                (COMPLETED, "مكتملة"), (CANCELLED, "ملغاة")]
    ACCEPTING = {APPROVED, ACTIVE}
    title = models.CharField(max_length=160)
    summary = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    area = models.ForeignKey("geo.Area", null=True, blank=True, on_delete=models.SET_NULL, related_name="initiatives")
    point = models.PointField(srid=4326, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUSES, default=DRAFT, db_index=True)
    manager = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="managed_initiatives")
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    funding_target = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    funding_deadline = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    reports = models.ManyToManyField("reports.Report", blank=True, related_name="initiatives")
    results_summary = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Need(TimeStamped):
    """A need of an initiative. `is_blocking` needs feed «شن ناقص؟» (what is holding the initiative back)."""
    KINDS = [("transport", "نقل"), ("tools", "أدوات"), ("funding", "تمويل"), ("permit", "تصريح"),
             ("volunteers", "متطوعون"), ("materials", "مواد"), ("service", "خدمة مهنية"), ("other", "أخرى")]
    OPEN, PARTIAL, MET, CANCELLED = "open", "partial", "met", "cancelled"
    initiative = models.ForeignKey(Initiative, on_delete=models.CASCADE, related_name="needs")
    kind = models.CharField(max_length=20, choices=KINDS)
    title = models.CharField(max_length=160)
    details = models.TextField(blank=True)
    quantity_needed = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    quantity_fulfilled = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit = models.CharField(max_length=30, blank=True)
    is_blocking = models.BooleanField(default=False)
    status = models.CharField(max_length=10, default=OPEN,
                              choices=[(OPEN, "مفتوح"), (PARTIAL, "جزئي"), (MET, "مكتمل"), (CANCELLED, "ملغى")])


    class Meta:
        ordering = ["-id"]

    def refresh_status(self):
        if self.status == self.CANCELLED:
            return
        if self.quantity_fulfilled >= self.quantity_needed:
            self.status = self.MET
        elif self.quantity_fulfilled > 0:
            self.status = self.PARTIAL
        else:
            self.status = self.OPEN

class HelpOffer(TimeStamped):
    """Offer of help linked to a blocking need (transport, tools, permit help, service...)."""
    OFFERED, ACCEPTED, DECLINED, FULFILLED, WITHDRAWN = "offered", "accepted", "declined", "fulfilled", "withdrawn"
    need = models.ForeignKey(Need, on_delete=models.CASCADE, related_name="offers")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="help_offers")
    organization_name = models.CharField(max_length=160, blank=True)
    kind = models.CharField(max_length=12, default="in_kind",
                            choices=[("in_kind", "عيني"), ("service", "خدمي")])
    message = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    status = models.CharField(max_length=12, default=OFFERED,
                              choices=[(OFFERED, "معروض"), (ACCEPTED, "مقبول/محجوز"), (DECLINED, "معتذر عنه"),
                                       (FULFILLED, "مستلم"), (WITHDRAWN, "مسحوب")])
    decided_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    received_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    received_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]


class Skill(models.Model):
    slug = models.SlugField(unique=True)
    name_ar = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80, blank=True)

    def __str__(self):
        return self.name_ar


class VolunteerProfile(TimeStamped):
    """مهاراتي — skills, availability and preferences (no continuous location tracking)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="volunteer_profile")
    skills = models.ManyToManyField(Skill, blank=True)
    # availability: {"days": [0..6], "slots": ["morning","afternoon","evening"]}  (0=Saturday … 6=Friday)
    availability = models.JSONField(default=dict, blank=True)
    preferred_areas = models.ManyToManyField("geo.Area", blank=True)
    preferences = models.JSONField(default=dict, blank=True)  # e.g. {"outdoor": true, "max_hours": 3}
    bio = models.CharField(max_length=300, blank=True)


class Task(DemoFlag, TimeStamped):
    """خُذ مهمة — volunteer tasks with duration, location, skill, owner and capacity."""
    OPEN, FULL, DONE, CANCELLED = "open", "full", "done", "cancelled"
    initiative = models.ForeignKey(Initiative, null=True, blank=True, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    point = models.PointField(srid=4326, null=True, blank=True)
    area = models.ForeignKey("geo.Area", null=True, blank=True, on_delete=models.SET_NULL)
    location_text = models.CharField(max_length=160, blank=True)
    starts_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=120)
    skill = models.ForeignKey(Skill, null=True, blank=True, on_delete=models.SET_NULL)
    owner = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="owned_tasks")
    capacity = models.PositiveIntegerField(default=5)
    status = models.CharField(max_length=10, default=OPEN,
                              choices=[(OPEN, "متاحة"), (FULL, "مكتملة العدد"), (DONE, "منجزة"), (CANCELLED, "ملغاة")])

    class Meta:
        ordering = ["starts_at"]


class TaskBooking(TimeStamped):
    BOOKED, CANCELLED, ATTENDED, NO_SHOW, COMPLETED = "booked", "cancelled", "attended", "no_show", "completed"
    ACTIVE = {BOOKED, ATTENDED, COMPLETED}
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="bookings")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="task_bookings")
    status = models.CharField(max_length=10, default=BOOKED,
                              choices=[(BOOKED, "محجوزة"), (CANCELLED, "ملغاة"), (ATTENDED, "حضور مؤكد"),
                                       (NO_SHOW, "لم يحضر"), (COMPLETED, "منجزة")])
    attendance_confirmed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    completion_note = models.CharField(max_length=500, blank=True)
    completion_media = models.ManyToManyField("core.MediaAsset", blank=True)

    class Meta:
        ordering = ["-id"]
        constraints = [models.UniqueConstraint(fields=["task", "user"], name="uniq_booking")]


class CarePoint(DemoFlag, TimeStamped):
    """نقاط العناية بالحومة — verified hosts (water, shade, first aid, phone charging, ...)."""
    name = models.CharField(max_length=160)
    host_type = models.CharField(max_length=60)
    area = models.ForeignKey("geo.Area", null=True, blank=True, on_delete=models.SET_NULL)
    point = models.PointField(srid=4326)
    services = models.JSONField(default=list)
    hours = models.CharField(max_length=160)
    contact = models.CharField(max_length=80, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-id"]


class BudgetCycle(DemoFlag, TimeStamped):
    DRAFT, REVIEW, VOTING, CLOSED = "draft", "review", "voting", "closed"
    title = models.CharField(max_length=160)
    area = models.ForeignKey("geo.Area", null=True, blank=True, on_delete=models.SET_NULL)
    budget_amount = models.DecimalField(max_digits=12, decimal_places=2)
    budget_source = models.CharField(max_length=200, help_text="مصدر الميزانية المعلنة")
    voting_opens = models.DateTimeField()
    voting_closes = models.DateTimeField()
    status = models.CharField(max_length=10, default=DRAFT,
                              choices=[(DRAFT, "مسودة"), (REVIEW, "مراجعة الاقتراحات"), (VOTING, "تصويت"),
                                       (CLOSED, "مغلقة")])


    class Meta:
        ordering = ["-id"]

    def voting_open(self, now=None):
        now = now or timezone.now()
        return self.status == self.VOTING and self.voting_opens <= now < self.voting_closes

class Proposal(DemoFlag, TimeStamped):
    """اقتراحات الحومة: proposal → feasibility/permit/cost/maintenance review → eligible → vote."""
    SUBMITTED, REVIEW, NEEDS_CHANGES, ELIGIBLE, REJECTED, SELECTED = ("submitted", "under_review", "needs_changes",
                                                                      "eligible", "rejected", "selected")
    cycle = models.ForeignKey(BudgetCycle, null=True, blank=True, on_delete=models.SET_NULL, related_name="proposals")
    area = models.ForeignKey("geo.Area", null=True, blank=True, on_delete=models.SET_NULL)
    proposer = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="proposals")
    title = models.CharField(max_length=160)
    description = models.TextField()
    point = models.PointField(srid=4326, null=True, blank=True)
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=15, default=SUBMITTED, db_index=True,
                              choices=[(SUBMITTED, "مقدّم"), (REVIEW, "قيد المراجعة"), (NEEDS_CHANGES, "يحتاج تعديل"),
                                       (ELIGIBLE, "مؤهل للتصويت"), (REJECTED, "غير مؤهل"), (SELECTED, "مختار")])
    feasibility_ok = models.BooleanField(null=True)
    permit_ok = models.BooleanField(null=True)
    cost_verified = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    maintenance_plan = models.CharField(max_length=500, blank=True)
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    votes_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-id"]


class ProposalVote(models.Model):
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["proposal", "user"], name="uniq_proposal_vote")]


class SurplusOffer(DemoFlag, TimeStamped):
    """فائض ينفع — usable surplus. Food sharing stays disabled until a partner + procedure exist."""
    AVAILABLE, RESERVED, HANDED_OVER, EXPIRED, WITHDRAWN = "available", "reserved", "handed_over", "expired", "withdrawn"
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="surplus_offers")
    title = models.CharField(max_length=160)
    kind = models.CharField(max_length=12, choices=[("non_food", "غير غذائي"), ("food", "غذائي")], default="non_food")
    quantity = models.CharField(max_length=60)
    area = models.ForeignKey("geo.Area", null=True, blank=True, on_delete=models.SET_NULL)
    pickup_location = models.CharField(max_length=200)
    pickup_window = models.CharField(max_length=120)
    available_until = models.DateTimeField()
    status = models.CharField(max_length=12, default=AVAILABLE,
                              choices=[(AVAILABLE, "متاح"), (RESERVED, "محجوز"), (HANDED_OVER, "مُسلّم"),
                                       (EXPIRED, "انتهى"), (WITHDRAWN, "مسحوب")])
    reserved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reserved_at = models.DateTimeField(null=True, blank=True)
    handed_over_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]


class SurveyAssignment(DemoFlag, TimeStamped):
    """Ambassador field-survey assignment for low-participation areas."""
    ASSIGNED, IN_PROGRESS, DONE, CANCELLED = "assigned", "in_progress", "done", "cancelled"
    area = models.ForeignKey("geo.Area", on_delete=models.CASCADE, related_name="surveys")
    ambassador = models.ForeignKey(User, on_delete=models.CASCADE, related_name="surveys")
    assigned_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    due_at = models.DateTimeField()
    instructions = models.TextField(blank=True)
    status = models.CharField(max_length=12, default=ASSIGNED,
                              choices=[(ASSIGNED, "مكلّف"), (IN_PROGRESS, "جارٍ"), (DONE, "منجز"), (CANCELLED, "ملغى")])
    findings_note = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

