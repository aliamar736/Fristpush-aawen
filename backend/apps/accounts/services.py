from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.audit import audit
from apps.core.config import feature_enabled

from .models import DeletionRequest, OTPChallenge, User, normalize_phone


def request_otp(raw_phone):
    try:
        phone = normalize_phone(raw_phone)
    except ValueError as exc:
        raise ValidationError({"phone": str(exc)})
    ch, code = OTPChallenge.issue(phone)
    from apps.notifications.channels import send_sms
    delivery = send_sms(phone, f"رمز الدخول إلى عاون: {code}. لا تشاركه مع أحد.")
    out = {"phone": phone, "expires_in": int(OTPChallenge.TTL.total_seconds()), "delivery": delivery.status}
    # Development convenience ONLY: never returned in production or when a real SMS provider is used
    if not settings.IS_PRODUCTION and settings.SMS_PROVIDER == "console":
        out["dev_code"] = code
    return out


def tokens_for(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


@transaction.atomic
def verify_otp(raw_phone, code, display_name=""):
    try:
        phone = normalize_phone(raw_phone)
    except ValueError as exc:
        raise ValidationError({"phone": str(exc)})
    ch = OTPChallenge.objects.select_for_update().filter(phone=phone, consumed_at__isnull=True).order_by("-created_at").first()
    if not ch or not ch.verify(code):
        raise AuthenticationFailed("الرمز غير صحيح أو انتهت صلاحيته.")
    user = User.objects.filter(phone=phone).first()
    created = False
    if user is None:
        if not feature_enabled("public_registration"):
            raise PermissionDenied("التسجيل مغلق حاليًا.")
        user = User.objects.create_user(username=phone, phone=phone, display_name=display_name[:80])
        created = True
    if not user.is_active:
        raise AuthenticationFailed("الحساب غير مفعّل.")
    user.phone_verified_at = timezone.now()
    user.last_login = timezone.now()
    user.save(update_fields=["phone_verified_at", "last_login"])
    return user, created


@transaction.atomic
def request_deletion(user):
    req = DeletionRequest.objects.filter(user=user, status=DeletionRequest.PENDING).first()
    if req:
        return req
    req = DeletionRequest.objects.create(user=user, scheduled_for=timezone.now() + DeletionRequest.GRACE)
    audit(user, "account.deletion_requested", user)
    return req


def anonymize(user):
    """Removes personal data; keeps anonymised civic records (reports, ledger) for accountability."""
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
    for t in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=t)
    user.username = f"deleted-{user.pk}"
    user.phone = None
    user.email = None
    user.display_name = ""
    user.is_active = False
    user.deleted_at = timezone.now()
    user.set_unusable_password()
    user.save()
    user.devices.all().delete()
    user.role_assignments.update(active=False)
    from apps.community.models import VolunteerProfile
    VolunteerProfile.objects.filter(user=user).delete()
    from apps.notifications.models import Notification
    Notification.objects.filter(user=user).delete()
    audit(None, "account.anonymized", ("accounts.user", user.pk))


def process_due_deletions(now=None):
    now = now or timezone.now()
    n = 0
    for req in DeletionRequest.objects.filter(status=DeletionRequest.PENDING, scheduled_for__lte=now).select_related("user"):
        with transaction.atomic():
            anonymize(req.user)
            req.status, req.processed_at = DeletionRequest.DONE, now
            req.save()
            n += 1
    return n
