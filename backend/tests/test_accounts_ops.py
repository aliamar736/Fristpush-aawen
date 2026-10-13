"""Auth, sessions, account deletion, first-admin bootstrap, demo separation, backup & restore."""
import os
from datetime import timedelta

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone
from freezegun import freeze_time

from apps.accounts.models import OTPChallenge, Role, RoleAssignment, User
from apps.accounts.services import process_due_deletions


@pytest.mark.django_db
def test_otp_login_flow_and_lockout(api, ref):
    c = api.as_(None)
    r = c.post("/api/v1/auth/otp/request", {"phone": "091 234 5678"}, format="json")
    assert r.status_code == 200 and r.json()["phone"] == "+218912345678"
    code = r.json()["dev_code"]                       # only exposed with the console SMS simulator, never in prod
    assert c.post("/api/v1/auth/otp/verify", {"phone": "0912345678", "code": "000000" if code != "000000" else "111111"},
                  format="json").status_code == 401
    r = c.post("/api/v1/auth/otp/verify", {"phone": "0912345678", "code": code, "display_name": "علي"}, format="json")
    assert r.status_code == 200 and r.json()["created"] and r.json()["access"]
    # code is single-use
    assert c.post("/api/v1/auth/otp/verify", {"phone": "0912345678", "code": code}, format="json").status_code == 401
    # brute force: 5 attempts max per challenge
    c.post("/api/v1/auth/otp/request", {"phone": "0923334444"}, format="json")
    ch = OTPChallenge.objects.filter(phone="+218923334444").latest("created_at")
    for _ in range(6):
        ch.refresh_from_db()
        ch.verify("999999")
    ch.refresh_from_db()
    assert ch.attempts == OTPChallenge.MAX_ATTEMPTS
    assert c.post("/api/v1/auth/otp/request", {"phone": "12"}, format="json").status_code == 400


@pytest.mark.django_db
def test_otp_not_exposed_in_production(settings, ref):
    from apps.accounts.services import request_otp
    settings.IS_PRODUCTION = True
    assert "dev_code" not in request_otp("0912345679")


@pytest.mark.django_db
def test_sessions_list_and_revoke(api, ref):
    c = api.as_(None)
    code = c.post("/api/v1/auth/otp/request", {"phone": "0915550000"}, format="json").json()["dev_code"]
    tokens = c.post("/api/v1/auth/otp/verify", {"phone": "0915550000", "code": code}, format="json").json()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert len(c.get("/api/v1/auth/sessions").json()) == 1
    assert c.delete("/api/v1/auth/sessions").json()["revoked"] == 1
    r = api.as_(None).post("/api/v1/auth/refresh", {"refresh": tokens["refresh"]}, format="json")
    assert r.status_code == 401                                   # revoked refresh token is dead


@pytest.mark.django_db
def test_account_deletion_anonymises_but_keeps_civic_record(api, ref, users):
    import uuid
    u = users["citizen"]
    rid = api.as_(u).post("/api/v1/reports/", {"category": ref["cats"]["garbage"].pk, "lat": 32.87, "lng": 13.12,
                                                "client_id": str(uuid.uuid4())}, format="json").json()["id"]
    r = api.as_(u).post("/api/v1/me/deletion")
    assert r.status_code == 201
    with freeze_time(timezone.now() + timedelta(days=8)):
        assert process_due_deletions() == 1
    u.refresh_from_db()
    assert u.phone is None and not u.is_active and u.display_name == "" and u.username.startswith("deleted-")
    from apps.reports.models import Report
    assert Report.objects.filter(pk=rid).exists()                 # report stays (anonymous)


@pytest.mark.django_db
def test_first_admin_bootstrap_is_safe(db, monkeypatch):
    monkeypatch.setenv("AAWEN_ADMIN_PASSWORD", "short")
    with pytest.raises(CommandError):
        call_command("create_first_admin", phone="0911111111", name="مدير")
    monkeypatch.setenv("AAWEN_ADMIN_PASSWORD", "Kx9!correct-horse-Battery")
    call_command("create_first_admin", phone="0911111111", name="مدير")
    u = User.objects.get(phone="+218911111111")
    assert u.check_password("Kx9!correct-horse-Battery") and RoleAssignment.objects.filter(user=u, role=Role.SYSADMIN).exists()
    with pytest.raises(CommandError):                             # second run refused
        call_command("create_first_admin", phone="0922222222", name="آخر")


@pytest.mark.django_db
def test_demo_seed_refused_when_not_allowed(settings):
    settings.DEMO_DATA_ALLOWED = False
    with pytest.raises(CommandError):
        call_command("seed_demo")


@pytest.mark.django_db
def test_demo_rows_are_flagged_and_purgeable(settings):
    call_command("seed_demo", verbosity=0)
    from apps.reports.models import Report
    assert Report.objects.count() > 0 and not Report.objects.filter(is_demo=False).exists()
    assert not User.objects.filter(is_demo=False).exists()
    call_command("purge_demo", verbosity=0)
    assert Report.objects.count() == 0 and User.objects.count() == 0


@pytest.mark.django_db
def test_health_and_public_config(api):
    assert api.as_(None).get("/api/v1/health").json()["db"] is True
    cfg = api.as_(None).get("/api/v1/config").json()
    assert cfg["payments"]["accepting_real_money"] is False
    assert "emergency_notice" in cfg and cfg["features"]["surplus_food"] is False


@pytest.mark.slow
@pytest.mark.django_db(transaction=True)
def test_backup_and_restore_roundtrip(tmp_path, ref, users, settings):
    """Creates a real pg_dump of the test database, restores it into a fresh database and compares row counts."""
    import uuid

    import psycopg

    from apps.core.backup import create_backup, restore_backup
    from apps.reports import services
    services.create_report(users["citizen"], {"category": ref["cats"]["pothole"].pk, "lat": 32.87, "lng": 13.12,
                                              "client_id": uuid.uuid4()})
    settings.MEDIA_ROOT = str(tmp_path / "media")
    os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
    manifest = create_backup(tmp_path)
    target = f"aawen_restore_{uuid.uuid4().hex[:8]}"
    try:
        out = restore_backup(manifest, target)
        assert out["ok"], out["mismatches"]
        assert out["counts"]["reports_report"] == 1 and out["counts"]["geo_area"] == 2
    finally:
        from django.conf import settings as s
        db = s.DATABASES["default"]
        with psycopg.connect(host=db["HOST"] or "localhost", user=db["USER"], password=db["PASSWORD"], dbname="postgres",
                             autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{target}"')
    # corrupted backup is detected
    dump = next(tmp_path.glob("*.dump"))
    dump.write_bytes(dump.read_bytes()[:-10] + b"corrupted!")
    with pytest.raises(RuntimeError):
        restore_backup(manifest, f"aawen_restore_{uuid.uuid4().hex[:8]}")
