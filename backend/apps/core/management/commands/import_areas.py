"""Import area boundaries from a GeoJSON FeatureCollection.
    python manage.py import_areas file.geojson --city tripoli --name-field name_ar --source "بلدية طرابلس 2026"
"""
import json

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from apps.geo.models import Area, City


class Command(BaseCommand):
    def add_arguments(self, p):
        p.add_argument("path")
        p.add_argument("--city", required=True)
        p.add_argument("--name-field", default="name_ar")
        p.add_argument("--population-field", default="population")
        p.add_argument("--source", required=True, help="مصدر الحدود الرسمي")

    def handle(self, *a, **o):
        city = City.objects.filter(slug=o["city"]).first()
        if not city:
            raise CommandError("city not found")
        data = json.load(open(o["path"], encoding="utf-8"))
        n = 0
        for i, f in enumerate(data.get("features", [])):
            g = GEOSGeometry(json.dumps(f["geometry"]), srid=4326)
            if g.geom_type == "Polygon":
                g = MultiPolygon(g, srid=4326)
            if not g.valid:
                g = g.buffer(0)
                if g.geom_type == "Polygon":
                    g = MultiPolygon(g, srid=4326)
            props = f.get("properties", {})
            name = props.get(o["name_field"]) or f"area-{i}"
            slug = slugify(props.get("slug") or props.get("name_en") or name, allow_unicode=True)[:50] or f"area-{i}"
            Area.objects.update_or_create(city=city, slug=slug, defaults=dict(
                name_ar=name, name_en=props.get("name_en", ""), geom=g, population=props.get(o["population_field"]),
                boundary_source=o["source"][:40], is_demo=False))
            n += 1
        self.stdout.write(self.style.SUCCESS(f"imported {n} areas"))
