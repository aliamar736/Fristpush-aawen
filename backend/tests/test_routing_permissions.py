"""Section 12: routing on area boundaries + agency/area permissions enforced server-side."""
import uuid

import pytest

from apps.accounts.models import Role
from apps.reports.models import Report, Status

from .conftest import make_user


def create(api, user, ref, lng, lat, cat="pothole"):
    r = api.as_(user).post("/api/v1/reports/", {"category": ref["cats"][cat].pk, "lat": lat, "lng": lng,
                                                "client_id": str(uuid.uuid4())}, format="json")
    assert r.status_code == 201, r.content
    return Report.objects.get(pk=r.json()["id"])


@pytest.mark.django_db
def test_area_specific_rule_overrides_city_rule(api, ref, users):
    west = create(api, users["citizen"], ref, 13.12, 32.87, "garbage")
    east = create(api, users["citizen"], ref, 13.18, 32.87, "garbage")
    assert west.area == ref["west"] and west.agency == ref["clean"] and west.routing_status == "auto"
    assert east.area == ref["east"] and east.agency == ref["east_muni"] and east.routing_status == "auto"


@pytest.mark.django_db
def test_point_near_boundary_with_different_agencies_needs_review(api, ref, users):
    # 10 m east of the shared boundary (lng 13.15): east → بلدية الشرق, west → النظافة
    r = create(api, users["citizen"], ref, 13.15011, 32.87, "garbage")
    assert r.routing_status == Report.ROUTING_REVIEW
    agencies = {c["agency"] for c in r.routing_candidates}
    assert agencies == {"النظافة", "بلدية الشرق"}
    assert "حد" in r.routing_notes


@pytest.mark.django_db
def test_point_near_boundary_same_agency_is_auto(api, ref, users):
    r = create(api, users["citizen"], ref, 13.15011, 32.87, "pothole")  # roads on both sides
    assert r.routing_status == Report.ROUTING_AUTO and r.agency == ref["roads"]


@pytest.mark.django_db
def test_point_outside_coverage_needs_review(api, ref, users):
    r = create(api, users["citizen"], ref, 13.40, 32.70, "pothole")
    assert r.area is None and r.agency is None and r.routing_status == Report.ROUTING_REVIEW
    # cannot be referred without an agency
    api.as_(users["reviewer"]).post(f"/api/v1/reports/{r.pk}/transition/", {"to": "under_review"}, format="json")
    api.as_(users["reviewer"]).post(f"/api/v1/reports/{r.pk}/transition/", {"to": "verified"}, format="json")
    res = api.as_(users["reviewer"]).post(f"/api/v1/reports/{r.pk}/transition/", {"to": "referred"}, format="json")
    assert res.status_code == 400
    res = api.as_(users["reviewer"]).post(f"/api/v1/reports/{r.pk}/transition/",
                                          {"to": "referred", "agency": ref["roads"].pk}, format="json")
    assert res.status_code == 200 and res.json()["routing_status"] == "manual"


@pytest.mark.django_db
def test_area_scoped_reviewer_cannot_act_outside_area(api, ref, users):
    west = create(api, users["citizen"], ref, 13.12, 32.87)
    east = create(api, users["citizen"], ref, 13.18, 32.87)
    rv = users["reviewer_east"]
    assert api.as_(rv).post(f"/api/v1/reports/{west.pk}/transition/", {"to": "under_review"}, format="json").status_code == 403
    assert api.as_(rv).post(f"/api/v1/reports/{east.pk}/transition/", {"to": "under_review"}, format="json").status_code == 200
    q = api.as_(rv).get("/api/v1/reports/queue/", {"queue": "review"}).json()["results"]
    assert {x["id"] for x in q} == {east.pk}


@pytest.mark.django_db
def test_agency_portal_only_shows_own_referrals(api, ref, users):
    r = create(api, users["citizen"], ref, 13.12, 32.87, "garbage")  # → النظافة
    for to in ("under_review", "verified", "referred"):
        api.as_(users["reviewer"]).post(f"/api/v1/reports/{r.pk}/transition/", {"to": to}, format="json")
    mine = api.as_(users["clean_staff"]).get("/api/v1/reports/agency/").json()["results"]
    other = api.as_(users["roads_staff"]).get("/api/v1/reports/agency/").json()["results"]
    assert [x["id"] for x in mine] == [r.pk] and other == []
    assert api.as_(users["citizen"]).get("/api/v1/reports/agency/").status_code == 403
    # citizen cannot use staff queues
    assert api.as_(users["citizen"]).get("/api/v1/reports/queue/").status_code == 403


@pytest.mark.django_db
def test_only_sysadmin_grants_roles_and_changes_are_audited(api, ref, users):
    from apps.core.models import AuditLog
    target = make_user()
    body = {"user": target.pk, "role": Role.REVIEWER, "area": ref["west"].pk}
    assert api.as_(users["coord"]).post("/api/v1/admin/roles/", body, format="json").status_code == 403
    assert api.as_(target).post("/api/v1/admin/roles/", {**body, "user": target.pk}, format="json").status_code == 403
    r = api.as_(users["admin"]).post("/api/v1/admin/roles/", body, format="json")
    assert r.status_code == 201
    assert AuditLog.objects.filter(action="role.granted", actor=users["admin"]).exists()
    # agency staff role needs an agency
    r = api.as_(users["admin"]).post("/api/v1/admin/roles/", {"user": target.pk, "role": Role.AGENCY_STAFF}, format="json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_category_admin_and_new_category_routes(api, ref, users):
    r = api.as_(users["coord"]).post("/api/v1/categories/", {"slug": "trees", "name_ar": "أشجار ساقطة",
                                                              "layer": "services", "hazard_weight": 3}, format="json")
    assert r.status_code == 201
    assert api.as_(users["citizen"]).post("/api/v1/categories/", {"slug": "x", "name_ar": "x"}, format="json").status_code == 403
    cats = [c["slug"] for c in api.as_(None).get("/api/v1/categories/").json()["results"]]
    assert {"garbage", "pothole", "obstacle", "lighting", "water-sewage", "trees"} <= set(cats)
