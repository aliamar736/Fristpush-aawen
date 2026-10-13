"""Section 12: duplicate submission after connection loss; privacy, media moderation, uploads."""
import io
import threading
import uuid

import pytest
from django.db import connection

from apps.core.models import MediaAsset
from apps.reports.models import Report


@pytest.mark.django_db
def test_retry_with_same_client_id_returns_same_report(api, ref, users):
    cid = str(uuid.uuid4())
    body = {"category": ref["cats"]["garbage"].pk, "lat": 32.87, "lng": 13.12, "client_id": cid,
            "description": "قمامة"}
    c = api.as_(users["citizen"])
    first = c.post("/api/v1/reports/", body, format="json")
    second = c.post("/api/v1/reports/", body, format="json")             # client retries after timeout
    third = c.post("/api/v1/reports/", body, format="json", HTTP_IDEMPOTENCY_KEY=cid)
    assert first.status_code == 201
    assert second.status_code in (200, 201) and second["Idempotent-Replay"] == "true"
    assert first.json()["id"] == second.json()["id"] == third.json()["id"]
    assert Report.objects.filter(reporter=users["citizen"]).count() == 1
    # a different user with the same client id is a different report
    other = api.as_(users["citizen2"]).post("/api/v1/reports/", body, format="json")
    assert other.status_code == 201 and other.json()["id"] != first.json()["id"]


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_submissions_create_one_report(ref, users):
    """Two in-flight retries of the same draft arrive at the same time (real transactions)."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken
    token = str(RefreshToken.for_user(users["citizen"]).access_token)
    cid = str(uuid.uuid4())
    body = {"category": ref["cats"]["garbage"].pk, "lat": 32.87, "lng": 13.12, "client_id": cid}
    results = []
    barrier = threading.Barrier(4)

    def worker():
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        barrier.wait()
        try:
            r = c.post("/api/v1/reports/", body, format="json")
            results.append((r.status_code, r.json().get("id")))
        finally:
            connection.close()

    ts = [threading.Thread(target=worker) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert Report.objects.filter(reporter=users["citizen"], client_id=cid).count() == 1
    assert len(results) == 4 and all(s in (200, 201) for s, _ in results), results   # every retry gets an answer
    assert len({i for _, i in results}) == 1, results


@pytest.mark.django_db
def test_public_view_hides_reporter_and_unverified_description(api, ref, users):
    r = api.as_(users["citizen"]).post("/api/v1/reports/", {
        "category": ref["cats"]["pothole"].pk, "lat": 32.87, "lng": 13.12, "client_id": str(uuid.uuid4()),
        "description": "اتصلوا بي على 0912345678 اسمه محمد"}, format="json").json()
    pub = api.as_(None).get(f"/api/v1/reports/{r['id']}/").json()
    text = str(pub)
    assert "0912345678" not in text and users["citizen"].display_name not in text and "reporter" not in pub
    assert pub["description"] is None                                       # not public before verification
    for to in ("under_review", "verified"):
        api.as_(users["reviewer"]).post(f"/api/v1/reports/{r['id']}/transition/", {"to": to}, format="json")
    pub = api.as_(None).get(f"/api/v1/reports/{r['id']}/").json()
    assert "0912345678" not in pub["description"] and "[رقم محجوب]" in pub["description"]
    assert "[اسم محجوب]" in pub["description"]
    staff = api.as_(users["reviewer"]).get(f"/api/v1/reports/{r['id']}/").json()
    assert set(staff["sensitive_flags"]) >= {"phone_number", "personal_name"}
    # list endpoint never includes reporter either
    lst = api.as_(None).get("/api/v1/reports/").json()["results"]
    assert all("reporter" not in x and "reporter_name" not in x for x in lst)


@pytest.mark.django_db
def test_media_private_until_moderated_and_blur(api, ref, users, upload):
    uid = upload(users["citizen"], context="accident")
    asset = MediaAsset.objects.get(uid=uid)
    assert asset.status == "pending_review" and "possible_injured_person" in asset.sensitive_flags
    # anonymous / other users cannot fetch unmoderated media
    assert api.as_(None).get(f"/api/v1/media/{uid}/file/").status_code == 404
    assert api.as_(users["citizen2"]).get(f"/api/v1/media/{uid}/file/").status_code == 404
    assert api.as_(users["citizen"]).get(f"/api/v1/media/{uid}/file/").status_code == 200
    # plain approval of a possible-injury image is refused without explicit confirmation
    mod = api.as_(users["reviewer"])
    assert mod.post(f"/api/v1/admin/moderation/{uid}/decide/", {"decision": "approve"}, format="json").status_code == 400
    r = mod.post(f"/api/v1/admin/moderation/{uid}/decide/",
                 {"decision": "blur", "regions": [{"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}]}, format="json")
    assert r.status_code == 200
    asset.refresh_from_db()
    assert asset.status == "approved" and asset.public_file
    public = api.as_(None).get(f"/api/v1/media/{uid}/file/")
    assert public.status_code == 200
    from PIL import Image
    data = b"".join(public.streaming_content)
    img = Image.open(io.BytesIO(data))
    px = img.getpixel((int(img.width * 0.2), int(img.height * 0.2)))
    assert img.size == (800, 600) and px is not None
    assert api.as_(users["citizen"]).post(f"/api/v1/admin/moderation/{uid}/decide/", {"decision": "approve"},
                                          format="json").status_code == 403


@pytest.mark.django_db
def test_upload_strips_exif_and_rejects_bad_files(api, users, settings):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image
    buf = io.BytesIO()
    im = Image.new("RGB", (3000, 2000), (1, 2, 3))
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (32.0, 52.0, 0.0)}  # GPS IFD
    exif[0x010F] = "PhoneMaker"
    im.save(buf, "JPEG", exif=exif.tobytes())
    f = SimpleUploadedFile("gps.jpg", buf.getvalue(), content_type="image/jpeg")
    r = api.as_(users["citizen"]).post("/api/v1/media/", {"file": f, "kind": "image"}, format="multipart")
    assert r.status_code == 201
    a = MediaAsset.objects.get(uid=r.json()["uid"])
    stored = Image.open(a.file.path)
    assert max(stored.size) == 1600 and len(stored.getexif()) == 0
    fake = SimpleUploadedFile("x.jpg", b"not an image at all", content_type="image/jpeg")
    assert api.as_(users["citizen"]).post("/api/v1/media/", {"file": fake, "kind": "image"},
                                          format="multipart").status_code == 400
    settings.AAWEN_MAX_IMAGE_BYTES = 1000
    big = SimpleUploadedFile("b.jpg", buf.getvalue(), content_type="image/jpeg")
    r = api.as_(users["citizen"]).post("/api/v1/media/", {"file": big, "kind": "image"}, format="multipart")
    assert r.status_code == 400 and "حجم" in str(r.json())
    assert api.as_(None).post("/api/v1/media/", {}, format="multipart").status_code == 401


@pytest.mark.django_db
def test_arabic_error_format(api, users):
    r = api.as_(users["citizen"]).post("/api/v1/reports/", {"lat": 999}, format="json")
    body = r.json()
    assert r.status_code == 400 and body["error"]["code"] == "validation_error"
    assert "fields" in body["error"] and body["error"]["message"] == "بعض البيانات غير صحيحة."
    r = api.as_(None).post("/api/v1/reports/", {}, format="json")
    assert r.status_code == 401 and "error" in r.json()
