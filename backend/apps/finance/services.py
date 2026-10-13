"""Finance operations. Rules:
- pledge ≠ payment; transfer screenshot ≠ payment until an accountant matches it;
- webhook events are de-duplicated by (provider, event_id) and ledger uniqueness;
- disbursement: requester → financial auditor (≠ requester) approves → accountant (≠ approver) pays;
- refunds: accountant requests → financial auditor approves → executed via provider / bank;
- no person-to-person wallets: money only flows into approved initiatives and out to documented payees.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Role
from apps.accounts.permissions import has_role
from apps.community.models import Initiative
from apps.core.audit import audit
from apps.core.exceptions import Conflict, InvalidTransition

from .models import Disbursement, LedgerEntry, Payment, Pledge, ProviderEvent, Refund, TransferProof
from .providers import get_provider

D = Decimal


def money(v):
    try:
        d = D(str(v)).quantize(D("0.01"), rounding=ROUND_HALF_UP)
    except Exception:  # noqa: BLE001
        raise ValidationError({"amount": "مبلغ غير صحيح."})
    if d <= 0:
        raise ValidationError({"amount": "المبلغ يجب أن يكون أكبر من صفر."})
    if d > D("1000000"):
        raise ValidationError({"amount": "المبلغ أكبر من الحد المسموح."})
    return d


def _receipt_number(payment):
    return f"RC-{timezone.now():%Y}-{payment.pk:07d}"


@transaction.atomic
def create_pledge(user, initiative_id, amount, method="online", need_id=None, organization_name="",
                  is_anonymous=True, client_id=None):
    if client_id:
        existing = Pledge.objects.filter(contributor=user, client_id=client_id).first()
        if existing:
            return existing, False
    ini = Initiative.objects.get(pk=initiative_id)
    if ini.status not in Initiative.ACCEPTING:
        raise Conflict("هذه المبادرة غير معتمدة لاستقبال المساهمات.")
    if need_id and not ini.needs.filter(pk=need_id).exists():
        raise ValidationError({"need": "الاحتياج لا يتبع هذه المبادرة."})
    if method not in ("online", "bank_transfer", "cash"):
        raise ValidationError({"method": "طريقة غير صحيحة."})
    p = Pledge.objects.create(initiative=ini, need_id=need_id, contributor=user, amount=money(amount), method=method,
                              organization_name=organization_name[:160], is_corporate=bool(organization_name),
                              is_anonymous=is_anonymous, client_id=client_id)
    return p, True


@transaction.atomic
def cancel_pledge(user, pledge):
    pledge = Pledge.objects.select_for_update().get(pk=pledge.pk)
    if pledge.contributor_id != user.pk:
        raise PermissionDenied()
    if pledge.status not in (Pledge.PLEDGED, Pledge.AWAITING):
        raise InvalidTransition("لا يمكن إلغاء تعهد مدفوع؛ اطلب الاسترداد.")
    if pledge.payments.filter(status=Payment.SUCCEEDED).exists():
        raise InvalidTransition("توجد دفعة مؤكدة.")
    pledge.status = Pledge.CANCELLED
    pledge.save()
    return pledge


@transaction.atomic
def start_online_payment(user, pledge):
    pledge = Pledge.objects.select_for_update().get(pk=pledge.pk)
    if pledge.contributor_id != user.pk:
        raise PermissionDenied()
    if pledge.status not in (Pledge.PLEDGED, Pledge.AWAITING):
        raise InvalidTransition("هذا التعهد لا يقبل الدفع.")
    if pledge.initiative.status not in Initiative.ACCEPTING:
        raise Conflict("المبادرة لم تعد تستقبل مساهمات.")
    provider = get_provider()  # raises ServiceDisabled when real collection is not configured/authorised
    open_payment = pledge.payments.filter(status=Payment.INITIATED, provider=provider.name).first()
    if open_payment:
        return open_payment
    payment = Payment.objects.create(pledge=pledge, provider=provider.name, amount=pledge.amount,
                                     is_simulated=provider.simulated)
    out = provider.create_checkout(payment)
    payment.provider_payment_id = out["provider_payment_id"]
    payment.checkout_url = out["checkout_url"]
    payment.save()
    pledge.status = Pledge.AWAITING
    pledge.method = "online"
    pledge.save()
    return payment


def _book_collection(payment, fee, actor=None):
    ini = payment.pledge.initiative
    LedgerEntry.objects.create(initiative=ini, entry_type=LedgerEntry.COLLECTION, direction=LedgerEntry.CREDIT,
                               amount=payment.amount, payment=payment, created_by=actor,
                               memo=f"تحصيل {payment.receipt_number}", is_simulated=payment.is_simulated)
    if fee and fee > 0:
        LedgerEntry.objects.create(initiative=ini, entry_type=LedgerEntry.FEE, direction=LedgerEntry.DEBIT,
                                   amount=fee, payment=payment, created_by=actor, memo="رسوم مزود الدفع",
                                   is_simulated=payment.is_simulated)


def handle_webhook(provider_name, body: bytes, headers):
    """Entry point for provider webhooks. Returns a short result string. Safe to call repeatedly."""
    provider = get_provider(provider_name)
    try:
        ev = provider.verify_and_parse(body, headers)
    except (PermissionError, KeyError, ValueError):
        raise PermissionDenied("توقيع غير صالح.")
    import json
    with transaction.atomic():
        record, created = ProviderEvent.objects.select_for_update().get_or_create(
            provider=provider.name, event_id=ev["event_id"],
            defaults={"type": ev["type"], "payload": json.loads(body)})
        if not created:
            record.deliveries += 1
            record.save(update_fields=["deliveries"])
            if record.processed_at:
                return "duplicate"
        result = _apply_event(provider, ev)
        record.processed_at = timezone.now()
        record.result = result[:200]
        record.save(update_fields=["processed_at", "result"])
        return result


def _apply_event(provider, ev):
    payment = Payment.objects.select_for_update().filter(provider=provider.name,
                                                         provider_payment_id=ev["payment_id"]).first()
    if payment is None:
        return "unknown_payment"
    pledge = Pledge.objects.select_for_update().get(pk=payment.pledge_id)
    t = ev["type"]
    if t == "payment.succeeded":
        if payment.status in (Payment.SUCCEEDED, Payment.REFUNDED, Payment.PARTIAL_REFUND):
            return "already_succeeded"
        amount = D(str(ev["amount"])) if ev.get("amount") is not None else None
        if amount != payment.amount:
            payment.status = Payment.REVIEW
            payment.failure_reason = f"المبلغ المبلّغ ({amount}) لا يطابق المبلغ المطلوب ({payment.amount})"
            payment.save()
            return "amount_mismatch"
        fee = D(str(ev.get("fee") or "0"))
        payment.status, payment.fee, payment.confirmed_at = Payment.SUCCEEDED, fee, timezone.now()
        payment.receipt_number = _receipt_number(payment)
        payment.save()
        pledge.status = Pledge.PAID
        pledge.save()
        _book_collection(payment, fee)
        _notify_payment(payment, "تم تأكيد مساهمتك", f"إيصال {payment.receipt_number}")
        return "succeeded"
    if t == "payment.failed":
        if payment.status != Payment.INITIATED:
            return f"ignored_failed_in_{payment.status}"
        payment.status, payment.failure_reason = Payment.FAILED, (ev.get("reason") or "")[:300]
        payment.save()
        pledge.status = Pledge.PLEDGED  # the pledge stays; contributor may retry or cancel
        pledge.save()
        _notify_payment(payment, "لم تكتمل عملية الدفع", "لم يُخصم أي مبلغ مؤكد. يمكنك المحاولة مرة أخرى.")
        return "failed"
    if t == "refund.succeeded":
        refund = Refund.objects.select_for_update().filter(provider_refund_id=ev.get("refund_id")).first()
        if refund is None:
            return "unknown_refund"
        if refund.status == Refund.COMPLETED:
            return "already_refunded"
        _complete_refund(refund, payment, None)
        return "refunded"
    return "ignored_type"


def _complete_refund(refund, payment, actor, reference=""):
    refund.status, refund.completed_at = Refund.COMPLETED, timezone.now()
    if reference:
        refund.reference = reference
    refund.save()
    payment.refunded_amount += refund.amount
    payment.status = Payment.REFUNDED if payment.refunded_amount >= payment.amount else Payment.PARTIAL_REFUND
    payment.save()
    if payment.status == Payment.REFUNDED:
        Pledge.objects.filter(pk=payment.pledge_id).update(status=Pledge.REFUNDED)
    LedgerEntry.objects.create(initiative=payment.pledge.initiative, entry_type=LedgerEntry.REFUND,
                               direction=LedgerEntry.DEBIT, amount=refund.amount, payment=payment, refund=refund,
                               created_by=actor, memo=f"استرداد: {refund.reason}"[:300],
                               is_simulated=payment.is_simulated)
    _notify_payment(payment, "تم الاسترداد", f"استُرد {refund.amount} د.ل")


def _notify_payment(payment, title, body):
    from apps.notifications.services import notify
    if payment.pledge.contributor:
        notify(payment.pledge.contributor, "payment", title, body, {"pledge_id": payment.pledge_id})


# ---------- bank transfers (manual reconciliation) ----------
@transaction.atomic
def upload_transfer_proof(user, pledge, asset, claimed_reference=""):
    if pledge.contributor_id != user.pk:
        raise PermissionDenied()
    if pledge.status in (Pledge.PAID, Pledge.CANCELLED, Pledge.REFUNDED):
        raise InvalidTransition("هذا التعهد لا يقبل إثبات تحويل.")
    if asset.owner_id != user.pk:
        raise PermissionDenied()
    proof = TransferProof.objects.create(pledge=pledge, asset=asset, uploaded_by=user,
                                         claimed_reference=claimed_reference[:80])
    pledge.status, pledge.method = Pledge.AWAITING, "bank_transfer"
    pledge.save()
    return proof


@transaction.atomic
def match_transfer(accountant, proof, bank_reference, amount, matched=True, note=""):
    if not has_role(accountant, Role.ACCOUNTANT, any_scope=True):
        raise PermissionDenied("المطابقة للمحاسب فقط.")
    proof = TransferProof.objects.select_for_update().get(pk=proof.pk)
    if proof.status != TransferProof.PENDING:
        raise Conflict("تمت معالجة هذا الإثبات.")
    if proof.uploaded_by_id == accountant.pk:
        raise PermissionDenied("لا يمكن مطابقة تحويل قدمته بنفسك.")
    if not matched:
        proof.status, proof.matched_by, proof.matched_at, proof.note = (TransferProof.REJECTED, accountant,
                                                                       timezone.now(), note[:300])
        proof.save()
        Pledge.objects.filter(pk=proof.pledge_id).update(status=Pledge.PLEDGED)
        audit(accountant, "finance.transfer_rejected", proof, note=note)
        return proof
    if not bank_reference.strip():
        raise ValidationError({"bank_reference": "رقم العملية من كشف الحساب مطلوب."})
    amount = money(amount)
    pledge = Pledge.objects.select_for_update().get(pk=proof.pledge_id)
    pid = f"bank:{bank_reference.strip()}"
    try:
        with transaction.atomic():
            payment = Payment.objects.create(pledge=pledge, provider="bank_transfer", provider_payment_id=pid,
                                             amount=amount, status=Payment.SUCCEEDED, confirmed_at=timezone.now())
    except IntegrityError:
        raise Conflict("رقم العملية المصرفية مستخدم في مطابقة سابقة.")
    payment.receipt_number = _receipt_number(payment)
    payment.save()
    pledge.status = Pledge.PAID
    pledge.save()
    _book_collection(payment, D("0"), accountant)
    proof.status, proof.matched_by, proof.matched_at, proof.payment, proof.note = (
        TransferProof.MATCHED, accountant, timezone.now(), payment, note[:300])
    proof.save()
    audit(accountant, "finance.transfer_matched", proof, amount=str(amount), bank_reference=bank_reference)
    _notify_payment(payment, "تم تأكيد تحويلك", f"إيصال {payment.receipt_number}")
    return proof


# ---------- disbursements ----------
@transaction.atomic
def request_disbursement(user, initiative, amount, purpose, payee_name, need_id=None):
    if not (initiative.manager_id == user.pk or has_role(user, Role.ACCOUNTANT, any_scope=True)):
        raise PermissionDenied("طلب الصرف لمسؤول المبادرة أو المحاسب.")
    if not purpose.strip() or not payee_name.strip():
        raise ValidationError({"purpose": "الغرض والمستفيد مطلوبان."})
    d = Disbursement.objects.create(initiative=initiative, amount=money(amount), purpose=purpose[:300],
                                    payee_name=payee_name[:160], requested_by=user, need_id=need_id)
    audit(user, "finance.disbursement_requested", d, amount=str(d.amount))
    return d


@transaction.atomic
def decide_disbursement(auditor, disb, approve, note=""):
    disb = Disbursement.objects.select_for_update().get(pk=disb.pk)
    if not has_role(auditor, Role.FINANCIAL_AUDITOR, any_scope=True):
        raise PermissionDenied("اعتماد الصرف للمراجع المالي فقط.")
    if disb.requested_by_id == auditor.pk:
        raise PermissionDenied("لا يمكن اعتماد طلب صرف قدمته بنفسك.")
    if disb.status != Disbursement.REQUESTED:
        raise InvalidTransition("الطلب ليس بانتظار الاعتماد.")
    if not approve and not note.strip():
        raise ValidationError({"note": "اذكر سبب الرفض."})
    disb.status = Disbursement.APPROVED if approve else Disbursement.REJECTED
    disb.approved_by, disb.approved_at, disb.decision_note = auditor, timezone.now(), note[:300]
    disb.save()
    audit(auditor, "finance.disbursement_" + ("approved" if approve else "rejected"), disb, note=note)
    return disb


@transaction.atomic
def pay_disbursement(accountant, disb, payment_reference, receipt_asset, public_result=""):
    disb = Disbursement.objects.select_for_update().get(pk=disb.pk)
    if not has_role(accountant, Role.ACCOUNTANT, any_scope=True):
        raise PermissionDenied("تنفيذ الصرف للمحاسب فقط.")
    if accountant.pk in (disb.approved_by_id,):
        raise PermissionDenied("من اعتمد الصرف لا ينفذه.")
    if disb.status != Disbursement.APPROVED:
        raise InvalidTransition("لا يمكن الصرف قبل الاعتماد.")
    if receipt_asset is None:
        raise ValidationError({"receipt": "أرفق إيصال/فاتورة الصرف."})
    if not payment_reference.strip():
        raise ValidationError({"payment_reference": "رقم مرجع الصرف مطلوب."})
    Initiative.objects.select_for_update().get(pk=disb.initiative_id)  # serialise spending per initiative
    balance = LedgerEntry.balance(disb.initiative)
    if balance < disb.amount:
        raise Conflict(f"الرصيد المتاح ({balance}) أقل من مبلغ الصرف.")
    disb.status, disb.paid_by, disb.paid_at = Disbursement.PAID, accountant, timezone.now()
    disb.payment_reference, disb.receipt, disb.public_result = payment_reference[:80], receipt_asset, public_result[:300]
    disb.save()
    LedgerEntry.objects.create(initiative=disb.initiative, entry_type=LedgerEntry.DISBURSEMENT,
                               direction=LedgerEntry.DEBIT, amount=disb.amount, disbursement=disb,
                               created_by=accountant, memo=f"صرف: {disb.purpose}"[:300])
    audit(accountant, "finance.disbursement_paid", disb, amount=str(disb.amount), ref=payment_reference)
    return disb


# ---------- refunds ----------
@transaction.atomic
def request_refund(accountant, payment, amount, reason):
    if not has_role(accountant, Role.ACCOUNTANT, any_scope=True):
        raise PermissionDenied("طلب الاسترداد للمحاسب.")
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status not in (Payment.SUCCEEDED, Payment.PARTIAL_REFUND):
        raise InvalidTransition("لا يمكن استرداد دفعة غير مؤكدة.")
    amount = money(amount)
    pending = sum((r.amount for r in payment.refunds.exclude(status__in=[Refund.REJECTED, Refund.FAILED, Refund.COMPLETED])), D("0"))
    if amount + pending + payment.refunded_amount > payment.amount:
        raise ValidationError({"amount": "مبلغ الاسترداد أكبر من المتبقي من الدفعة."})
    if not reason.strip():
        raise ValidationError({"reason": "سبب الاسترداد مطلوب."})
    r = Refund.objects.create(payment=payment, amount=amount, reason=reason[:300], requested_by=accountant)
    audit(accountant, "finance.refund_requested", r, amount=str(amount))
    return r


@transaction.atomic
def approve_refund(auditor, refund, approve=True, note=""):
    refund = Refund.objects.select_for_update().get(pk=refund.pk)
    if not has_role(auditor, Role.FINANCIAL_AUDITOR, any_scope=True) or refund.requested_by_id == auditor.pk:
        raise PermissionDenied("اعتماد الاسترداد لمراجع مالي غير طالب الاسترداد.")
    if refund.status != Refund.REQUESTED:
        raise InvalidTransition("الطلب ليس بانتظار الاعتماد.")
    if not approve:
        refund.status = Refund.REJECTED
        refund.save()
        audit(auditor, "finance.refund_rejected", refund, note=note)
        return refund
    refund.status, refund.approved_by = Refund.APPROVED, auditor
    refund.save()
    payment = refund.payment
    if payment.provider in ("bank_transfer", "cash"):
        audit(auditor, "finance.refund_approved", refund)
        return refund  # executed manually by the accountant with a bank reference
    provider = get_provider(payment.provider)
    refund.status = Refund.PROCESSING
    refund.save()
    refund.provider_refund_id = provider.refund(payment, refund)
    refund.save(update_fields=["provider_refund_id", "status", "updated_at"])
    audit(auditor, "finance.refund_approved", refund)
    transaction.on_commit(lambda: provider.after_refund_requested(payment, refund))
    return refund


@transaction.atomic
def complete_manual_refund(accountant, refund, reference):
    refund = Refund.objects.select_for_update().get(pk=refund.pk)
    if not has_role(accountant, Role.ACCOUNTANT, any_scope=True):
        raise PermissionDenied()
    if refund.status != Refund.APPROVED or refund.payment.provider not in ("bank_transfer", "cash"):
        raise InvalidTransition("الاسترداد اليدوي متاح للتحويلات المعتمدة فقط.")
    if not reference.strip():
        raise ValidationError({"reference": "مرجع الاسترداد مطلوب."})
    payment = Payment.objects.select_for_update().get(pk=refund.payment_id)
    _complete_refund(refund, payment, accountant, reference)
    audit(accountant, "finance.refund_completed", refund, reference=reference)
    return refund


def initiative_summary(ini):
    from django.db.models import Q, Sum
    led = LedgerEntry.objects.filter(initiative=ini)
    def s(**f):
        return led.filter(**f).aggregate(t=Sum("amount"))["t"] or D("0")
    pledged = Pledge.objects.filter(initiative=ini).exclude(status__in=[Pledge.CANCELLED, Pledge.EXPIRED]).aggregate(
        t=Sum("amount"))["t"] or D("0")
    return {
        "funding_target": str(ini.funding_target),
        "pledged_total": str(pledged),
        "collected": str(s(entry_type=LedgerEntry.COLLECTION)),
        "fees": str(s(entry_type=LedgerEntry.FEE)),
        "disbursed": str(s(entry_type=LedgerEntry.DISBURSEMENT)),
        "refunded": str(s(entry_type=LedgerEntry.REFUND)),
        "balance": str(LedgerEntry.balance(ini)),
        "simulated_entries": led.filter(is_simulated=True).count(),
        "contributors": Pledge.objects.filter(initiative=ini, status=Pledge.PAID).values("contributor").distinct().count(),
        "corporate_contributors": Pledge.objects.filter(Q(initiative=ini, status=Pledge.PAID, is_corporate=True))
        .values_list("organization_name", flat=True).distinct().count(),
    }


def reconciliation_report():
    """Checks invariants: each succeeded payment has exactly one collection entry; ledger totals match."""
    from django.db.models import Count, Q, Sum
    problems = []
    for p in Payment.objects.filter(status__in=[Payment.SUCCEEDED, Payment.REFUNDED, Payment.PARTIAL_REFUND]).annotate(
            n=Count("ledger", filter=Q(ledger__entry_type="collection"))):
        if p.n != 1:
            problems.append({"payment": p.pk, "issue": f"collection entries = {p.n}"})
    orphan = LedgerEntry.objects.filter(entry_type=LedgerEntry.COLLECTION).exclude(
        payment__status__in=[Payment.SUCCEEDED, Payment.REFUNDED, Payment.PARTIAL_REFUND])
    for e in orphan:
        problems.append({"ledger": e.pk, "issue": "collection for unconfirmed payment"})
    paid_total = Payment.objects.filter(status__in=[Payment.SUCCEEDED, Payment.REFUNDED, Payment.PARTIAL_REFUND]
                                        ).aggregate(t=Sum("amount"))["t"] or D("0")
    coll_total = LedgerEntry.objects.filter(entry_type="collection").aggregate(t=Sum("amount"))["t"] or D("0")
    return {
        "ok": not problems and paid_total == coll_total,
        "payments_confirmed_total": str(paid_total),
        "ledger_collections_total": str(coll_total),
        "pending_transfer_proofs": TransferProof.objects.filter(status=TransferProof.PENDING).count(),
        "payments_needing_review": Payment.objects.filter(status=Payment.REVIEW).count(),
        "duplicate_webhook_deliveries": ProviderEvent.objects.filter(deliveries__gt=1).count(),
        "problems": problems,
        "mode": settings.PAYMENTS_MODE,
    }
