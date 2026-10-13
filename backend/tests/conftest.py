import itertools

import pytest
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.cache import cache
from django.core.management import call_command
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Role, RoleAssignment, User
from apps.agencies.models import Agency, JurisdictionRule
from apps.geo.models import Area, City
from apps.reports.models import Category

_phones = itertools.count(1000000)


def rect(x1, y1, x2, y2):
    return MultiPolygon(Polygon(((x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)), srid=4326), srid=4326)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def ref(db):
    call_command("seed_reference", verbosity=0)
    city = City.objects.get(slug="tripoli")
    # Two adjacent test areas sharing the boundary at lng = 13.15
    west = Area.objects.create(city=city, name_ar="غرب", slug="west", geom=rect(13.10, 32.85, 13.15, 32.90))
    east = Area.objects.create(city=city, name_ar="شرق", slug="east", geom=rect(13.15, 32.85, 13.20, 32.90))
    cats = {c.slug: c for c in Category.objects.all()}
    clean = Agency.objects.create(name="النظافة", city=city, is_linked=True)
    roads = Agency.objects.create(name="الطرق", city=city, is_linked=True)
    east_muni = Agency.objects.create(name="بلدية الشرق", city=city, is_linked=True)
    for slug in cats:
        JurisdictionRule.objects.create(category=cats[slug], city=city, agency=roads if slug != "garbage" else clean)
    JurisdictionRule.objects.create(category=cats["garbage"], area=east, agency=east_muni, priority=10)
    return {"city": city, "west": west, "east": east, "cats": cats, "clean": clean, "roads": roads,
            "east_muni": east_muni}


def make_user(*roles, area=None, agency=None, name="مستخدم"):
    phone = f"+21891{next(_phones):07d}"
    u = User.objects.create_user(username=phone, phone=phone, display_name=name)
    for r in roles:
        RoleAssignment.objects.create(user=u, role=r, area=area, agency=agency)
    return u


@pytest.fixture
def users(ref):
    return {
        "citizen": make_user(name="مواطن"),
        "citizen2": make_user(name="مواطنة"),
        "citizen3": make_user(name="ساكن"),
        "reviewer": make_user(Role.REVIEWER, name="مراجع"),
        "reviewer_east": make_user(Role.REVIEWER, area=ref["east"], name="مراجع الشرق"),
        "coord": make_user(Role.COORDINATOR, name="منسق"),
        "clean_staff": make_user(Role.AGENCY_STAFF, agency=ref["clean"], name="موظف نظافة"),
        "roads_staff": make_user(Role.AGENCY_STAFF, agency=ref["roads"], name="موظف طرق"),
        "east_staff": make_user(Role.AGENCY_STAFF, agency=ref["east_muni"], name="موظف بلدية الشرق"),
        "accountant": make_user(Role.ACCOUNTANT, name="محاسب"),
        "accountant2": make_user(Role.ACCOUNTANT, name="محاسب 2"),
        "auditor": make_user(Role.FINANCIAL_AUDITOR, name="مراجع مالي"),
        "manager": make_user(Role.INITIATIVE_MANAGER, name="مسؤول مبادرة"),
        "admin": make_user(Role.SYSADMIN, name="مدير"),
        "ambassador": make_user(Role.AMBASSADOR, name="سفير"),
    }


class Api:
    def __init__(self):
        self.client = APIClient()

    def as_(self, user):
        c = APIClient()
        if user is not None:
            c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
        return c


@pytest.fixture
def api():
    return Api()


@pytest.fixture
def image_bytes():
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (200, 100, 50)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def upload(api, image_bytes):
    from django.core.files.uploadedfile import SimpleUploadedFile

    def _up(user, kind="image", data=None, name="p.jpg", context=""):
        f = SimpleUploadedFile(name, data or image_bytes, content_type="image/jpeg")
        r = api.as_(user).post("/api/v1/media/", {"file": f, "kind": kind, "context": context}, format="multipart")
        assert r.status_code == 201, r.content
        return r.json()["uid"]
    return _up


def pt(lng, lat):
    return Point(lng, lat, srid=4326)


@pytest.fixture(autouse=True)
def _run_on_commit_immediately(monkeypatch):
    """Tests run inside a rolled-back transaction, so on_commit hooks would never fire. Execute them
    immediately (only after the surrounding atomic block in production)."""
    from django.db import transaction
    monkeypatch.setattr(transaction, "on_commit", lambda fn, using=None, robust=False: fn())
