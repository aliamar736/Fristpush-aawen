"""Reference data that is valid in production: categories, skills, Tripoli city. No reports, no people."""
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand

from apps.community.models import Skill
from apps.geo.models import City
from apps.reports.models import Category

CATEGORIES = [
    # slug, ar, en, layer, hazard, icon, followup_days
    ("garbage", "قمامة", "Garbage", "services", 2, "trash", 14),
    ("pothole", "حفر", "Potholes", "services", 4, "pothole", 60),
    ("obstacle", "عوائق", "Obstacles", "services", 3, "cone", 30),
    ("lighting", "إنارة", "Street lighting", "services", 3, "lamp", 30),
    ("water-sewage", "تسرب مياه وصرف صحي", "Water leak & sewage", "services", 4, "drop", 30),
    ("sidewalk", "عائق رصيف أو منحدر", "Sidewalk / ramp barrier", "pedestrian", 3, "wheelchair", 60),
]
SKILLS = [("cleaning", "تنظيف"), ("painting", "دهان"), ("plumbing", "سباكة"), ("electrical", "كهرباء"),
          ("driving", "قيادة ونقل"), ("first-aid", "إسعافات أولية"), ("photography", "تصوير وتوثيق"),
          ("organizing", "تنظيم وتنسيق"), ("carpentry", "نجارة"), ("gardening", "تشجير وزراعة")]


class Command(BaseCommand):
    help = "Seed reference data (idempotent, production-safe)."

    def handle(self, *a, **o):
        for i, (slug, ar, en, layer, hz, icon, fu) in enumerate(CATEGORIES):
            Category.objects.update_or_create(slug=slug, defaults=dict(name_ar=ar, name_en=en, layer=layer,
                                                                       hazard_weight=hz, icon=icon, followup_days=fu,
                                                                       sort_order=(i + 1) * 10))
        for slug, ar in SKILLS:
            Skill.objects.update_or_create(slug=slug, defaults={"name_ar": ar})
        City.objects.update_or_create(slug="tripoli", defaults=dict(name_ar="طرابلس", name_en="Tripoli",
                                                                     center=Point(13.1913, 32.8872, srid=4326)))
        self.stdout.write(self.style.SUCCESS("reference data ok"))
