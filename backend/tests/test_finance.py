"""Section 12: payment failure, duplicate webhook deliveries, refunds; ledger & separation of duties."""
import json
import uuid
from decimal import Decimal

import pytest
from django.db import connection, transaction
from django.db.utils import DatabaseError

from apps.community.models import Initiative
from apps.core.exceptions import ServiceDisabled
from apps.finance import services
from apps.finance.models import LedgerEntry, Payment, Pledge, ProviderEvent
from apps.finance.providers import SimulatorProvider, get_provider


@pytest.fixture
def ini(ref, users):
    return Initiative.objects.create(title="تشجير", summary="س", area=ref["west"], manager=users["manager"],
                                     status=Initiative.ACTIVE, funding_target=5000)


def pledge(api, user, ini, amount="250.00", **kw):
    r = api.as_(user).post("/api/v1/pledges/", {"initiative": ini.pk, "amount": amount, "client_id": str(uuid.uuid4()),
                                                **kw}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def webhook(api, body, headers):
    return api.as_(None).post("/api/v1/finance/webhooks/simulator", data=body, content_type="application/json",
                              **{"HTTP_" + k.upper().replace("-", "_"): v for k, v in headers.items()})


@pytest.mark.django_db
def test_pledge_is_not_a_payment_and_needs_approved_initiative(api, ref, users, ini):
    p = pledge(api, users["citizen"], ini)
    assert p["status"] == "pledged"
    assert LedgerEntry.balance(ini) == 0
    draft = Initiative.objects.create(title="د", summary="د", manager=users["manager"], status=Initiative.PENDING)
    r = api.as_(users["citizen"]).post("/api/v1/pledges/", {"initiative": draft.pk, "amount": "10"}, format="json")
    assert r.status_code == 409
    assert api.as_(users["citizen"]).post("/api/v1/pledges/", {"initiative": ini.pk, "amount": "-5"},
                                          format="json").status_code == 400


@pytest.mark.django_db
def test_payment_success_with_duplicate_webhooks_books_once(api, ref, users, ini, settings):
    settings.PLATFORM_FEE_PERCENT = 2.0
    p = pledge(api, users["citizen"], ini, "100.00")
    pay = api.as_(users["citizen"]).post(f"/api/v1/pledges/{p['id']}/pay/").json()
    assert pay["is_simulated"] and pay["status"] == "initiated"
    body, headers = SimulatorProvider.build_event("payment.succeeded", pay["provider_payment_id"], "100.00", "2.00",
                                                  event_id="evt_same")
    results = [webhook(api, body, headers).json()["result"] for _ in range(3)]       # provider retries
    assert results == ["succeeded", "duplicate", "duplicate"]
    # a *different* event id for the same payment must not double-book either
    body2, h2 = SimulatorProvider.build_event("payment.succeeded", pay["provider_payment_id"], "100.00", "2.00")
    assert webhook(api, body2, h2).json()["result"] == "already_succeeded"
    assert LedgerEntry.objects.filter(entry_type="collection").count() == 1
    assert LedgerEntry.balance(ini) == Decimal("98.00")
    assert ProviderEvent.objects.get(event_id="evt_same").deliveries == 3
    payment = Payment.objects.get(pk=pay["id"])
    assert payment.status == "succeeded" and payment.receipt_number.startswith("RC-")
    assert Pledge.objects.get(pk=p["id"]).status == "paid"
    rec = api.as_(users["accountant"]).get("/api/v1/finance/reconciliation").json()
    assert rec["ok"] and rec["duplicate_webhook_deliveries"] >= 1


@pytest.mark.django_db
def test_bad_signature_and_amount_mismatch(api, ref, users, ini):
    p = pledge(api, users["citizen"], ini, "100.00")
    pay = api.as_(users["citizen"]).post(f"/api/v1/pledges/{p['id']}/pay/").json()
    body, headers = SimulatorProvider.build_event("payment.succeeded", pay["provider_payment_id"], "100.00")
    assert webhook(api, body, {"X-Simulator-Signature": "forged"}).status_code == 403
    body, headers = SimulatorProvider.build_event("payment.succeeded", pay["provider_payment_id"], "1.00")
    assert webhook(api, body, headers).json()["result"] == "amount_mismatch"
    assert Payment.objects.get(pk=pay["id"]).status == "needs_review"
    assert LedgerEntry.objects.count() == 0


@pytest.mark.django_db
def test_payment_failure_keeps_pledge_and_allows_retry(api, ref, users, ini):
    p = pledge(api, users["citizen"], ini, "50.00")
    pay = api.as_(users["citizen"]).post(f"/api/v1/pledges/{p['id']}/pay/").json()
    r = api.as_(users["citizen"]).post(f"/api/v1/finance/simulator/{pay['provider_payment_id']}",
                                       {"outcome": "failure", "deliveries": 2}, format="json").json()
    assert r["results"] == ["failed", "duplicate"] or r["results"][0] == "failed"
    assert Payment.objects.get(pk=pay["id"]).status == "failed"
    assert Pledge.objects.get(pk=p["id"]).status == "pledged"
    assert LedgerEntry.objects.count() == 0
    # late success for a failed payment is not applied silently
    body, headers = SimulatorProvider.build_event("payment.succeeded", pay["provider_payment_id"], "50.00")
    # (failed payment ⇒ a new attempt is required)
    pay2 = api.as_(users["citizen"]).post(f"/api/v1/pledges/{p['id']}/pay/").json()
    assert pay2["id"] != pay["id"]
    r = api.as_(users["citizen"]).post(f"/api/v1/finance/simulator/{pay2['provider_payment_id']}",
                                       {"outcome": "success"}, format="json").json()
    assert r["results"] == ["succeeded"]
    assert LedgerEntry.balance(ini) == Decimal("50.00")
    # other users cannot drive someone else's simulator checkout
    assert api.as_(users["citizen2"]).post(f"/api/v1/finance/simulator/{pay2['provider_payment_id']}",
                                           {"outcome": "success"}, format="json").status_code == 403


@pytest.mark.django_db
def test_refund_flow_approval_and_duplicate_refund_webhook(api, ref, users, ini):
    p = pledge(api, users["citizen"], ini, "80.00")
    pay = api.as_(users["citizen"]).post(f"/api/v1/pledges/{p['id']}/pay/").json()
    api.as_(users["citizen"]).post(f"/api/v1/finance/simulator/{pay['provider_payment_id']}", {"outcome": "success"},
                                   format="json")
    acc, aud = api.as_(users["accountant"]), api.as_(users["auditor"])
    assert api.as_(users["citizen"]).post("/api/v1/finance/refunds/", {"payment": pay["id"], "amount": "30",
                                                                       "reason": "x"}, format="json").status_code == 403
    assert acc.post("/api/v1/finance/refunds/", {"payment": pay["id"], "amount": "100", "reason": "طلب المساهم"},
                    format="json").status_code == 400                               # more than paid
    rf = acc.post("/api/v1/finance/refunds/", {"payment": pay["id"], "amount": "30", "reason": "طلب المساهم"},
                  format="json").json()
    assert acc.post(f"/api/v1/finance/refunds/{rf['id']}/approve/", {}, format="json").status_code == 403  # SoD
    out = aud.post(f"/api/v1/finance/refunds/{rf['id']}/approve/", {}, format="json").json()
    assert out["status"] in ("processing", "completed")  # completed only once the provider webhook arrives
    from apps.finance.models import Refund
    refund = Refund.objects.get(pk=rf["id"])
    assert refund.status == "completed"             # simulator delivered the signed refund webhook (eager task)
    body, headers = SimulatorProvider.build_event("refund.succeeded", pay["provider_payment_id"], "30.00",
                                                  refund_id=refund.provider_refund_id)
    assert webhook(api, body, headers).json()["result"] == "already_refunded"
    assert LedgerEntry.objects.filter(entry_type="refund").count() == 1
    assert LedgerEntry.balance(ini) == Decimal("50.00")
    assert Payment.objects.get(pk=pay["id"]).status == "partially_refunded"


@pytest.mark.django_db
def test_transfer_screenshot_is_not_payment_until_matched(api, ref, users, ini, upload):
    p = pledge(api, users["citizen"], ini, "300.00", method="bank_transfer")
    m = upload(users["citizen"])
    r = api.as_(users["citizen"]).post(f"/api/v1/pledges/{p['id']}/transfer-proof/", {"media": m,
                                                                                     "claimed_reference": "TRX1"},
                                       format="json")
    assert r.status_code == 201 and "لا تُعد الدفعة مؤكدة" in r.json()["message"]
    assert LedgerEntry.balance(ini) == 0 and Pledge.objects.get(pk=p["id"]).status == "awaiting_payment"
    proofs = api.as_(users["accountant"]).get("/api/v1/finance/transfer-proofs/").json()
    pid = proofs[0]["id"]
    assert api.as_(users["citizen"]).post(f"/api/v1/finance/transfer-proofs/{pid}/match/").status_code == 403
    r = api.as_(users["accountant"]).post(f"/api/v1/finance/transfer-proofs/{pid}/match/",
                                          {"bank_reference": "BNK-77", "amount": "300.00"}, format="json")
    assert r.json()["status"] == "matched"
    assert LedgerEntry.balance(ini) == Decimal("300.00")
    # the same bank reference cannot be matched twice
    p2 = pledge(api, users["citizen2"], ini, "300.00", method="bank_transfer")
    api.as_(users["citizen2"]).post(f"/api/v1/pledges/{p2['id']}/transfer-proof/", {"media": upload(users["citizen2"])},
                                    format="json")
    pid2 = [x for x in api.as_(users["accountant"]).get("/api/v1/finance/transfer-proofs/").json()][0]["id"]
    r = api.as_(users["accountant"]).post(f"/api/v1/finance/transfer-proofs/{pid2}/match/",
                                          {"bank_reference": "BNK-77", "amount": "300.00"}, format="json")
    assert r.status_code == 409


@pytest.mark.django_db
def test_disbursement_separation_of_duties_and_balance(api, ref, users, ini, upload):
    p = pledge(api, users["citizen"], ini, "500.00")
    pay = api.as_(users["citizen"]).post(f"/api/v1/pledges/{p['id']}/pay/").json()
    api.as_(users["citizen"]).post(f"/api/v1/finance/simulator/{pay['provider_payment_id']}", {"outcome": "success"},
                                   format="json")
    mgr = api.as_(users["manager"])
    assert api.as_(users["citizen"]).post("/api/v1/finance/disbursements/", {"initiative": ini.pk, "amount": "100",
                                                                             "purpose": "x", "payee_name": "y"},
                                          format="json").status_code == 403
    d = mgr.post("/api/v1/finance/disbursements/", {"initiative": ini.pk, "amount": "400", "purpose": "شراء شتلات",
                                                     "payee_name": "مشتل الربيع"}, format="json").json()
    acc = api.as_(users["accountant"])
    # cannot pay before approval; accountant cannot approve
    assert acc.post(f"/api/v1/finance/disbursements/{d['id']}/pay/", {"payment_reference": "1"}, format="json").status_code == 409
    assert acc.post(f"/api/v1/finance/disbursements/{d['id']}/decide/", {"approve": True}, format="json").status_code == 403
    assert api.as_(users["auditor"]).post(f"/api/v1/finance/disbursements/{d['id']}/decide/", {"approve": True},
                                          format="json").json()["status"] == "approved"
    # receipt required
    assert acc.post(f"/api/v1/finance/disbursements/{d['id']}/pay/", {"payment_reference": "CHQ-1"},
                    format="json").status_code == 400
    rec = upload(users["accountant"])
    out = acc.post(f"/api/v1/finance/disbursements/{d['id']}/pay/", {"payment_reference": "CHQ-1", "receipt": rec,
                                                                    "public_result": "زُرعت 30 شجرة"}, format="json")
    assert out.json()["status"] == "paid"
    assert LedgerEntry.balance(ini) == Decimal("100.00")
    # over-spending blocked
    d2 = mgr.post("/api/v1/finance/disbursements/", {"initiative": ini.pk, "amount": "150", "purpose": "x",
                                                      "payee_name": "y"}, format="json").json()
    api.as_(users["auditor"]).post(f"/api/v1/finance/disbursements/{d2['id']}/decide/", {"approve": True}, format="json")
    r = acc.post(f"/api/v1/finance/disbursements/{d2['id']}/pay/", {"payment_reference": "2",
                                                                   "receipt": upload(users["accountant"])}, format="json")
    assert r.status_code == 409
    led = api.as_(None).get(f"/api/v1/initiatives/{ini.pk}/ledger/").json()
    assert led[0]["result"] == "زُرعت 30 شجرة"
    summary = api.as_(None).get(f"/api/v1/initiatives/{ini.pk}/").json()["finance"]
    assert summary["collected"] == "500.00" and summary["disbursed"] == "400.00" and summary["balance"] == "100.00"
    csv_resp = api.as_(users["auditor"]).get("/api/v1/finance/ledger", {"export": "csv"})
    assert csv_resp.status_code == 200 and "disbursement" in csv_resp.content.decode()


@pytest.mark.django_db
def test_requester_cannot_approve_own_disbursement(api, ref, users, ini):
    from apps.accounts.models import Role, RoleAssignment
    RoleAssignment.objects.create(user=users["manager"], role=Role.FINANCIAL_AUDITOR)
    d = api.as_(users["manager"]).post("/api/v1/finance/disbursements/", {"initiative": ini.pk, "amount": "10",
                                                                          "purpose": "x", "payee_name": "y"},
                                       format="json").json()
    assert api.as_(users["manager"]).post(f"/api/v1/finance/disbursements/{d['id']}/decide/", {"approve": True},
                                          format="json").status_code == 403


@pytest.mark.django_db
def test_ledger_is_immutable_at_database_level(ref, users, ini):
    e = LedgerEntry.objects.create(initiative=ini, entry_type="adjustment", direction="credit", amount=Decimal("1"))
    with pytest.raises(ValueError):
        e.save()
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as c:
                c.execute("UPDATE finance_ledgerentry SET amount = 999 WHERE id = %s", [e.pk])


@pytest.mark.django_db
def test_live_payments_disabled_until_configured(api, ref, users, ini, settings):
    settings.PAYMENTS_MODE = "live"
    status = api.as_(None).get("/api/v1/finance/status").json()
    assert status["accepting_real_money"] is False and "PAYMENT_LIVE_AUTHORISED" in status["missing"]
    with pytest.raises(ServiceDisabled):
        get_provider()
    p = pledge(api, users["citizen"], ini)
    assert api.as_(users["citizen"]).post(f"/api/v1/pledges/{p['id']}/pay/").status_code == 503
    settings.PAYMENTS_MODE = "disabled"
    assert api.as_(None).get("/api/v1/finance/status").json()["mode"] == "disabled"
    settings.PAYMENTS_MODE = "simulated"
    settings.IS_PRODUCTION = True
    with pytest.raises(ServiceDisabled):
        get_provider()


@pytest.mark.django_db
def test_no_person_to_person_wallet_endpoints():
    from django.urls import get_resolver
    names = " ".join(str(p.pattern) for p in get_resolver().url_patterns[0].url_patterns)
    assert "wallet" not in names and "transfer-to-user" not in names
