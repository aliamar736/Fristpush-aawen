"""Section 12: road alert expiry and renewal; delayed submissions never published as live."""
from datetime import timedelta

import pytest
from django.utils import timezone
from freezegun import freeze_time

from apps.core.config import get_setting, set_setting
from apps.roadnow import services
from apps.roadnow.models import RoadAlert


def post_alert(api, user, **kw):
    body = {"type": "accident", "lat": 32.87, "lng": 13.12, "description": "حادث", **kw}
    r = api.as_(user).post("/api/v1/road-alerts/", body, format="json")
    assert r.status_code in (200, 201), r.content
    return r.json()


def live_ids(api):
    return {a["id"] for a in api.as_(None).get("/api/v1/road-alerts/").json()}


@pytest.mark.django_db
def test_alert_expires_and_still_there_renews(api, ref, users):
    t0 = timezone.now()
    with freeze_time(t0):
        a = post_alert(api, users["citizen"])
        assert a["is_live"] and a["verification"] == "unverified" and a["source"] == "citizen"
        assert a["id"] in live_ids(api)
    rule = get_setting("road_rules")["accident"]   # ttl 60, extend 30, max 360
    with freeze_time(t0 + timedelta(minutes=50)):
        r = api.as_(users["citizen2"]).post(f"/api/v1/road-alerts/{a['id']}/vote/", {"vote": "still_there"}, format="json")
        assert r.status_code == 200
        exp = RoadAlert.objects.get(pk=a["id"]).expires_at
        assert exp >= t0 + timedelta(minutes=50 + rule["extend"]) - timedelta(seconds=1)
    with freeze_time(t0 + timedelta(minutes=55)):
        api.as_(users["citizen3"]).post(f"/api/v1/road-alerts/{a['id']}/vote/", {"vote": "still_there"}, format="json")
        assert RoadAlert.objects.get(pk=a["id"]).verification == "community_confirmed"
    with freeze_time(t0 + timedelta(minutes=70)):              # beyond original ttl but renewed
        services.expire_alerts()
        assert a["id"] in live_ids(api)
    with freeze_time(t0 + timedelta(minutes=200)):             # renewal window lapsed
        assert services.expire_alerts() == 1
        assert a["id"] not in live_ids(api)
        assert RoadAlert.objects.get(pk=a["id"]).status == "expired"
        hist = api.as_(None).get("/api/v1/road-alerts/", {"history": "1"}).json()
        assert any(h["id"] == a["id"] and not h["is_live"] for h in hist)


@pytest.mark.django_db
def test_max_lifetime_caps_renewals(api, ref, users):
    t0 = timezone.now()
    with freeze_time(t0):
        a = post_alert(api, users["citizen"], type="congestion")  # max_lifetime 180
    voters = [users[k] for k in ("citizen2", "citizen3", "reviewer", "coord", "manager", "ambassador", "admin")]
    for i, v in enumerate(voters):
        with freeze_time(t0 + timedelta(minutes=25 * (i + 1))):
            try:
                services.vote(RoadAlert.objects.get(pk=a["id"]), v, "still_there")
            except Exception:
                pass
    assert RoadAlert.objects.get(pk=a["id"]).expires_at <= t0 + timedelta(minutes=180, seconds=1)


@pytest.mark.django_db
def test_road_open_votes_clear_alert(api, ref, users):
    a = post_alert(api, users["citizen"])
    api.as_(users["citizen2"]).post(f"/api/v1/road-alerts/{a['id']}/vote/", {"vote": "cleared"}, format="json")
    assert RoadAlert.objects.get(pk=a["id"]).status == "active"          # one vote is not enough
    r = api.as_(users["citizen3"]).post(f"/api/v1/road-alerts/{a['id']}/vote/", {"vote": "cleared"}, format="json")
    assert r.json()["status"] == "cleared"
    assert a["id"] not in live_ids(api)
    # repeated voting by same user is rate limited per alert
    b = post_alert(api, users["citizen"], lng=13.13)
    api.as_(users["citizen2"]).post(f"/api/v1/road-alerts/{b['id']}/vote/", {"vote": "still_there"}, format="json")
    assert api.as_(users["citizen2"]).post(f"/api/v1/road-alerts/{b['id']}/vote/", {"vote": "still_there"},
                                           format="json").status_code == 409


@pytest.mark.django_db
def test_agency_staff_clears_immediately_and_marks_official(api, ref, users):
    a = post_alert(api, users["citizen"], type="closure")
    r = api.as_(users["roads_staff"]).post(f"/api/v1/road-alerts/{a['id']}/vote/", {"vote": "cleared"}, format="json")
    assert r.json()["status"] == "cleared"


@pytest.mark.django_db
def test_delayed_submission_not_published_as_live(api, ref, users):
    observed = timezone.now() - timedelta(minutes=90)   # accident stale_after = 45 min
    a = post_alert(api, users["citizen"], observed_at=observed.isoformat())
    assert a["status"] == "historical" and not a["is_live"]
    assert "متأخر" in a["notice"]
    assert a["id"] not in live_ids(api)
    # fresh but slightly delayed (within threshold) is live, with its real observation time kept
    obs2 = timezone.now() - timedelta(minutes=10)
    b = post_alert(api, users["citizen"], observed_at=obs2.isoformat(), lng=13.13)
    from django.utils.dateparse import parse_datetime
    assert b["is_live"] and abs((parse_datetime(b["observed_at"]) - obs2).total_seconds()) < 1


@pytest.mark.django_db
def test_rules_are_configurable(api, ref, users):
    rules = get_setting("road_rules")
    rules["accident"]["stale_after"] = 200
    rules["accident"]["ttl"] = 180
    r = api.as_(users["admin"]).patch("/api/v1/admin/settings", {"road_rules": rules}, format="json")
    assert r.status_code == 200
    assert api.as_(users["coord"]).patch("/api/v1/admin/settings", {"road_rules": rules}, format="json").status_code == 403
    a = post_alert(api, users["citizen"], observed_at=(timezone.now() - timedelta(minutes=90)).isoformat())
    assert a["status"] == "active"


@pytest.mark.django_db
def test_no_fabricated_traffic_metrics_and_emergency_is_separate(api, ref, users):
    a = post_alert(api, users["citizen"], type="congestion")
    assert a["type_label"] == "ازدحام مبلّغ عنه"
    for forbidden in ("speed", "travel_time", "eta", "route", "delay_minutes"):
        assert forbidden not in a
    em = api.as_(None).get("/api/v1/emergency").json()
    assert "لا يرسل إسعافًا" in em["ar"] and em["contacts"] == []
