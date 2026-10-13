from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q, Sum

from apps.core.models import DemoFlag, TimeStamped

User = settings.AUTH_USER_MODEL
LYD = "LYD"


class Pledge(DemoFlag, TimeStamped):
    """A financial commitment (تعهد). It is NOT money received; only a confirmed Payment is."""
    PLEDGED, AWAITING, PAID, CANCELLED, EXPIRED, REFUNDED = ("pledged", "awaiting_payment", "paid", "cancelled",
                                                             "expired", "refunded")
    initiative = models.ForeignKey("community.Initiative", on_delete=models.PROTECT, related_name="pledges")
    need = models.ForeignKey("community.Need", null=True, blank=True, on_delete=models.SET_NULL, related_name="pledges")
    contributor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="pledges")
    organization_name = models.CharField(max_length=160, blank=True)
    is_corporate = models.BooleanField(default=False)
    is_anonymous = models.BooleanField(default=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=LYD)
    method = models.CharField(max_length=15, default="online",
                              choices=[("online", "دفع إلكتروني"), ("bank_transfer", "تحويل مصرفي"), ("cash", "نقدًا بإيصال")])
    status = models.CharField(max_length=20, default=PLEDGED, db_index=True,
                              choices=[(PLEDGED, "تعهد"), (AWAITING, "بانتظار الدفع"), (PAID, "مدفوع ومؤكد"),
                                       (CANCELLED, "ملغى"), (EXPIRED, "منتهٍ"), (REFUNDED, "مسترد")])
    client_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="pledge_amount_positive"),
                       models.UniqueConstraint(fields=["contributor", "client_id"], name="uniq_pledge_client")]


class Payment(TimeStamped):
    INITIATED, SUCCEEDED, FAILED, REFUNDED, PARTIAL_REFUND, REVIEW = ("initiated", "succeeded", "failed", "refunded",
                                                                      "partially_refunded", "needs_review")
    pledge = models.ForeignKey(Pledge, on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=30)  # simulator | generic_http | bank_transfer | cash
    provider_payment_id = models.CharField(max_length=120, unique=True, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    refunded_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    status = models.CharField(max_length=20, default=INITIATED, db_index=True,
                              choices=[(INITIATED, "بدأت"), (SUCCEEDED, "مؤكدة"), (FAILED, "فشلت"),
                                       (REFUNDED, "مستردة"), (PARTIAL_REFUND, "مستردة جزئيًا"),
                                       (REVIEW, "تحتاج مراجعة")])
    failure_reason = models.CharField(max_length=300, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    receipt_number = models.CharField(max_length=30, unique=True, null=True, blank=True)
    is_simulated = models.BooleanField(default=False)
    checkout_url = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-id"]


class ProviderEvent(models.Model):
    """Every webhook delivery, stored once per (provider, event_id): duplicates are detected and ignored."""
    provider = models.CharField(max_length=30)
    event_id = models.CharField(max_length=120)
    type = models.CharField(max_length=40)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    deliveries = models.PositiveIntegerField(default=1)
    processed_at = models.DateTimeField(null=True, blank=True)
    result = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "event_id"], name="uniq_provider_event")]


class TransferProof(TimeStamped):
    """A screenshot/receipt of a bank transfer uploaded by a contributor. It is NOT a confirmed payment
    until an accountant matches it against the bank statement."""
    PENDING, MATCHED, REJECTED = "pending", "matched", "rejected"
    pledge = models.ForeignKey(Pledge, on_delete=models.PROTECT, related_name="transfer_proofs")
    asset = models.ForeignKey("core.MediaAsset", on_delete=models.PROTECT)
    uploaded_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    claimed_reference = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=10, default=PENDING,
                              choices=[(PENDING, "بانتظار المطابقة"), (MATCHED, "مطابق"), (REJECTED, "غير مطابق")])
    matched_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    matched_at = models.DateTimeField(null=True, blank=True)
    payment = models.OneToOneField(Payment, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-id"]


class Disbursement(TimeStamped):
    """Spending: requested → approved (financial auditor ≠ requester) → paid (accountant ≠ approver)."""
    REQUESTED, APPROVED, REJECTED, PAID, CANCELLED = "requested", "approved", "rejected", "paid", "cancelled"
    initiative = models.ForeignKey("community.Initiative", on_delete=models.PROTECT, related_name="disbursements")
    need = models.ForeignKey("community.Need", null=True, blank=True, on_delete=models.SET_NULL)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    purpose = models.CharField(max_length=300)
    payee_name = models.CharField(max_length=160)
    status = models.CharField(max_length=10, default=REQUESTED, db_index=True,
                              choices=[(REQUESTED, "مطلوب"), (APPROVED, "معتمد"), (REJECTED, "مرفوض"),
                                       (PAID, "مصروف"), (CANCELLED, "ملغى")])
    requested_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=300, blank=True)
    paid_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=80, blank=True)
    receipt = models.ForeignKey("core.MediaAsset", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    public_result = models.CharField(max_length=300, blank=True, help_text="ماذا أنتج هذا الصرف (يُنشر)")

    class Meta:
        ordering = ["-id"]
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="disb_amount_positive")]


class Refund(TimeStamped):
    REQUESTED, APPROVED, PROCESSING, COMPLETED, FAILED, REJECTED = ("requested", "approved", "processing",
                                                                    "completed", "failed", "rejected")
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=300)
    status = models.CharField(max_length=12, default=REQUESTED,
                              choices=[(REQUESTED, "مطلوب"), (APPROVED, "معتمد"), (PROCESSING, "قيد التنفيذ"),
                                       (COMPLETED, "منفذ"), (FAILED, "فشل"), (REJECTED, "مرفوض")])
    requested_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    provider_refund_id = models.CharField(max_length=120, unique=True, null=True, blank=True)
    reference = models.CharField(max_length=80, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="refund_amount_positive")]


class LedgerEntry(models.Model):
    """Append-only, auditable ledger (also protected by a database trigger against UPDATE/DELETE)."""
    COLLECTION, FEE, DISBURSEMENT, REFUND, ADJUSTMENT = "collection", "fee", "disbursement", "refund", "adjustment"
    CREDIT, DEBIT = "credit", "debit"
    initiative = models.ForeignKey("community.Initiative", on_delete=models.PROTECT, related_name="ledger")
    entry_type = models.CharField(max_length=15, choices=[(COLLECTION, "تحصيل"), (FEE, "رسوم"), (DISBURSEMENT, "صرف"),
                                                          (REFUND, "استرداد"), (ADJUSTMENT, "تسوية")])
    direction = models.CharField(max_length=6, choices=[(CREDIT, "دائن"), (DEBIT, "مدين")])
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=LYD)
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger")
    disbursement = models.ForeignKey(Disbursement, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger")
    refund = models.ForeignKey(Refund, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger")
    memo = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_simulated = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="ledger_amount_positive"),
            # A payment can only be collected once, a fee charged once, a disbursement paid once, a refund booked once
            models.UniqueConstraint(fields=["payment", "entry_type"], condition=Q(entry_type__in=["collection", "fee"]),
                                    name="uniq_payment_collection"),
            models.UniqueConstraint(fields=["disbursement"], condition=Q(disbursement__isnull=False),
                                    name="uniq_disbursement_entry"),
            models.UniqueConstraint(fields=["refund"], condition=Q(refund__isnull=False), name="uniq_refund_entry"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Ledger entries are immutable; post an adjustment instead.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Ledger entries are immutable.")

    @classmethod
    def balance(cls, initiative):
        agg = cls.objects.filter(initiative=initiative).aggregate(
            c=Sum("amount", filter=Q(direction=cls.CREDIT)), d=Sum("amount", filter=Q(direction=cls.DEBIT)))
        return (agg["c"] or Decimal("0")) - (agg["d"] or Decimal("0"))
