"""Section 12: race for the last unit; reserve/cancel/pickup/return; tasks, needs, proposals, surplus."""
import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone
from freezegun import freeze_time

from apps.community.models import BudgetCycle, Initiative, Need, Proposal, Skill, Task, TaskBooking
from apps.inventory import services as inv
from apps.inventory.models import Reservation, Resource

from .conftest import make_user


@pytest.mark.django_db(transaction=True)
def test_race_for_last_unit(ref):
    """8 people try to reserve the last 1 unit at the same moment — exactly one succeeds."""
    keeper = make_user(name="أمين المخزن")
    res = Resource.objects.create(title="سلم", kind="loan", total_quantity=3, custodian=keeper, pickup_location="x")
    early = make_user()
    inv.reserve(early, res.pk, 2)
    racers = [make_user() for _ in range(8)]
    outcomes = []
    barrier = threading.Barrier(len(racers))

    def go(u):
        barrier.wait()
        try:
            inv.reserve(u, res.pk, 1)
            outcomes.append("ok")
        except Exception as exc:  # Conflict
            outcomes.append(type(exc).__name__)
        finally:
            connection.close()

    ts = [threading.Thread(target=go, args=(u,)) for u in racers]
    [t.start() for t in ts]
    [t.join() for t in ts]
    res.refresh_from_db()
    assert outcomes.count("ok") == 1 and outcomes.count("Conflict") == 7, outcomes
    assert res.reserved_quantity == 3 and res.available_quantity == 0
    assert Reservation.objects.filter(resource=res, status="reserved").count() == 2


@pytest.mark.django_db
def test_reserve_cancel_pickup_return_cycle(api, ref, users):
    keeper = users["ambassador"]
    res = Resource.objects.create(title="عربة يد", kind="loan", total_quantity=2, custodian=keeper,
                                  pickup_location="المخزن", max_loan_days=3)
    c = api.as_(users["citizen"])
    r = c.post(f"/api/v1/resources/{res.pk}/reserve/", {"quantity": 2}, format="json")
    assert r.status_code == 201
    rid = r.json()["id"]
    assert c.post(f"/api/v1/resources/{res.pk}/reserve/", {"quantity": 1}, format="json").status_code == 409
    # cancel returns stock
    assert c.post(f"/api/v1/reservations/{rid}/cancel/").json()["status"] == "cancelled"
    res.refresh_from_db()
    assert res.available_quantity == 2
    rid = c.post(f"/api/v1/resources/{res.pk}/reserve/", {"quantity": 1}, format="json").json()["id"]
    # only the custodian confirms the hand-over
    assert c.post(f"/api/v1/reservations/{rid}/pickup/").status_code == 403
    k = api.as_(keeper)
    out = k.post(f"/api/v1/reservations/{rid}/pickup/").json()
    assert out["status"] == "picked_up" and out["due_return_at"]
    res.refresh_from_db()
    assert (res.reserved_quantity, res.out_quantity, res.available_quantity) == (0, 1, 1)
    assert c.post(f"/api/v1/reservations/{rid}/cancel/").status_code == 409   # cannot cancel after pickup
    with freeze_time(timezone.now() + timedelta(days=5)):
        assert inv.mark_overdue() == 1
    out = k.post(f"/api/v1/reservations/{rid}/return/", {"condition": "needs_repair"}, format="json").json()
    assert out["status"] == "returned"
    res.refresh_from_db()
    assert res.out_quantity == 0 and res.available_quantity == 2 and res.condition == "needs_repair"


@pytest.mark.django_db
def test_donation_stock_is_consumed_and_not_returned(api, ref, users):
    res = Resource.objects.create(title="أكياس", kind="donation", total_quantity=10, custodian=users["ambassador"],
                                  pickup_location="x")
    rid = api.as_(users["citizen"]).post(f"/api/v1/resources/{res.pk}/reserve/", {"quantity": 4}, format="json").json()["id"]
    api.as_(users["ambassador"]).post(f"/api/v1/reservations/{rid}/pickup/")
    res.refresh_from_db()
    assert res.consumed_quantity == 4 and res.available_quantity == 6
    assert api.as_(users["ambassador"]).post(f"/api/v1/reservations/{rid}/return/").status_code == 409
    # cannot reduce total below what is used
    r = api.as_(users["ambassador"]).patch(f"/api/v1/resources/{res.pk}/", {"total_quantity": 3}, format="json")
    assert r.status_code == 400


def _initiative(users, ref, status=Initiative.ACTIVE):
    return Initiative.objects.create(title="تنظيف", summary="س", area=ref["west"], manager=users["manager"],
                                     status=status, funding_target=1000)


@pytest.mark.django_db
def test_task_booking_capacity_attendance_completion(api, ref, users):
    ini = _initiative(users, ref)
    t = Task.objects.create(initiative=ini, title="تنظيف", starts_at=timezone.now() + timedelta(days=1), capacity=1,
                            owner=users["manager"], area=ref["west"])
    a, b = users["citizen"], users["citizen2"]
    r = api.as_(a).post(f"/api/v1/tasks/{t.pk}/book/")
    assert r.status_code == 201
    assert api.as_(b).post(f"/api/v1/tasks/{t.pk}/book/").status_code == 409            # full
    bid = r.json()["id"]
    assert api.as_(a).post(f"/api/v1/bookings/{bid}/complete/", {"note": "تم"}, format="json").status_code == 409
    assert api.as_(b).post(f"/api/v1/bookings/{bid}/attendance/", {"attended": True}, format="json").status_code == 403
    assert api.as_(users["manager"]).post(f"/api/v1/bookings/{bid}/attendance/", {"attended": True},
                                          format="json").json()["status"] == "attended"
    assert api.as_(a).post(f"/api/v1/bookings/{bid}/complete/", {"note": "نظفنا"}, format="json").json()["status"] == "completed"
    # cancellation frees the seat
    t2 = Task.objects.create(title="نقل", starts_at=timezone.now() + timedelta(days=2), capacity=1, owner=users["coord"])
    bid2 = api.as_(a).post(f"/api/v1/tasks/{t2.pk}/book/").json()["id"]
    api.as_(a).post(f"/api/v1/bookings/{bid2}/cancel/")
    assert api.as_(b).post(f"/api/v1/tasks/{t2.pk}/book/").status_code == 201


@pytest.mark.django_db
def test_skills_profile_recommendations(api, ref, users):
    cleaning = Skill.objects.get(slug="cleaning")
    driving = Skill.objects.get(slug="driving")
    sat_morning = timezone.localtime(timezone.now() + timedelta(days=7))
    while sat_morning.weekday() != 5:  # Saturday
        sat_morning += timedelta(days=1)
    sat_morning = sat_morning.replace(hour=9, minute=0)
    good = Task.objects.create(title="تنظيف", skill=cleaning, area=ref["west"], starts_at=sat_morning, owner=users["coord"])
    other = Task.objects.create(title="قيادة", skill=driving, area=ref["east"], starts_at=sat_morning, owner=users["coord"])
    r = api.as_(users["citizen"]).put("/api/v1/me/volunteer-profile", {
        "skills": [cleaning.pk], "preferred_areas": [ref["west"].pk],
        "availability": {"days": [0], "slots": ["morning"]}}, format="json")
    assert r.status_code == 200
    rec = api.as_(users["citizen"]).get("/api/v1/tasks/recommended/").json()
    assert rec[0]["id"] == good.pk and "تطابق مهارة" in rec[0]["match_reasons"]
    assert rec[-1]["id"] == other.pk


@pytest.mark.django_db
def test_blocking_needs_and_help_offer_lifecycle(api, ref, users):
    ini = _initiative(users, ref)
    need = Need.objects.create(initiative=ini, kind="transport", title="شاحنة", is_blocking=True)
    Need.objects.create(initiative=_initiative(users, ref, Initiative.PENDING), kind="tools", title="x", is_blocking=True)
    blocking = api.as_(None).get("/api/v1/needs/blocking/").json()
    assert [n["id"] for n in blocking] == [need.pk]                  # unapproved initiatives excluded
    o = api.as_(users["citizen"]).post(f"/api/v1/needs/{need.pk}/offer/", {"message": "عندي شاحنة يوم السبت"},
                                       format="json").json()
    m = api.as_(users["manager"])
    assert api.as_(users["citizen2"]).post(f"/api/v1/help-offers/{o['id']}/decide/", {"action": "accept"},
                                           format="json").status_code == 403
    assert m.post(f"/api/v1/help-offers/{o['id']}/decide/", {"action": "receive"}, format="json").status_code == 409
    assert m.post(f"/api/v1/help-offers/{o['id']}/decide/", {"action": "accept"}, format="json").json()["status"] == "accepted"
    assert m.post(f"/api/v1/help-offers/{o['id']}/decide/", {"action": "receive"}, format="json").json()["status"] == "fulfilled"
    need.refresh_from_db()
    assert need.status == "met"
    assert api.as_(None).get("/api/v1/needs/blocking/").json() == []


@pytest.mark.django_db
def test_initiative_approval_by_independent_coordinator(api, ref, users):
    r = api.as_(users["citizen"]).post("/api/v1/initiatives/", {"title": "مبادرة", "summary": "ملخص", "area": ref["west"].pk},
                                       format="json")
    iid = r.json()["id"]
    assert r.json()["status"] == "draft"
    assert api.as_(None).get(f"/api/v1/initiatives/{iid}/").status_code == 404      # drafts are private
    api.as_(users["citizen"]).post(f"/api/v1/initiatives/{iid}/submit/")
    assert api.as_(users["citizen"]).post(f"/api/v1/initiatives/{iid}/decide/", {"approve": True},
                                          format="json").status_code == 403
    assert api.as_(users["coord"]).post(f"/api/v1/initiatives/{iid}/decide/", {"approve": True},
                                        format="json").json()["status"] == "approved"


@pytest.mark.django_db
def test_proposal_review_and_budget_constrained_voting(api, ref, users):
    now = timezone.now()
    cyc = BudgetCycle.objects.create(title="د", area=ref["west"], budget_amount=Decimal("10000"), budget_source="معلن",
                                     voting_opens=now - timedelta(days=1), voting_closes=now + timedelta(days=5),
                                     status="voting")
    r = api.as_(users["citizen"]).post("/api/v1/proposals/", {"cycle": cyc.pk, "title": "إنارة", "description": "د",
                                                               "area": ref["west"].pk, "estimated_cost": "6000"},
                                       format="json")
    p1 = r.json()["id"]
    assert api.as_(users["citizen2"]).post(f"/api/v1/proposals/{p1}/vote/").status_code == 409   # not eligible yet
    rv = api.as_(users["reviewer"])
    r = rv.post(f"/api/v1/proposals/{p1}/review/", {"decision": "eligible", "feasibility_ok": True}, format="json")
    assert r.status_code == 400                                                                  # missing checks
    r = rv.post(f"/api/v1/proposals/{p1}/review/", {"decision": "eligible", "feasibility_ok": True, "permit_ok": True,
                                                   "cost_verified": "6000", "maintenance_plan": "البلدية"}, format="json")
    assert r.json()["status"] == "eligible"
    p2 = Proposal.objects.create(cycle=cyc, title="مقاعد", description="د", cost_verified=5000, status="eligible",
                                 feasibility_ok=True, permit_ok=True, maintenance_plan="م")
    v = api.as_(users["citizen2"])
    assert v.post(f"/api/v1/proposals/{p1}/vote/").status_code == 200
    assert v.post(f"/api/v1/proposals/{p1}/vote/").status_code == 409                # once
    r = v.post(f"/api/v1/proposals/{p2.pk}/vote/")
    assert r.status_code == 400 and "الميزانية" in str(r.json())                      # 6000+5000 > 10000
    res = api.as_(None).get(f"/api/v1/budget-cycles/{cyc.pk}/results/").json()
    assert res["proposals"][0]["selected"] and not res["proposals"][1]["selected"]


@pytest.mark.django_db
def test_food_surplus_disabled_until_enabled(api, ref, users):
    base = {"title": "خبز", "kind": "food", "quantity": "20", "pickup_location": "x", "pickup_window": "مساء",
            "available_until": (timezone.now() + timedelta(days=1)).isoformat()}
    assert api.as_(users["citizen"]).post("/api/v1/surplus/", base, format="json").status_code == 503
    r = api.as_(users["citizen"]).post("/api/v1/surplus/", {**base, "kind": "non_food", "title": "كراسي"}, format="json")
    sid = r.json()["id"]
    assert api.as_(None).get("/api/v1/surplus/").json()["results"][0]["pickup_location"] == "يظهر بعد الحجز"
    assert api.as_(users["citizen"]).post(f"/api/v1/surplus/{sid}/reserve/").status_code == 409
    assert api.as_(users["citizen2"]).post(f"/api/v1/surplus/{sid}/reserve/").json()["status"] == "reserved"
    assert api.as_(users["citizen3"]).post(f"/api/v1/surplus/{sid}/reserve/").status_code == 409
    assert api.as_(users["citizen"]).post(f"/api/v1/surplus/{sid}/handover/").json()["status"] == "handed_over"


@pytest.mark.django_db
def test_coverage_dashboard_and_survey_assignment(api, ref, users):
    cov = api.as_(users["coord"]).get("/api/v1/coverage").json()
    assert {a["area"] for a in cov["areas"]} == {"غرب", "شرق"} and all(a["low_participation"] for a in cov["areas"])
    assert api.as_(users["citizen"]).get("/api/v1/coverage").status_code == 403
    r = api.as_(users["coord"]).post("/api/v1/surveys/", {"area": ref["east"].pk, "ambassador": users["ambassador"].pk,
                                                           "due_at": (timezone.now() + timedelta(days=7)).isoformat(),
                                                           "instructions": "امسح الشوارع الرئيسية"}, format="json")
    assert r.status_code == 201
    r2 = api.as_(users["coord"]).post("/api/v1/surveys/", {"area": ref["east"].pk, "ambassador": users["citizen"].pk,
                                                            "due_at": timezone.now().isoformat()}, format="json")
    assert r2.status_code == 400
    sid = r.json()["id"]
    out = api.as_(users["ambassador"]).patch(f"/api/v1/surveys/{sid}/", {"status": "done", "findings_note": "5 حفر"},
                                             format="json").json()
    assert out["completed_at"]


@pytest.mark.django_db
def test_care_points_only_verified_are_public(api, ref, users):
    r = api.as_(users["ambassador"]).post("/api/v1/care-points/", {"name": "صيدلية", "host_type": "صيدلية",
                                                                   "point": {"lat": 32.87, "lng": 13.12},
                                                                   "services": ["مية"], "hours": "9-5"}, format="json")
    cid = r.json()["id"]
    assert api.as_(None).get("/api/v1/care-points/").json()["results"] == []
    assert api.as_(users["ambassador"]).post(f"/api/v1/care-points/{cid}/verify/").status_code == 403
    api.as_(users["coord"]).post(f"/api/v1/care-points/{cid}/verify/")
    pub = api.as_(None).get("/api/v1/care-points/").json()["results"]
    assert pub[0]["verified_at"]


@pytest.mark.django_db
def test_bundle_keeps_individual_report_status(api, ref, users):
    import uuid
    ids = []
    for lng in (13.120, 13.121):
        ids.append(api.as_(users["citizen"]).post("/api/v1/reports/", {"category": ref["cats"]["pothole"].pk,
                                                                       "lat": 32.87, "lng": lng,
                                                                       "client_id": str(uuid.uuid4())}, format="json").json()["id"])
    for to in ("under_review", "verified"):
        api.as_(users["reviewer"]).post(f"/api/v1/reports/{ids[0]}/transition/", {"to": to}, format="json")
    r = api.as_(users["coord"]).post("/api/v1/bundles/", {"title": "زيارة صيانة", "kind": "visit", "reports": ids},
                                     format="json")
    assert r.status_code == 201
    statuses = {x["id"]: x["status"] for x in r.json()["reports_detail"]}
    assert statuses == {ids[0]: "verified", ids[1]: "submitted"}
