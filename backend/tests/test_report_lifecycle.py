"""Section 12: report lifecycle up to verification, objection and reopening; no closure by time."""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from freezegun import freeze_time

from apps.reports import tasks
from apps.reports.models import CompletionCheck, FollowUpReview, Recurrence, Report, Status


def submit(api, user, ref, lng=13.12, lat=32.87, cat="pothole", **extra):
    body = {"category": ref["cats"][cat].pk, "lat": lat, "lng": lng, "description": "حفرة كبيرة قدام البيت",
            "client_id": str(uuid.uuid4()), **extra}
    r = api.as_(user).post("/api/v1/reports/", body, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def go(api, user, rid, to, expect=200, **data):
    r = api.as_(user).post(f"/api/v1/reports/{rid}/transition/", {"to": to, **data}, format="json")
    assert r.status_code == expect, (to, r.status_code, r.content)
    return r.json()


@pytest.mark.django_db
def test_full_lifecycle_with_objection_and_recurrence(api, ref, users, upload):
    u = users
    rep = submit(api, u["citizen"], ref)
    rid = rep["id"]
    assert rep["status"] == Status.SUBMITTED
    assert rep["tracking_number"].startswith("AW-")
    assert rep["agency_name"] == "الطرق"           # routed by city rule
    assert rep["observed_at"] and rep["submitted_at"]

    # citizen cannot verify their own report
    go(api, u["citizen"], rid, Status.UNDER_REVIEW, expect=403)
    go(api, u["reviewer"], rid, Status.UNDER_REVIEW)
    go(api, u["reviewer"], rid, Status.NEEDS_INFO, expect=400)                  # reason required
    go(api, u["reviewer"], rid, Status.NEEDS_INFO, reason="وين بالضبط؟ أضف معلمًا قريبًا")
    r = api.as_(u["citizen"]).post(f"/api/v1/reports/{rid}/add-info/", {"note": "قدام مخبز النور"}, format="json")
    assert r.json()["status"] == Status.UNDER_REVIEW
    go(api, u["reviewer"], rid, Status.VERIFIED)
    out = go(api, u["reviewer"], rid, Status.REFERRED)
    assert out["referral"]["acknowledged_at"] is None                          # referral ≠ acknowledgement
    # another agency's staff cannot acknowledge
    go(api, u["clean_staff"], rid, Status.ACKNOWLEDGED, expect=403)
    go(api, u["roads_staff"], rid, Status.IN_PROGRESS, expect=409)              # must acknowledge first
    out = go(api, u["roads_staff"], rid, Status.ACKNOWLEDGED)
    assert out["referral"]["acknowledged_at"] is not None
    go(api, u["roads_staff"], rid, Status.IN_PROGRESS)
    go(api, u["roads_staff"], rid, Status.WAITING, reason="بانتظار وصول الأسفلت")
    go(api, u["roads_staff"], rid, Status.IN_PROGRESS)
    # done without proof is refused
    go(api, u["roads_staff"], rid, Status.DONE_PENDING, expect=400)
    m = upload(u["roads_staff"])
    r = api.as_(u["roads_staff"]).post(f"/api/v1/reports/{rid}/proof/", {"note": "تم الردم والتسوية", "media": [m]},
                                       format="json")
    assert r.status_code == 200, r.content
    assert r.json()["status"] == Status.DONE_PENDING
    # the executor cannot confirm their own work; resolution needs an independent confirmation
    assert api.as_(u["roads_staff"]).post(f"/api/v1/reports/{rid}/check/", {"verdict": "fixed"}, format="json").status_code == 403
    go(api, u["reviewer"], rid, Status.RESOLVED, expect=400)
    assert api.as_(u["citizen2"]).post(f"/api/v1/reports/{rid}/check/", {"verdict": "fixed"}, format="json").status_code == 200
    # conflicting confirmation → reviewer must write a conflict-review note
    assert api.as_(u["citizen3"]).post(f"/api/v1/reports/{rid}/check/", {"verdict": "not_fixed"}, format="json").status_code == 200
    go(api, u["reviewer"], rid, Status.RESOLVED, expect=400)
    out = go(api, u["reviewer"], rid, Status.RESOLVED, note="زيارة ميدانية: الإصلاح سليم، الاعتراض على جزء خارج النطاق")
    assert out["status"] == Status.RESOLVED
    assert FollowUpReview.objects.filter(report_id=rid, round=1).exists()        # follow-up scheduled

    # objection → disputed → accepted → reopened (new round)
    r = api.as_(u["citizen"]).post(f"/api/v1/reports/{rid}/object/", {"reason": "الحفرة رجعت تتكسر"}, format="json")
    assert r.status_code == 201
    assert Report.objects.get(pk=rid).status == Status.DISPUTED
    obj_id = r.json()["id"]
    r = api.as_(u["reviewer"]).post(f"/api/v1/objections/{obj_id}/decide/", {"accept": True, "note": "تأكدنا ميدانيًا"},
                                    format="json")
    assert r.status_code == 200
    rep = Report.objects.get(pk=rid)
    assert rep.status == Status.REOPENED and rep.resolution_round == 2 and rep.reopen_count == 1


@pytest.mark.django_db
def test_problem_returned_links_previous_fix_and_requires_evidence(api, ref, users, upload):
    u = users
    rid = submit(api, u["citizen"], ref)["id"]
    for to in (Status.UNDER_REVIEW, Status.VERIFIED, Status.REFERRED):
        go(api, u["reviewer"], rid, to)
    go(api, u["coord"], rid, Status.ACKNOWLEDGED, expect=400)  # coordinator must state off-portal evidence
    go(api, u["coord"], rid, Status.ACKNOWLEDGED, note="اتصال هاتفي مع مدير الإدارة")
    go(api, u["coord"], rid, Status.IN_PROGRESS)
    api.as_(u["coord"]).post(f"/api/v1/reports/{rid}/proof/", {"note": "تم", "media": [upload(u["coord"])]}, format="json")
    api.as_(u["citizen2"]).post(f"/api/v1/reports/{rid}/check/", {"verdict": "fixed"}, format="json")
    go(api, u["reviewer"], rid, Status.RESOLVED)
    # without new evidence → refused
    r = api.as_(u["citizen3"]).post(f"/api/v1/reports/{rid}/recurrence/", {"note": "رجعت"}, format="json")
    assert r.status_code == 400
    r = api.as_(u["citizen3"]).post(f"/api/v1/reports/{rid}/recurrence/",
                                    {"note": "رجعت الحفرة بعد المطر", "media": [upload(u["citizen3"])]}, format="json")
    assert r.status_code == 201
    rec = Recurrence.objects.get(report_id=rid)
    assert rec.previous_round == 1 and rec.previous_proof is not None and rec.previous_resolved_at is not None
    rep = Report.objects.get(pk=rid)
    assert rep.status == Status.REOPENED and rep.resolution_round == 2
    assert FollowUpReview.objects.get(report_id=rid, round=1).status == FollowUpReview.RETURNED


@pytest.mark.django_db
def test_reports_never_close_because_time_passed(api, ref, users):
    u = users
    rid = submit(api, u["citizen"], ref)["id"]
    for to in (Status.UNDER_REVIEW, Status.VERIFIED, Status.REFERRED):
        go(api, u["reviewer"], rid, to)
    with freeze_time(timezone.now() + timedelta(days=400)):
        tasks.escalate_unacknowledged()
        tasks.schedule_followups()
        tasks.recompute_priorities()
        from apps.roadnow.tasks import expire_alerts
        expire_alerts()
    rep = Report.objects.get(pk=rid)
    assert rep.status == Status.REFERRED            # still open after 400 days of agency silence
    assert rep.escalated_at is not None             # but escalated to the coordinator
    assert rep.events.filter(kind="escalation").exists()


@pytest.mark.django_db
def test_ai_cannot_change_status_or_close(api, ref, users):
    """AI endpoints are advisory: they never alter status, and the AI module has no access to the workflow."""
    import inspect

    import apps.ai.services as ai
    src = inspect.getsource(ai)
    assert "workflow" not in src and "transition(" not in src and "LedgerEntry" not in src
    rid = submit(api, users["citizen"], ref)["id"]
    r = api.as_(users["citizen"]).post("/api/v1/reports/suggest-category/", {"text": "حاوية زبالة فايضة"}, format="json")
    assert r.json()["suggestion"]["slug"] == "garbage"
    assert Report.objects.get(pk=rid).status == Status.SUBMITTED


@pytest.mark.django_db
def test_report_accepted_without_ai(api, ref, users, settings):
    from apps.core.config import set_setting
    set_setting("features", {"ai_assist": False})
    r = api.as_(users["citizen"]).post("/api/v1/reports/suggest-category/", {"text": "حفرة"}, format="json")
    assert r.json()["suggestion"] is None
    assert submit(api, users["citizen"], ref)["status"] == Status.SUBMITTED


@pytest.mark.django_db
def test_unresolvable_requires_reason_and_coordinator(api, ref, users):
    rid = submit(api, users["citizen"], ref)["id"]
    go(api, users["reviewer"], rid, Status.UNRESOLVABLE, expect=403)
    go(api, users["coord"], rid, Status.UNRESOLVABLE, expect=400)
    out = go(api, users["coord"], rid, Status.UNRESOLVABLE, reason="الموقع ملكية خاصة خارج اختصاص البلدية")
    assert out["status_reason"].startswith("الموقع")


@pytest.mark.django_db
def test_similar_reports_and_confirm_instead_of_duplicate(api, ref, users):
    first = submit(api, users["citizen"], ref, lng=13.1200, lat=32.8700)
    r = api.as_(None).get("/api/v1/reports/similar/", {"lat": 32.8702, "lng": 13.1201,
                                                       "category": ref["cats"]["pothole"].pk})
    res = r.json()["results"]
    assert len(res) == 1 and res[0]["id"] == first["id"] and res[0]["distance_m"] < 40
    far = api.as_(None).get("/api/v1/reports/similar/", {"lat": 32.88, "lng": 13.13}).json()["results"]
    assert far == []
    r = api.as_(users["citizen2"]).post(f"/api/v1/reports/{first['id']}/confirm/", {}, format="json")
    assert r.json()["confirmations_count"] == 1
    assert api.as_(users["citizen2"]).post(f"/api/v1/reports/{first['id']}/confirm/", {}, format="json").status_code == 409
    assert api.as_(users["citizen"]).post(f"/api/v1/reports/{first['id']}/confirm/", {}, format="json").status_code == 409


@pytest.mark.django_db
def test_priority_not_driven_by_votes_alone(api, ref, users):
    from apps.reports import priority
    a = Report.objects.get(pk=submit(api, users["citizen"], ref, cat="pothole", danger_level=3)["id"])
    b = Report.objects.get(pk=submit(api, users["citizen"], ref, cat="garbage", danger_level=0, lng=13.13)["id"])
    Report.objects.filter(pk=b.pk).update(confirmations_count=10_000)
    b.refresh_from_db()
    priority.update(a)
    priority.update(b)
    a.refresh_from_db(); b.refresh_from_db()
    assert b.priority_breakdown["confirmations"] <= 6
    assert a.priority_score > b.priority_score


@pytest.mark.django_db
def test_observed_time_separate_and_not_in_future(api, ref, users):
    obs = (timezone.now() - timedelta(hours=5)).isoformat()
    rep = submit(api, users["citizen"], ref, observed_at=obs)
    assert rep["observed_at"][:16] != rep["submitted_at"][:16]
    bad = (timezone.now() + timedelta(hours=2)).isoformat()
    r = api.as_(users["citizen"]).post("/api/v1/reports/", {"category": ref["cats"]["pothole"].pk, "lat": 32.87,
                                                            "lng": 13.12, "observed_at": bad}, format="json")
    assert r.status_code == 400
