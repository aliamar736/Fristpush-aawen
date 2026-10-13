"""Securely create the FIRST system administrator.

    python manage.py create_first_admin --phone 0912345678 --name "اسم" [--email a@b.ly]

The password is read interactively (or from AAWEN_ADMIN_PASSWORD for automated, one-time bootstrap)
and must pass the password validators. Refuses to run if an active system administrator already exists —
further admins are granted from the admin console by an existing admin (audited)."""
import getpass
import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Role, RoleAssignment, User, normalize_phone
from apps.core.audit import audit


class Command(BaseCommand):
    help = "Create the first system administrator (refuses if one exists)."

    def add_arguments(self, parser):
        parser.add_argument("--phone", required=True)
        parser.add_argument("--name", required=True)
        parser.add_argument("--email", default=None)

    @transaction.atomic
    def handle(self, *args, **opts):
        if RoleAssignment.objects.filter(role=Role.SYSADMIN, active=True).exists():
            raise CommandError("يوجد مدير نظام بالفعل. أضف المديرين الآخرين من لوحة الإدارة.")
        try:
            phone = normalize_phone(opts["phone"])
        except ValueError as exc:
            raise CommandError(str(exc))
        password = os.environ.get("AAWEN_ADMIN_PASSWORD")
        if not password:
            password = getpass.getpass("كلمة مرور المدير (12 حرفًا على الأقل): ")
            if password != getpass.getpass("أعد كتابتها: "):
                raise CommandError("كلمتا المرور غير متطابقتين.")
        user = User.objects.filter(phone=phone).first() or User(username=phone, phone=phone)
        user.display_name = opts["name"]
        user.email = opts["email"]
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages))
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.save()
        RoleAssignment.objects.get_or_create(user=user, role=Role.SYSADMIN, area=None, agency=None)
        audit(None, "admin.first_admin_created", user)
        self.stdout.write(self.style.SUCCESS(f"تم إنشاء مدير النظام {phone}. احذف AAWEN_ADMIN_PASSWORD من البيئة إن استخدمتها."))
