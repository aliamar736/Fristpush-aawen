from django.contrib.gis.db import models

from apps.core.models import DemoFlag


class City(DemoFlag):
    name_ar = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80, blank=True)
    slug = models.SlugField(unique=True)
    center = models.PointField(geography=False, srid=4326)
    active = models.BooleanField(default=True)


    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.name_ar

class Area(DemoFlag):
    """A neighbourhood / municipality (حومة / بلدية). Boundaries must come from an authoritative
    source; demo polygons are flagged `boundary_source='approximate'`."""
    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name="areas")
    name_ar = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    slug = models.SlugField()
    geom = models.MultiPolygonField(srid=4326)
    population = models.PositiveIntegerField(null=True, blank=True)
    boundary_source = models.CharField(max_length=40, default="approximate")
    active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("city", "slug")]
        ordering = ["name_ar"]

    def __str__(self):
        return self.name_ar


class Landmark(DemoFlag):
    KINDS = [("school", "مدرسة"), ("hospital", "مستشفى"), ("clinic", "مستوصف"), ("mosque", "جامع"),
             ("market", "سوق"), ("square", "ميدان"), ("other", "معلم")]
    SENSITIVE = {"school", "hospital", "clinic"}
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=KINDS, default="other")
    point = models.PointField(srid=4326)
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.SET_NULL, related_name="landmarks")
    verified = models.BooleanField(default=False)


    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.name
