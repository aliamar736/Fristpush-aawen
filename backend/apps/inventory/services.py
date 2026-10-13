"""Stock operations. Every quantity change locks the Resource row (SELECT … FOR UPDATE) so two people
racing for the last unit can never both get it."""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Role
from apps.accounts.permissions import has_role
from apps.core.audit import audit
from apps.core.exceptions import Conflict, InvalidTransition

from .models import Reservation, Resource


def _can_manage(user, resource):
    return resource.custodian_id == user.pk or has_role(user, Role.COORDINATOR, area=resource.area_id)


@transaction.atomic
def reserve(user, resource_id, quantity, purpose="", client_id=None):
    if client_id:
        existing = Reservation.objects.filter(user=user, client_id=client_id).first()
        if existing:
            return existing, False
    quantity = int(quantity)
    if quantity < 1:
        raise ValidationError({"quantity": "الكمية يجب أن تكون 1 أو أكثر."})
    res = Resource.objects.select_for_update().get(pk=resource_id)
    if not res.active:
        raise Conflict("هذا المورد غير متاح حاليًا.")
    if res.available_quantity < quantity:
        raise Conflict(f"الكمية المتاحة الآن {res.available_quantity} فقط.")
    res.reserved_quantity += quantity
    res.save(update_fields=["reserved_quantity", "updated_at"])
    try:
        with transaction.atomic():
            r = Reservation.objects.create(resource=res, user=user, quantity=quantity, purpose=purpose[:300],
                                           client_id=client_id, pickup_by=timezone.now() + timedelta(days=2))
    except IntegrityError:
        transaction.set_rollback(True)
        raise
    return r, True


@transaction.atomic
def cancel(user, reservation_id):
    r = Reservation.objects.select_for_update().get(pk=reservation_id)
    if r.user_id != user.pk and not _can_manage(user, r.resource):
        raise PermissionDenied()
    if r.status != Reservation.RESERVED:
        raise InvalidTransition("يمكن إلغاء الحجز قبل الاستلام فقط.")
    res = Resource.objects.select_for_update().get(pk=r.resource_id)
    res.reserved_quantity -= r.quantity
    res.save(update_fields=["reserved_quantity", "updated_at"])
    r.status = Reservation.CANCELLED
    r.save(update_fields=["status", "updated_at"])
    return r


@transaction.atomic
def confirm_pickup(manager, reservation_id):
    r = Reservation.objects.select_for_update().get(pk=reservation_id)
    res = Resource.objects.select_for_update().get(pk=r.resource_id)
    if not _can_manage(manager, res):
        raise PermissionDenied("تأكيد التسليم من مسؤول الاستلام فقط.")
    if r.status != Reservation.RESERVED:
        raise InvalidTransition("هذا الحجز ليس بانتظار الاستلام.")
    res.reserved_quantity -= r.quantity
    now = timezone.now()
    if res.kind == Resource.LOAN:
        res.out_quantity += r.quantity
        r.due_return_at = now + timedelta(days=res.max_loan_days)
    else:
        res.consumed_quantity += r.quantity
    res.save()
    r.status, r.picked_up_at, r.picked_up_confirmed_by = Reservation.PICKED_UP, now, manager
    r.save()
    audit(manager, "inventory.pickup", r, quantity=r.quantity)
    return r


@transaction.atomic
def confirm_return(manager, reservation_id, condition="good"):
    r = Reservation.objects.select_for_update().get(pk=reservation_id)
    res = Resource.objects.select_for_update().get(pk=r.resource_id)
    if not _can_manage(manager, res):
        raise PermissionDenied("تأكيد الإرجاع من مسؤول الاستلام فقط.")
    if res.kind != Resource.LOAN:
        raise InvalidTransition("موارد التبرع لا تُرجع.")
    if r.status not in (Reservation.PICKED_UP, Reservation.OVERDUE):
        raise InvalidTransition("هذا الحجز ليس مستلمًا.")
    res.out_quantity -= r.quantity
    if condition == "needs_repair":
        res.condition = "needs_repair"
    res.save()
    r.status, r.returned_at, r.returned_confirmed_by = Reservation.RETURNED, timezone.now(), manager
    r.return_condition = condition
    r.save()
    audit(manager, "inventory.return", r, condition=condition)
    return r


def mark_overdue(now=None):
    now = now or timezone.now()
    return Reservation.objects.filter(status=Reservation.PICKED_UP, due_return_at__lt=now).update(
        status=Reservation.OVERDUE)
