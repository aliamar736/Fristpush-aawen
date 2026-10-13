"""Outbound connectors. Real providers need credentials (see docs/INTEGRATIONS.md); without them the
explicit simulators record deliveries with status='simulated' so nothing pretends to be sent."""
import json
import logging
import urllib.request

from django.conf import settings

from .models import Delivery

log = logging.getLogger("aawen.channels")


def send_sms(phone, text):
    provider = settings.SMS_PROVIDER
    if provider == "console":
        log.warning("[SMS SIMULATOR] to=%s text=%s", phone, text)
        return Delivery.objects.create(channel="sms", provider="console", to=phone, payload={"text": text},
                                       status="simulated")
    if provider == "http":
        if not settings.SMS_HTTP_URL or not settings.SMS_HTTP_TOKEN:
            return Delivery.objects.create(channel="sms", provider="http", to=phone, payload={},
                                           status="failed", error="SMS provider not configured")
        req = urllib.request.Request(
            settings.SMS_HTTP_URL, method="POST",
            data=json.dumps({"to": phone, "from": settings.SMS_SENDER_ID, "text": text}).encode(),
            headers={"Authorization": f"Bearer {settings.SMS_HTTP_TOKEN}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                ok = 200 <= resp.status < 300
            return Delivery.objects.create(channel="sms", provider="http", to=phone, payload={"len": len(text)},
                                           status="sent" if ok else "failed")
        except Exception as exc:  # noqa: BLE001
            return Delivery.objects.create(channel="sms", provider="http", to=phone, payload={},
                                           status="failed", error=str(exc)[:300])
    return Delivery.objects.create(channel="sms", provider="disabled", to=phone, payload={}, status="skipped",
                                   error="SMS disabled")


def send_push(token, title, body, data):
    provider = settings.PUSH_PROVIDER
    if provider == "simulated":
        return Delivery.objects.create(channel="push", provider="simulated", to=token[-12:],
                                       payload={"title": title, "data": data}, status="simulated")
    if provider == "fcm":
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import service_account
        except ImportError:
            return Delivery.objects.create(channel="push", provider="fcm", to=token[-12:], payload={},
                                           status="failed", error="google-auth not installed")
        if not settings.FCM_PROJECT_ID or not settings.FCM_SERVICE_ACCOUNT_FILE:
            return Delivery.objects.create(channel="push", provider="fcm", to=token[-12:], payload={},
                                           status="failed", error="FCM not configured")
        creds = service_account.Credentials.from_service_account_file(
            settings.FCM_SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/firebase.messaging"])
        creds.refresh(Request())
        msg = {"message": {"token": token, "notification": {"title": title, "body": body},
                           "data": {k: str(v) for k, v in data.items()}}}
        req = urllib.request.Request(
            f"https://fcm.googleapis.com/v1/projects/{settings.FCM_PROJECT_ID}/messages:send", method="POST",
            data=json.dumps(msg).encode(),
            headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10):
                pass
            return Delivery.objects.create(channel="push", provider="fcm", to=token[-12:], payload={}, status="sent")
        except Exception as exc:  # noqa: BLE001
            return Delivery.objects.create(channel="push", provider="fcm", to=token[-12:], payload={},
                                           status="failed", error=str(exc)[:300])
    return None
