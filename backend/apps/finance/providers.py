"""Payment provider connectors.

- SimulatorProvider: explicit development simulator. Signs webhooks with PAYMENT_WEBHOOK_SECRET.
  Every payment it creates is flagged is_simulated=True and shown as «محاكي» in all UIs.
- GenericHttpProvider: connector for a hosted-checkout gateway (contract in docs/INTEGRATIONS.md).
  It needs real credentials and a signed agreement; until then live mode stays disabled.

Real money is accepted ONLY when PAYMENTS_MODE=live AND PAYMENT_LIVE_AUTHORISED AND
PAYMENT_BENEFICIARY_CONFIGURED AND a non-simulator provider with a webhook secret is configured.
"""
import hashlib
import hmac
import json
import urllib.request
import uuid

from django.conf import settings

from apps.core.exceptions import ServiceDisabled


class PaymentProvider:
    name = "base"
    simulated = False

    def create_checkout(self, payment):
        raise NotImplementedError

    def verify_and_parse(self, body: bytes, headers) -> dict:
        """Returns {'event_id','type','payment_id','amount','fee','refund_id','reason'}; raises on bad signature."""
        raise NotImplementedError

    def refund(self, payment, refund):
        raise NotImplementedError

    def after_refund_requested(self, payment, refund):
        """Hook run after the refund id is stored (real gateways confirm later via webhook)."""


def sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class SimulatorProvider(PaymentProvider):
    name = "simulator"
    simulated = True
    header = "X-Simulator-Signature"

    def create_checkout(self, payment):
        pid = f"sim_{uuid.uuid4().hex[:20]}"
        return {"provider_payment_id": pid,
                "checkout_url": f"{settings.PUBLIC_WEB_URL}/contribute/simulator/{pid}"}

    def verify_and_parse(self, body, headers):
        sig = headers.get(self.header, "")
        if not settings.PAYMENT_WEBHOOK_SECRET or not hmac.compare_digest(sig, sign(body, settings.PAYMENT_WEBHOOK_SECRET)):
            raise PermissionError("bad signature")
        data = json.loads(body)
        return {"event_id": data["id"], "type": data["type"], "payment_id": data.get("payment_id"),
                "amount": data.get("amount"), "fee": data.get("fee", "0"), "refund_id": data.get("refund_id"),
                "reason": data.get("reason", "")}

    def refund(self, payment, refund):
        return f"simr_{uuid.uuid4().hex[:20]}"

    def after_refund_requested(self, payment, refund):
        # The simulator confirms refunds asynchronously through a signed webhook (like a real gateway)
        from .tasks import simulator_emit
        simulator_emit.delay({"id": f"evt_{uuid.uuid4().hex}", "type": "refund.succeeded",
                              "payment_id": payment.provider_payment_id, "refund_id": refund.provider_refund_id,
                              "amount": str(refund.amount)})

    @staticmethod
    def build_event(event_type, payment_id, amount=None, fee="0", reason="", event_id=None, refund_id=None):
        body = json.dumps({"id": event_id or f"evt_{uuid.uuid4().hex}", "type": event_type, "payment_id": payment_id,
                           "amount": None if amount is None else str(amount), "fee": str(fee), "reason": reason,
                           "refund_id": refund_id}).encode()
        return body, {SimulatorProvider.header: sign(body, settings.PAYMENT_WEBHOOK_SECRET)}


class GenericHttpProvider(PaymentProvider):
    """Hosted checkout over HTTPS. Endpoint contract documented in docs/INTEGRATIONS.md."""
    name = "generic_http"
    header = "X-Gateway-Signature"

    def _post(self, path, payload):
        req = urllib.request.Request(settings.PAYMENT_HTTP_BASE_URL.rstrip("/") + path, method="POST",
                                     data=json.dumps(payload).encode(),
                                     headers={"Authorization": f"Bearer {settings.PAYMENT_HTTP_API_KEY}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    def create_checkout(self, payment):
        out = self._post("/checkouts", {"amount": str(payment.amount), "currency": payment.pledge.currency,
                                        "reference": f"AAWEN-{payment.pk}",
                                        "return_url": f"{settings.PUBLIC_WEB_URL}/me/contributions"})
        return {"provider_payment_id": out["id"], "checkout_url": out["url"]}

    def verify_and_parse(self, body, headers):
        sig = headers.get(self.header, "")
        if not hmac.compare_digest(sig, sign(body, settings.PAYMENT_WEBHOOK_SECRET)):
            raise PermissionError("bad signature")
        d = json.loads(body)
        return {"event_id": d["event_id"], "type": d["type"], "payment_id": d.get("checkout_id"),
                "amount": d.get("amount"), "fee": d.get("fee", "0"), "refund_id": d.get("refund_id"),
                "reason": d.get("failure_reason", "")}

    def refund(self, payment, refund):
        return self._post("/refunds", {"checkout_id": payment.provider_payment_id, "amount": str(refund.amount)})["id"]


PROVIDERS = {"simulator": SimulatorProvider, "generic_http": GenericHttpProvider}


def payments_status():
    mode = settings.PAYMENTS_MODE
    if mode == "simulated":
        return {"mode": "simulated", "accepting_real_money": False,
                "message": "الدفع في وضع المحاكاة — لا تُحصّل أي أموال حقيقية."}
    if mode == "live":
        missing = live_missing()
        if not missing:
            return {"mode": "live", "accepting_real_money": True, "message": ""}
        return {"mode": "disabled", "accepting_real_money": False, "missing": missing,
                "message": "استقبال المال الحقيقي معطّل حتى اكتمال الإعدادات والتفويض."}
    return {"mode": "disabled", "accepting_real_money": False,
            "message": "الدفع الإلكتروني غير مفعّل حاليًا. يمكنك تسجيل تعهد فقط."}


def live_missing():
    missing = []
    if settings.PAYMENT_PROVIDER == "simulator":
        missing.append("PAYMENT_PROVIDER")
    if not settings.PAYMENT_WEBHOOK_SECRET:
        missing.append("PAYMENT_WEBHOOK_SECRET")
    if not settings.PAYMENT_BENEFICIARY_CONFIGURED:
        missing.append("PAYMENT_BENEFICIARY_CONFIGURED")
    if not settings.PAYMENT_LIVE_AUTHORISED:
        missing.append("PAYMENT_LIVE_AUTHORISED")
    if settings.PAYMENT_PROVIDER == "generic_http" and not (settings.PAYMENT_HTTP_BASE_URL and settings.PAYMENT_HTTP_API_KEY):
        missing.append("PAYMENT_HTTP_BASE_URL/API_KEY")
    return missing


def get_provider(name=None):
    mode = settings.PAYMENTS_MODE
    if mode == "simulated":
        if settings.IS_PRODUCTION:
            raise ServiceDisabled("وضع المحاكاة غير مسموح في الإنتاج.")
        if name not in (None, "simulator"):
            raise ServiceDisabled("المزود غير متاح في وضع المحاكاة.")
        return SimulatorProvider()
    if mode == "live" and not live_missing():
        cls = PROVIDERS.get(name or settings.PAYMENT_PROVIDER)
        if cls and not cls.simulated:
            return cls()
    raise ServiceDisabled("الدفع الإلكتروني غير مفعّل. يمكن تسجيل تعهد أو تحويل مصرفي بانتظار المطابقة.")
