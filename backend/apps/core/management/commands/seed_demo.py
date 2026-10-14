"""Demo data for development / training. Every row is flagged is_demo=True and labelled «تجريبي».
Refused when DEMO_DATA_ALLOWED is false (production default). Area polygons are APPROXIMATE rectangles.

    python manage.py seed_demo            # create
    python manage.py purge_demo           # remove all demo rows
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, RoleAssignment, User
from apps.agencies.models import Agency, AgencyAnnouncement, JurisdictionRule, ServiceDirectoryEntry
from apps.community.models import (BudgetCycle, CarePoint, Initiative, Need, Proposal, Skill, SurplusOffer, Task,
                                   VolunteerProfile)
from apps.geo.models import Area, City, Landmark
from apps.inventory.models import Resource
from apps.reports import services as rs
from apps.reports import workflow
from apps.reports.models import Category, CompletionCheck, Report, Status
from apps.roadnow.models import RoadAlert

T = "(تجريبي)"
AREAS = [  # slug, name, lng_min, lat_min, lng_max, lat_max, population (approximate demo values)
    ("andalus", "حي الأندلس", 13.10, 32.86, 13.15, 32.90, 90000),
    ("gurji", "قرجي", 13.10, 32.83, 13.15, 32.86, 70000),
    ("old-city", "المدينة القديمة", 13.15, 32.88, 13.185, 32.91, 30000),
    ("dahra", "الظهرة", 13.185, 32.88, 13.21, 32.91, 40000),
    ("ben-ashour", "بن عاشور", 13.15, 32.85, 13.21, 32.88, 60000),
    ("souq-jumaa", "سوق الجمعة", 13.21, 32.86, 13.27, 32.91, 150000),
    ("ain-zara", "عين زارة", 13.21, 32.79, 13.28, 32.85, 110000),
]


def rect(x1, y1, x2, y2):
    return MultiPolygon(Polygon(((x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)), srid=4326), srid=4326)


class Command(BaseCommand):
    help = "Seed clearly-labelled demo data (never in production)."

    def handle(self, *a, **o):
        if settings.IS_PRODUCTION or not settings.DEMO_DATA_ALLOWED:
            raise CommandError("بيانات العرض غير مسموحة في هذه البيئة (DEMO_DATA_ALLOWED=false).")
        call_command("seed_reference")
        with transaction.atomic():
            self._seed()
        self.stdout.write(self.style.SUCCESS("demo data ok — كل السجلات مُعلّمة is_demo"))

    def user(self, phone, name, *roles, area=None, agency=None):
        u, _ = User.objects.get_or_create(phone=phone, defaults={"username": phone, "display_name": name, "is_demo": True})
        for r in roles:
            RoleAssignment.objects.get_or_create(user=u, role=r, area=area, agency=agency)
        return u

    def _seed(self):
        now = timezone.now()
        city = City.objects.get(slug="tripoli")
        areas = {}
        for slug, name, x1, y1, x2, y2, pop in AREAS:
            areas[slug], _ = Area.objects.update_or_create(city=city, slug=slug, defaults=dict(
                name_ar=name, geom=rect(x1, y1, x2, y2), population=pop, boundary_source="approximate-demo",
                is_demo=True))
        cats = {c.slug: c for c in Category.objects.all()}
        clean = Agency.objects.get_or_create(name=f"إدارة النظافة العامة {T}", defaults=dict(
            kind="municipality", city=city, is_linked=True, is_demo=True))[0]
        roads = Agency.objects.get_or_create(name=f"إدارة الطرق والجسور {T}", defaults=dict(
            kind="ministry", city=city, is_linked=True, is_demo=True))[0]
        water = Agency.objects.get_or_create(name=f"شركة المياه والصرف الصحي {T}", defaults=dict(
            kind="utility", city=city, is_linked=False, is_demo=True))[0]
        power = Agency.objects.get_or_create(name=f"شركة الكهرباء {T}", defaults=dict(
            kind="utility", city=city, is_linked=False, is_demo=True))[0]
        east = Agency.objects.get_or_create(name=f"بلدية سوق الجمعة {T}", defaults=dict(
            kind="municipality", city=city, is_linked=True, is_demo=True))[0]
        city_rules = {"garbage": clean, "pothole": roads, "obstacle": roads, "lighting": power,
                      "water-sewage": water, "sidewalk": roads}
        for slug, ag in city_rules.items():
            JurisdictionRule.objects.get_or_create(category=cats[slug], city=city, area=None, agency=ag,
                                                   defaults={"priority": 100})
        # Area-specific override: Souq al-Jumaa municipality handles garbage & obstacles in its area
        for slug in ("garbage", "obstacle"):
            JurisdictionRule.objects.get_or_create(category=cats[slug], area=areas["souq-jumaa"], agency=east,
                                                   defaults={"priority": 10})

        admin = self.user("+218910000001", f"مدير النظام {T}", Role.SYSADMIN)
        reviewer = self.user("+218910000002", f"مراجعة البلاغات {T}", Role.REVIEWER)
        coord = self.user("+218910000003", f"منسق الحومة {T}", Role.COORDINATOR)
        agency_clean = self.user("+218910000004", f"موظف النظافة {T}", Role.AGENCY_STAFF, agency=clean)
        agency_roads = self.user("+218910000005", f"موظف الطرق {T}", Role.AGENCY_STAFF, agency=roads)
        self.user("+218910000006", f"موظف بلدية سوق الجمعة {T}", Role.AGENCY_STAFF, agency=east)
        amb = self.user("+218910000007", f"سفير الحومة {T}", Role.AMBASSADOR, area=areas["andalus"])
        vol = self.user("+218910000008", f"متطوعة {T}", Role.VOLUNTEER)
        manager = self.user("+218910000009", f"مسؤول مبادرة {T}", Role.INITIATIVE_MANAGER)
        self.user("+218910000010", f"المحاسب {T}", Role.ACCOUNTANT)
        self.user("+218910000011", f"المراجع المالي {T}", Role.FINANCIAL_AUDITOR)
        citizen = self.user("+218910000012", f"مواطن {T}")
        citizen2 = self.user("+218910000013", f"مواطنة {T}")
        field = self.user("+218910000014", f"فني ميداني {T}", Role.AGENCY_STAFF, agency=roads)
        prof, _ = VolunteerProfile.objects.get_or_create(user=vol, defaults={
            "availability": {"days": [0, 1, 5], "slots": ["morning", "evening"]}})
        prof.skills.set(Skill.objects.filter(slug__in=["cleaning", "photography"]))
        prof.preferred_areas.set([areas["andalus"], areas["old-city"]])

        Landmark.objects.get_or_create(name=f"مدرسة الأندلس الابتدائية {T}", defaults=dict(
            kind="school", point=Point(13.125, 32.875, srid=4326), area=areas["andalus"], is_demo=True))
        Landmark.objects.get_or_create(name=f"مستوصف الظهرة {T}", defaults=dict(
            kind="clinic", point=Point(13.195, 32.895, srid=4326), area=areas["dahra"], is_demo=True))
        Landmark.objects.get_or_create(name=f"ميدان الشهداء {T}", defaults=dict(
            kind="square", point=Point(13.181, 32.8955, srid=4326), area=areas["old-city"], is_demo=True))

        if Report.objects.filter(is_demo=True).exists():
            return  # reports already seeded
        specs = [
            (citizen, "pothole", 13.1255, 32.8752, "حفرة عميقة قدام المدرسة، السيارات تتفاداها فجأة", 3, "resolved"),
            (citizen, "garbage", 13.2302, 32.8801, "حاوية القمامة فايضة من ثلاث أيام والريحة قوية", 2, "acknowledged"),
            (citizen2, "lighting", 13.1950, 32.8946, "عمودين إنارة طافيين والشارع مظلم بالليل", 2, "referred"),
            (citizen2, "water-sewage", 13.1702, 32.8655, "تسرب مية من الماسورة الرئيسية في الرصيف", 3, "in_progress"),
            (citizen, "obstacle", 13.1405, 32.8455, "ركام بناء مسكّر نص الطريق", 2, "under_review"),
            (citizen2, "sidewalk", 13.1785, 32.8920, "الرصيف عالي وما فيه منحدر للكراسي المتحركة", 2, "verified"),
            (citizen, "garbage", 13.2401, 32.8255, "مكب عشوائي جنب السوق", 2, "submitted"),
            (citizen2, "pothole", 13.2080, 32.8620, "حفر متتالية في الشارع", 2, "done_pending_verification"),
        ]
        for i, (u, cat, lng, lat, desc, danger, target) in enumerate(specs):
            r, _ = rs.create_report(u, {"category": cats[cat].pk, "lat": lat, "lng": lng, "description": desc,
                                        "observed_at": now - timedelta(days=10 - i, hours=3),
                                        "danger_level": danger, "landmark_text": ""})
            Report.objects.filter(pk=r.pk).update(is_demo=True)
            r.refresh_from_db()
            self._advance(r, target, reviewer, coord, agency_clean, agency_roads, field, citizen2 if u == citizen else citizen)
        # bulk map points for clustering demonstration
        import random
        rnd = random.Random(7)
        for i in range(40):
            a = rnd.choice(AREAS)
            r, _ = rs.create_report(rnd.choice([citizen, citizen2]), {
                "category": rnd.choice(list(cats.values())).pk, "lat": rnd.uniform(a[3] + 0.002, a[5] - 0.002),
                "lng": rnd.uniform(a[2] + 0.002, a[4] - 0.002), "description": f"بلاغ تجريبي رقم {i + 1}",
                "observed_at": now - timedelta(days=rnd.randint(1, 40)), "danger_level": rnd.randint(0, 3)})
            Report.objects.filter(pk=r.pk).update(is_demo=True)

        RoadAlert.objects.create(type="accident", point=Point(13.1850, 32.8850, srid=4326), description=f"حادث بين سيارتين {T}",
                                 observed_at=now - timedelta(minutes=10), last_confirmed_at=now - timedelta(minutes=5),
                                 expires_at=now + timedelta(minutes=50), reporter=citizen, is_demo=True,
                                 still_there_count=2, verification="community_confirmed")
        RoadAlert.objects.create(type="congestion", point=Point(13.2050, 32.8700, srid=4326), description=f"زحمة عند الإشارة {T}",
                                 observed_at=now - timedelta(minutes=8), last_confirmed_at=now - timedelta(minutes=8),
                                 expires_at=now + timedelta(minutes=22), reporter=citizen2, is_demo=True)
        RoadAlert.objects.create(type="closure", point=Point(13.1600, 32.8700, srid=4326), description=f"إغلاق للصيانة {T}",
                                 observed_at=now - timedelta(hours=1), last_confirmed_at=now - timedelta(hours=1),
                                 expires_at=now + timedelta(hours=3), reporter=agency_roads, source="agency",
                                 verification="official", is_demo=True)

        ini = Initiative.objects.create(title=f"تنظيف وتشجير شارع الأندلس {T}", summary="حملة سكان الحومة لتنظيف الشارع وزراعة 30 شجرة",
                                        description="مبادرة تجريبية لعرض المنصة.", area=areas["andalus"],
                                        point=Point(13.127, 32.874, srid=4326), status=Initiative.ACTIVE, manager=manager,
                                        funding_target=Decimal("4500"), approved_by=coord, approved_at=now, is_demo=True,
                                        starts_at=now + timedelta(days=5))
        Need.objects.create(initiative=ini, kind="transport", title="شاحنة لنقل المخلفات يوم الحملة", is_blocking=True)
        Need.objects.create(initiative=ini, kind="tools", title="مكانس وأكياس وقفازات", quantity_needed=40, unit="طقم")
        Need.objects.create(initiative=ini, kind="funding", title="شراء الشتلات", quantity_needed=3000, unit="د.ل",
                            is_blocking=True)
        Need.objects.create(initiative=ini, kind="permit", title="إذن البلدية للزراعة على الرصيف", is_blocking=True)
        Initiative.objects.create(title=f"دهان سور المدرسة {T}", summary="بانتظار الاعتماد", area=areas["andalus"],
                                  status=Initiative.PENDING, manager=manager, is_demo=True)
        skills = {s.slug: s for s in Skill.objects.all()}
        Task.objects.create(initiative=ini, title=f"تنظيف الجزء الشمالي من الشارع {T}", area=areas["andalus"],
                            point=Point(13.126, 32.876, srid=4326), location_text="قرب المدرسة",
                            starts_at=(now + timedelta(days=5)).replace(hour=8, minute=0), duration_minutes=180,
                            skill=skills["cleaning"], owner=manager, capacity=12, is_demo=True)
        Task.objects.create(initiative=ini, title=f"توثيق قبل وبعد بالصور {T}", area=areas["andalus"],
                            starts_at=(now + timedelta(days=5)).replace(hour=17, minute=0), duration_minutes=60,
                            skill=skills["photography"], owner=manager, capacity=2, is_demo=True)
        Task.objects.create(title=f"نقل أدوات من المخزن {T}", area=areas["old-city"],
                            starts_at=(now + timedelta(days=3)).replace(hour=10, minute=0), duration_minutes=90,
                            skill=skills["driving"], owner=coord, capacity=1, is_demo=True)
        Resource.objects.create(title=f"عربة يد (كاروسة) {T}", kind="loan", total_quantity=3, custodian=amb,
                                area=areas["andalus"], pickup_location="مخزن الحومة — جنب الجامع", is_demo=True)
        Resource.objects.create(title=f"أكياس قمامة كبيرة {T}", kind="donation", unit="كيس", total_quantity=200,
                                custodian=amb, area=areas["andalus"], pickup_location="مخزن الحومة", is_demo=True,
                                initiative=ini)
        Resource.objects.create(title=f"سلم ألمنيوم {T}", kind="loan", total_quantity=1, custodian=coord,
                                area=areas["old-city"], pickup_location="مقر المنسق", is_demo=True)
        CarePoint.objects.create(name=f"صيدلية الأمل {T}", host_type="صيدلية", area=areas["dahra"],
                                 point=Point(13.196, 32.893, srid=4326), services=["مية للشرب", "إسعافات أولية", "شحن هاتف"],
                                 hours="9 صباحًا – 11 ليلًا", verified_at=now - timedelta(days=12), verified_by=coord, is_demo=True)
        CarePoint.objects.create(name=f"جامع الحومة {T}", host_type="جامع", area=areas["andalus"],
                                 point=Point(13.128, 32.877, srid=4326), services=["مية للشرب", "ظل واستراحة", "دورة مياه"],
                                 hours="من الفجر للعشاء", verified_at=now - timedelta(days=40), verified_by=coord, is_demo=True)
        cyc = BudgetCycle.objects.create(title=f"ميزانية الحومة 2026 {T}", area=areas["andalus"], budget_amount=Decimal("20000"),
                                         budget_source="مخصص تجريبي — ليس ميزانية حقيقية",
                                         voting_opens=now - timedelta(days=2), voting_closes=now + timedelta(days=12),
                                         status=BudgetCycle.VOTING, is_demo=True)
        Proposal.objects.create(cycle=cyc, area=areas["andalus"], proposer=citizen, title=f"إنارة ممر المشاة الخلفي {T}",
                                description="تركيب 6 أعمدة إنارة شمسية", estimated_cost=12000, cost_verified=11500,
                                feasibility_ok=True, permit_ok=True, maintenance_plan="شركة الكهرباء — صيانة سنوية",
                                status=Proposal.ELIGIBLE, reviewed_by=reviewer, is_demo=True)
        Proposal.objects.create(cycle=cyc, area=areas["andalus"], proposer=citizen2, title=f"مقاعد وظل عند محطة الحافلات {T}",
                                description="3 مقاعد ومظلة", estimated_cost=7000, cost_verified=6800, feasibility_ok=True,
                                permit_ok=True, maintenance_plan="متطوعو الحومة", status=Proposal.ELIGIBLE,
                                reviewed_by=reviewer, is_demo=True)
        Proposal.objects.create(cycle=cyc, area=areas["andalus"], proposer=citizen, title=f"ملعب صغير للأطفال {T}",
                                description="تحويل أرض فاضية لملعب", estimated_cost=40000, status=Proposal.REVIEW, is_demo=True)
        SurplusOffer.objects.create(owner=citizen2, title=f"كراسي بلاستيك مستعملة {T}", quantity="8 كراسي",
                                    area=areas["dahra"], pickup_location="شارع الظهرة، عمارة 4", pickup_window="بعد العصر",
                                    available_until=now + timedelta(days=6), is_demo=True)
        ServiceDirectoryEntry.objects.create(name=f"خط بلاغات النظافة {T}", service="نظافة", agency=clean, phone="0000000000",
                                             hours="8–14", verified_at=now - timedelta(days=20), verified_by=coord, is_demo=True)
        ann = AgencyAnnouncement.objects.create(agency=water, title=f"قطع مياه مجدول للصيانة {T}",
                                                body="انقطاع من 9 صباحًا حتى 2 ظهرًا يوم الخميس.", created_by=coord,
                                                ends_at=now + timedelta(days=4), is_demo=True)
        ann.areas.set([areas["andalus"], areas["gurji"]])

    def _advance(self, r, target, reviewer, coord, ag_clean, ag_roads, field, other):
        order = ["submitted", "under_review", "verified", "referred", "acknowledged", "in_progress",
                 "done_pending_verification", "resolved"]
        if target not in order:
            return
        idx = order.index(target)
        agency_user = ag_clean if r.agency and r.agency.name.startswith("إدارة النظافة") else ag_roads
        for step in order[1: idx + 1]:
            r.refresh_from_db()
            if step == "acknowledged":
                if r.agency and not r.agency.is_linked:
                    workflow.transition(r, step, coord, note="تأكيد استلام هاتفي من الجهة (تجريبي)")
                else:
                    from apps.accounts.models import RoleAssignment as RA
                    staff = RA.objects.filter(role=Role.AGENCY_STAFF, agency=r.agency).first()
                    workflow.transition(r, step, staff.user if staff else coord, note="" if staff else "تأكيد خارجي")
            elif step == "in_progress":
                if r.agency and r.agency_id == ag_roads.role_assignments.first().agency_id:
                    r.field_assignee = field
                    r.save()
                workflow.transition(r, step, coord)
            elif step == "done_pending_verification":
                from django.core.files.base import ContentFile

                from apps.core.models import MediaAsset
                img = _demo_jpeg()
                a = MediaAsset(owner=coord, kind="image", content_type="image/jpeg", sha256="demo", status="approved",
                               size_bytes=len(img))
                a.file.save("demo.jpg", ContentFile(img), save=True)
                rs.submit_completion_proof(r, coord, "تم الإصلاح (تجريبي)", [a.uid])
            elif step == "resolved":
                CompletionCheck.objects.create(report=r, round=r.resolution_round, user=other, verdict="fixed",
                                               note="تأكدت بنفسي (تجريبي)")
                workflow.transition(r, step, reviewer, note="تأكيد مستقل من السكان")
            else:
                workflow.transition(r, step, reviewer)


def _demo_jpeg():
    """Illustrative (generated) 'after repair' street image used as demo completion proof."""
    import io
    import random

    from PIL import Image, ImageDraw, ImageFilter
    r = random.Random(5)
    im = Image.new("RGB", (1200, 900), (196, 214, 226))
    d = ImageDraw.Draw(im)
    d.polygon([(0, 900), (480, 260), (720, 260), (1200, 900)], fill=(70, 72, 74))
    for _ in range(3000):
        x, y = r.randint(0, 1199), r.randint(260, 899)
        c = r.randint(60, 90)
        d.point((x, y), fill=(c, c, c))
    for y in range(300, 900, 90):
        d.rectangle((594, y, 606, y + 45), fill=(240, 236, 222))
    d.rectangle((0, 240, 1200, 265), fill=(210, 200, 180))
    d.text((20, 20), "AAWEN DEMO", fill=(18, 63, 70))
    buf = io.BytesIO()
    im.filter(ImageFilter.GaussianBlur(1)).save(buf, "JPEG", quality=85)
    return buf.getvalue()
