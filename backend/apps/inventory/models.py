from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import DemoFlag, TimeStamped

User = settings.AUTH_USER_MODEL


class Resource(DemoFlag, TimeStamped):
    """مخزن الخير — a stock of an item for donation (consumed on pickup) or loan (returned)."""
    DONATION, LOAN = "donation", "loan"
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=10, choices=[(DONATION, "تبرع"), (LOAN, "إعارة")])
    unit = models.CharField(max_length=30, default="قطعة")
    total_quantity = models.PositiveIntegerField()
    reserved_quantity = models.PositiveIntegerField(default=0)  # reserved, not yet picked up
    out_quantity = models.PositiveIntegerField(default=0)       # picked up (loans: not yet returned)
    consumed_quantity = models.PositiveIntegerField(default=0)  # donations handed over (left the stock)
    condition = models.CharField(max_length=20, default="good",
                                 choices=[("new", "جديد"), ("good", "جيد"), ("fair", "مقبول"), ("needs_repair", "يحتاج صيانة")])
    custodian = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="custody")
    area = models.ForeignKey("geo.Area", null=True, blank=True, on_delete=models.SET_NULL)
    pickup_location = models.CharField(max_length=200)
    initiative = models.ForeignKey("community.Initiative", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="resources")
    max_loan_days = models.PositiveSmallIntegerField(default=7)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-id"]
        constraints = [models.CheckConstraint(
            condition=Q(reserved_quantity__gte=0) & Q(out_quantity__gte=0),
            name="resource_non_negative"),
            models.CheckConstraint(
                condition=Q(total_quantity__gte=models.F("reserved_quantity") + models.F("out_quantity")
                            + models.F("consumed_quantity")),
                name="resource_never_oversubscribed")]

    @property
    def available_quantity(self):
        return self.total_quantity - self.reserved_quantity - self.out_quantity - self.consumed_quantity


class Reservation(TimeStamped):
    RESERVED, CANCELLED, PICKED_UP, RETURNED, OVERDUE = "reserved", "cancelled", "picked_up", "returned", "overdue"
    resource = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name="reservations")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reservations")
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=10, default=RESERVED, db_index=True,
                              choices=[(RESERVED, "محجوز"), (CANCELLED, "ملغى"), (PICKED_UP, "مستلم"),
                                       (RETURNED, "مُرجع"), (OVERDUE, "متأخر الإرجاع")])
    purpose = models.CharField(max_length=300, blank=True)
    pickup_by = models.DateTimeField(null=True, blank=True)
    due_return_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    picked_up_confirmed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    returned_at = models.DateTimeField(null=True, blank=True)
    returned_confirmed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    return_condition = models.CharField(max_length=20, blank=True)
    client_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        constraints = [models.UniqueConstraint(fields=["user", "client_id"], name="uniq_reservation_client")]
