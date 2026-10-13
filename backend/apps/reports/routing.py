"""Jurisdiction routing: area (PostGIS containment) × category → agency via JurisdictionRule.
Edge cases (outside coverage, overlapping areas, near a boundary, no rule) are flagged for a human."""
from django.db import connection

from apps.agencies.models import JurisdictionRule
from apps.core.config import get_setting
from apps.geo.models import Area

from .models import Report


def locate(point):
    """Returns (areas_containing, near_boundary_areas) for a lon/lat point."""
    tol = float(get_setting("routing_boundary_tolerance_m"))
    sql = """
        SELECT id,
               ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326)) AS inside,
               ST_Distance(ST_Boundary(geom)::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) AS d
        FROM geo_area
        WHERE active AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)
    """
    x, y = point.x, point.y
    with connection.cursor() as cur:
        cur.execute(sql, [x, y, x, y, x, y, tol])
        rows = cur.fetchall()
    inside = [r[0] for r in rows if r[1]]
    near = [(r[0], r[2]) for r in rows if r[2] is not None and r[2] <= tol]
    return inside, near


def find_rule(category_id, area):
    qs = JurisdictionRule.objects.filter(category_id=category_id, active=True, agency__active=True)
    if area is not None:
        rule = qs.filter(area=area).first() or qs.filter(area__isnull=True, city=area.city_id).first()
        return rule
    return None


def route(report: Report, save=True):
    inside, near = locate(report.point)
    candidates = []
    notes = []
    status = Report.ROUTING_AUTO
    area = None
    if len(inside) == 1:
        area = Area.objects.get(pk=inside[0])
    elif len(inside) > 1:
        status = Report.ROUTING_REVIEW
        notes.append("الموقع داخل أكثر من منطقة (تداخل حدود).")
        area = Area.objects.filter(pk__in=inside).order_by("pk").first()
    else:
        status = Report.ROUTING_REVIEW
        notes.append("الموقع خارج المناطق المغطاة.")
    if near and status == Report.ROUTING_AUTO:
        status = Report.ROUTING_REVIEW
        notes.append("الموقع قريب من حد بين منطقتين.")
    for area_id in sorted({a for a in inside} | {a for a, _ in near}):
        a = Area.objects.get(pk=area_id)
        rule = find_rule(report.category_id, a)
        candidates.append({"area_id": a.pk, "area": a.name_ar,
                           "agency_id": rule.agency_id if rule else None,
                           "agency": rule.agency.name if rule else None})
    agency = None
    if area is not None:
        rule = find_rule(report.category_id, area)
        if rule:
            agency = rule.agency
        else:
            status = Report.ROUTING_REVIEW
            notes.append("لا توجد قاعدة اختصاص لهذه الفئة في هذه المنطقة.")
    # If all candidate areas resolve to the same agency, a boundary case is not ambiguous for routing
    if status == Report.ROUTING_REVIEW and area is not None and agency is not None and len(inside) == 1:
        agencies = {c["agency_id"] for c in candidates}
        if agencies == {agency.pk}:
            status = Report.ROUTING_AUTO
            notes.append("قرب الحد لكن الجهة نفسها لكل المناطق المجاورة.")
    report.area = area
    if report.routing_status != Report.ROUTING_MANUAL:
        report.agency = agency
        report.routing_status = status
    report.routing_notes = " ".join(notes)[:300]
    report.routing_candidates = candidates
    if save:
        report.save(update_fields=["area", "agency", "routing_status", "routing_notes", "routing_candidates"])
    return report
