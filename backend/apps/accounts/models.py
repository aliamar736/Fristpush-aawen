import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.core.models import DemoFlag


class Role:
    CITIZEN = "citizen"
    AMBASSADOR = "ambassador"
    VOLUNTEER = "volunteer"
    REVIEWER = "reviewer"
    COORDINATOR = "coordinator"
    AGENCY_STAFF = "agency_staff"
    INITIATIVE_MANAGER = "initiative_manager"
    ACCOUNTANT = "accountant"
    FINANCIAL_AUDITOR = "financial_auditor"
    SYSADMIN = "sysadmin"

    CHOICES = [
        (CITIZEN, "مواطن"), (AMBASSADOR, "سفير"), (VOLUNTEER, "متطوع"), (REVIEWER, "مراجع"),
        (COORDINATOR, "منسق"), (AGENCY_STAFF, "موظف جهة"), (INITIATIVE_MANAGER, "مسؤول مبادرة"),
        (ACCOUNTANT, "محاسب"), (FINANCIAL_AUDITOR, "مراجع مالي"), (SYSADMIN, "مدير النظام"),
    ]
    STAFF_ROLES = {REVIEWER, COORDINATOR, AGENCY_STAFF, ACCOUNTANT, FINANCIAL_AUDITOR, SYSADMIN}
    # Roles a user can never self-assign or receive through self-service flows
    PRIVILEGED = STAFF_ROLES | {INITIATIVE_MANAGER, AMBASSADOR}


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, username, password=None, **extra):
        if not username:
            raise ValueError("username (phone or email) is required")
        user = self.model(username=username, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, username, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(username, password, **extra)

    def create_superuser(self, username, password, **extra):
        # Refuse weak passwords; first admin should use `manage.py create_first_admin`
        from django.contrib.auth.password_validation import validate_password
        validate_password(password)
        extra.update(is_staff=True, is_superuser=True)
        return self._create(username, password, **extra)


def normalize_phone(raw: str) -> str:
    """Normalise Libyan numbers to E.164 (+2189XXXXXXXX). Accepts 09x, 9x, 2189x, +2189x."""
    digits = "".join(ch for ch in str(raw) if ch.isdigit() or ch == "+")
    digits = digits.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    if digits.startswith("+"):
        digits = digits[1:]
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("218"):
        local = digits[3:]
    elif digits.startswith("0"):
        local = digits[1:]
    else:
        local = digits
    if len(local) != 9 or not local.startswith("9"):
        raise ValueError("رقم الهاتف غير صحيح. مثال: 0912345678")
    return "+218" + local


class User(AbstractBaseUser, PermissionsMixin, DemoFlag):
    username = models.CharField(max_length=150, unique=True)  # phone (E.164) for citizens, email for staff
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    display_name = models.CharField(max_length=80, blank=True)
    preferred_language = models.CharField(max_length=5, default="ar")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # Django admin access only
    date_joined = models.DateTimeField(default=timezone.now)
    deleted_at = models.DateTimeField(null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.display_name or self.username

    @property
    def public_name(self):
        """Name safe to show publicly (never the phone number)."""
        return self.display_name or "مشارك"


class RoleAssignment(models.Model):
    """A role, optionally scoped to an Area (None = whole platform) and/or an Agency."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_assignments")
    role = models.CharField(max_length=30, choices=Role.CHOICES, db_index=True)
    area = models.ForeignKey("geo.Area", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    agency = models.ForeignKey("agencies.Agency", null=True, blank=True, on_delete=models.CASCADE,
                               related_name="staff_assignments")
    granted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    granted_at = models.DateTimeField(default=timezone.now)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "role", "area", "agency"], name="uniq_role_scope",
                                               nulls_distinct=False)]

    def __str__(self):
        return f"{self.user} → {self.role}"


class OTPChallenge(models.Model):
    phone = models.CharField(max_length=20, db_index=True)
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)

    MAX_ATTEMPTS = 5
    TTL = timedelta(minutes=5)

    @staticmethod
    def _hash(phone, code):
        return hashlib.sha256(f"{settings.SECRET_KEY}:{phone}:{code}".encode()).hexdigest()

    @classmethod
    def issue(cls, phone):
        code = f"{secrets.randbelow(1_000_000):06d}"
        ch = cls.objects.create(phone=phone, code_hash=cls._hash(phone, code), expires_at=timezone.now() + cls.TTL)
        return ch, code

    def verify(self, code):
        if self.consumed_at or self.expires_at < timezone.now() or self.attempts >= self.MAX_ATTEMPTS:
            return False
        self.attempts += 1
        ok = secrets.compare_digest(self.code_hash, self._hash(self.phone, str(code).strip()))
        if ok:
            self.consumed_at = timezone.now()
        self.save(update_fields=["attempts", "consumed_at"])
        return ok


class DeletionRequest(models.Model):
    PENDING, CANCELLED, DONE = "pending", "cancelled", "done"
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="deletion_requests")
    requested_at = models.DateTimeField(auto_now_add=True)
    scheduled_for = models.DateTimeField()
    status = models.CharField(max_length=10, default=PENDING,
                              choices=[(PENDING, "معلق"), (CANCELLED, "ملغى"), (DONE, "منفذ")])
    processed_at = models.DateTimeField(null=True, blank=True)
    GRACE = timedelta(days=7)
