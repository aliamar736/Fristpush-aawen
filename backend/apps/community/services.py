from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, F, Max, Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Role
from apps.accounts.permissions import has_role
from apps.core.audit import audit
from apps.core.config import feature_enabled
from apps.core.exceptions import Conflict, InvalidTransition, ServiceDisabled
from apps.core.models import MediaAsset

from .models import (BudgetCycle, HelpOffer, Initiative, Need, Proposal, ProposalVote, SurplusOffer, Task,
                     TaskBooking, VolunteerProfile)


# ---------- initiatives ----------
def can_manage_initiative(user, ini):
    return ini.manager_id == user.pk or has_role(user, Role.COORDINATOR, area=ini.area_id)


@transaction.atomic
def submit_initiative(user, ini):
    if ini.manager_id != user.pk:
        raise PermissionDenied()
    if ini.status != Initiative.DRAFT:
        raise InvalidTransition("المبادرة ليست مسودة.")
    ini.status = Initiative.PENDING
    ini.save()
    from apps.notifications.services import notify_role
    notify_role(Role.COORDINATOR, "initiative_review", f"مبادرة بانتظار الاعتماد: {ini.title}", "",
                {"initiative_id": ini.pk}, area_id=ini.area_id)
    return ini


@transaction.atomic
def decide_initiative(user, ini, approve, note=""):
    if not has_role(user, Role.COORDINATOR, area=ini.area_id):
        raise PermissionDenied("اعتماد المبادرات للمنسق.")
    if ini.status != Initiative.PENDING:
        raise InvalidTransition("المبادرة ليست بانتظار الاعتماد.")
    if ini.manager_id == user.pk:
        raise PermissionDenied("لا يعتمد مسؤول المبادرة مبادرته.")
    ini.status = Initiative.APPROVED if approve else Initiative.DRAFT
    if approve:
        ini.approved_by, ini.approved_at = user, timezone.now()
    ini.save()
    audit(user, "initiative." + ("approved" if approve else "returned"), ini, note=note)
    from apps.notifications.services import notify
    if ini.manager:
        notify(ini.manager, "initiative", f"مبادرتك «{ini.title}»: " + ("اعتُمدت" if approve else "أُعيدت للتعديل"), note,
               {"initiative_id": ini.pk})
    return ini


def blocking_needs(area_id=None):
    """«شن ناقص؟» — open blocking needs of approved/active initiatives."""
    qs = Need.objects.filter(is_blocking=True, status__in=[Need.OPEN, Need.PARTIAL],
                             initiative__status__in=Initiative.ACCEPTING).select_related("initiative")
    if area_id:
        qs = qs.filter(initiative__area_id=area_id)
    return qs


# ---------- help offers (in-kind / service) ----------
@transaction.atomic
def offer_help(user, need, message, quantity=1, kind="in_kind", organization_name=""):
    if need.initiative.status not in Initiative.ACCEPTING:
        raise Conflict("المبادرة غير معتمدة بعد.")
    if need.status in (Need.MET, Need.CANCELLED):
        raise Conflict("هذا الاحتياج مكتمل.")
    if need.kind == "funding":
        raise ValidationError({"need": "احتياج التمويل يُغطّى عبر «ساهم» بتعهد مالي."})
    return HelpOffer.objects.create(need=need, user=user, message=message[:500], quantity=Decimal(str(quantity)),
                                    kind=kind if kind in ("in_kind", "service") else "in_kind",
                                    organization_name=organization_name[:160])


@transaction.atomic
def decide_offer(user, offer, action):
    """accept (reserve) → fulfil (received) | decline. Separate offer / reservation / receipt."""
    offer = HelpOffer.objects.select_for_update().get(pk=offer.pk)
    need = Need.objects.select_for_update().get(pk=offer.need_id)
    if action == "withdraw":
        if offer.user_id != user.pk or offer.status not in (HelpOffer.OFFERED, HelpOffer.ACCEPTED):
            raise PermissionDenied()
        offer.status = HelpOffer.WITHDRAWN
        offer.save()
        return offer
    if not can_manage_initiative(user, need.initiative):
        raise PermissionDenied()
    if action == "accept" and offer.status == HelpOffer.OFFERED:
        offer.status, offer.decided_by = HelpOffer.ACCEPTED, user
    elif action == "decline" and offer.status in (HelpOffer.OFFERED, HelpOffer.ACCEPTED):
        offer.status, offer.decided_by = HelpOffer.DECLINED, user
    elif action == "receive" and offer.status == HelpOffer.ACCEPTED:
        offer.status, offer.received_by, offer.received_at = HelpOffer.FULFILLED, user, timezone.now()
        need.quantity_fulfilled += offer.quantity
        need.refresh_status()
        need.save()
    else:
        raise InvalidTransition("إجراء غير متاح لهذه الحالة.")
    offer.save()
    return offer


# ---------- tasks («خُذ مهمة») ----------
@transaction.atomic
def book_task(user, task_id):
    task = Task.objects.select_for_update().get(pk=task_id)
    if task.status not in (Task.OPEN, Task.FULL) or task.starts_at < timezone.now():
        raise Conflict("المهمة غير متاحة للحجز.")
    existing = TaskBooking.objects.filter(task=task, user=user).first()
    active = TaskBooking.objects.filter(task=task, status__in=TaskBooking.ACTIVE).count()
    if existing and existing.status in TaskBooking.ACTIVE:
        return existing
    if active >= task.capacity:
        raise Conflict("اكتمل عدد المشاركين.")
    if existing:
        existing.status = TaskBooking.BOOKED
        existing.save()
        booking = existing
    else:
        booking = TaskBooking.objects.create(task=task, user=user)
    if active + 1 >= task.capacity:
        task.status = Task.FULL
        task.save(update_fields=["status"])
    return booking


@transaction.atomic
def cancel_booking(user, booking):
    booking = TaskBooking.objects.select_for_update().get(pk=booking.pk)
    if booking.user_id != user.pk:
        raise PermissionDenied()
    if booking.status != TaskBooking.BOOKED:
        raise InvalidTransition("لا يمكن إلغاء هذا الحجز.")
    booking.status = TaskBooking.CANCELLED
    booking.save()
    task = Task.objects.select_for_update().get(pk=booking.task_id)
    if task.status == Task.FULL:
        task.status = Task.OPEN
        task.save(update_fields=["status"])
    return booking


def _task_manager(user, task):
    return task.owner_id == user.pk or has_role(user, Role.COORDINATOR, area=task.area_id) or (
        task.initiative and task.initiative.manager_id == user.pk)


@transaction.atomic
def mark_attendance(manager, booking, attended):
    if not _task_manager(manager, booking.task):
        raise PermissionDenied("تأكيد الحضور لمسؤول المهمة.")
    if booking.status not in (TaskBooking.BOOKED, TaskBooking.ATTENDED, TaskBooking.NO_SHOW):
        raise InvalidTransition()
    booking.status = TaskBooking.ATTENDED if attended else TaskBooking.NO_SHOW
    booking.attendance_confirmed_by = manager
    booking.save()
    return booking


@transaction.atomic
def complete_booking(user, booking, note, media_ids=()):
    """Volunteer submits completion proof; only allowed after attendance was confirmed."""
    if booking.user_id != user.pk:
        raise PermissionDenied()
    if booking.status != TaskBooking.ATTENDED:
        raise InvalidTransition("يُثبت الإتمام بعد تأكيد الحضور من مسؤول المهمة.")
    booking.status, booking.completion_note = TaskBooking.COMPLETED, note[:500]
    booking.save()
    if media_ids:
        booking.completion_media.set(MediaAsset.objects.filter(uid__in=media_ids, owner=user))
    return booking


def recommend_tasks(user, limit=10, now=None):
    """Matches open future tasks to «مهاراتي»: skills, preferred areas and weekly availability."""
    now = now or timezone.now()
    profile = VolunteerProfile.objects.filter(user=user).first()
    qs = Task.objects.filter(status=Task.OPEN, starts_at__gt=now).exclude(bookings__user=user).select_related("skill")
    if not profile:
        return list(qs[:limit])
    skills = set(profile.skills.values_list("id", flat=True))
    areas = set(profile.preferred_areas.values_list("id", flat=True))
    days = set((profile.availability or {}).get("days", []))
    slots = set((profile.availability or {}).get("slots", []))
    scored = []
    for t in qs[:300]:
        local = timezone.localtime(t.starts_at)
        weekday = (local.weekday() + 2) % 7  # 0 = Saturday
        slot = "morning" if local.hour < 12 else "afternoon" if local.hour < 17 else "evening"
        score = 0
        reasons = []
        if t.skill_id and t.skill_id in skills:
            score += 3
            reasons.append("تطابق مهارة")
        elif t.skill_id and skills:
            score -= 1
        if areas and t.area_id in areas:
            score += 2
            reasons.append("في منطقتك المفضلة")
        if days and weekday in days:
            score += 1
            reasons.append("يوم مناسب")
        if slots and slot in slots:
            score += 1
            reasons.append("وقت مناسب")
        t.match_score, t.match_reasons = score, reasons
        scored.append(t)
    scored.sort(key=lambda t: (-t.match_score, t.starts_at))
    return scored[:limit]


# ---------- proposals & participatory budget ----------
@transaction.atomic
def review_proposal(user, proposal, decision, **fields):
    if not has_role(user, Role.REVIEWER, Role.COORDINATOR, area=proposal.area_id):
        raise PermissionDenied()
    for k in ("feasibility_ok", "permit_ok", "cost_verified", "maintenance_plan", "review_note"):
        if k in fields:
            v = fields[k]
            if k == "cost_verified" and v not in (None, ""):
                try:
                    v = Decimal(str(v))
                except Exception:  # noqa: BLE001
                    raise ValidationError({"cost_verified": "قيمة غير صحيحة."})
            if k in ("feasibility_ok", "permit_ok") and isinstance(v, str):
                v = v.lower() in ("true", "1", "yes")
            setattr(proposal, k, v)
    if decision == "eligible":
        missing = [k for k in ("feasibility_ok", "permit_ok") if getattr(proposal, k) is not True]
        if proposal.cost_verified is None:
            missing.append("cost_verified")
        if not proposal.maintenance_plan.strip():
            missing.append("maintenance_plan")
        if missing:
            raise ValidationError({"missing": missing,
                                   "detail": "لا يُؤهَّل الاقتراح قبل مراجعة الجدوى والإذن والتكلفة والصيانة."})
        if proposal.cycle and proposal.cost_verified > proposal.cycle.budget_amount:
            raise ValidationError({"cost_verified": "التكلفة أكبر من ميزانية الدورة المعلنة."})
    statuses = {"under_review": Proposal.REVIEW, "needs_changes": Proposal.NEEDS_CHANGES,
                "eligible": Proposal.ELIGIBLE, "rejected": Proposal.REJECTED}
    if decision not in statuses:
        raise ValidationError({"decision": "قرار غير صحيح."})
    proposal.status, proposal.reviewed_by = statuses[decision], user
    proposal.save()
    audit(user, "proposal.review", proposal, decision=decision)
    return proposal


@transaction.atomic
def vote_proposal(user, proposal, now=None):
    cycle = proposal.cycle
    if not cycle or not cycle.voting_open(now):
        raise Conflict("التصويت غير مفتوح.")
    if proposal.status != Proposal.ELIGIBLE:
        raise Conflict("يُصوَّت على الاقتراحات المؤهلة فقط.")
    if ProposalVote.objects.filter(proposal=proposal, user=user).exists():
        raise Conflict("صوّتّ لهذا الاقتراح من قبل.")
    # A voter's selection must fit inside the declared budget
    chosen = Proposal.objects.filter(cycle=cycle, votes__user=user)
    total = sum((p.cost_verified or 0 for p in chosen), Decimal("0")) + (proposal.cost_verified or 0)
    if total > cycle.budget_amount:
        raise ValidationError({"budget": f"مجموع تكلفة اختياراتك ({total}) يتجاوز الميزانية المعلنة ({cycle.budget_amount})."})
    try:
        with transaction.atomic():
            ProposalVote.objects.create(proposal=proposal, user=user)
    except IntegrityError:
        raise Conflict("صوّتّ لهذا الاقتراح من قبل.")
    Proposal.objects.filter(pk=proposal.pk).update(votes_count=F("votes_count") + 1)
    return proposal


def cycle_results(cycle):
    """Greedy selection by votes within the declared budget."""
    remaining = cycle.budget_amount
    rows = []
    for p in Proposal.objects.filter(cycle=cycle, status__in=[Proposal.ELIGIBLE, Proposal.SELECTED]).order_by(
            "-votes_count", "cost_verified"):
        fits = (p.cost_verified or 0) <= remaining
        if fits:
            remaining -= p.cost_verified or 0
        rows.append({"id": p.pk, "title": p.title, "votes": p.votes_count, "cost": str(p.cost_verified),
                     "selected": fits})
    return {"budget": str(cycle.budget_amount), "remaining": str(remaining), "proposals": rows}


# ---------- surplus ----------
def create_surplus(user, data):
    if data.get("kind") == "food" and not feature_enabled("surplus_food"):
        raise ServiceDisabled("مشاركة الغذاء غير مفعّلة حتى تجهيز إجراءات السلامة وشريك مناسب.")
    return SurplusOffer.objects.create(owner=user, **data)


@transaction.atomic
def reserve_surplus(user, offer):
    offer = SurplusOffer.objects.select_for_update().get(pk=offer.pk)
    if offer.kind == "food" and not feature_enabled("surplus_food"):
        raise ServiceDisabled("مشاركة الغذاء غير مفعّلة.")
    if offer.owner_id == user.pk:
        raise Conflict("لا يمكنك حجز عرضك.")
    if offer.status != SurplusOffer.AVAILABLE or offer.available_until < timezone.now():
        raise Conflict("العرض لم يعد متاحًا.")
    offer.status, offer.reserved_by, offer.reserved_at = SurplusOffer.RESERVED, user, timezone.now()
    offer.save()
    return offer


@transaction.atomic
def handover_surplus(user, offer, cancel=False):
    offer = SurplusOffer.objects.select_for_update().get(pk=offer.pk)
    if cancel:
        if user.pk not in (offer.owner_id, offer.reserved_by_id) or offer.status != SurplusOffer.RESERVED:
            raise PermissionDenied()
        offer.status, offer.reserved_by, offer.reserved_at = SurplusOffer.AVAILABLE, None, None
    else:
        if offer.owner_id != user.pk:
            raise PermissionDenied("صاحب العرض يؤكد التسليم.")
        if offer.status != SurplusOffer.RESERVED:
            raise InvalidTransition("العرض غير محجوز.")
        offer.status, offer.handed_over_at = SurplusOffer.HANDED_OVER, timezone.now()
    offer.save()
    return offer


# ---------- coverage of low-participation areas ----------
def coverage(now=None):
    from apps.geo.models import Area
    from apps.reports.models import Report
    now = now or timezone.now()
    since = now - timedelta(days=90)
    rows = []
    areas = Area.objects.filter(active=True).annotate(
        reports_90d=Count("reports", filter=Q(reports__submitted_at__gte=since), distinct=True),
        last_report=Max("reports__submitted_at"),
        open_surveys=Count("surveys", filter=Q(surveys__status__in=["assigned", "in_progress"]), distinct=True))
    counts = [a.reports_90d for a in areas]
    median = sorted(counts)[len(counts) // 2] if counts else 0
    for a in areas:
        per_k = (a.reports_90d / a.population * 1000) if a.population else None
        low = a.reports_90d < max(3, median * 0.4)
        rows.append({"area_id": a.pk, "area": a.name_ar, "population": a.population, "reports_90d": a.reports_90d,
                     "reports_per_1000": round(per_k, 2) if per_k is not None else None,
                     "last_report_at": a.last_report, "open_surveys": a.open_surveys, "low_participation": low,
                     "boundary_source": a.boundary_source})
    rows.sort(key=lambda r: (not r["low_participation"], r["reports_90d"]))
    return {"median_reports_90d": median, "areas": rows,
            "note": "قلة البلاغات قد تعني نقص المشاركة لا قلة المشاكل؛ استخدم المسح الميداني للتحقق."}
