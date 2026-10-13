"""Priority = danger + harm + place + age + recurrence (+ capped confirmations).
Confirmation/vote counts are capped so they can never dominate the score."""
import math

from django.db import connection
from django.utils import timezone

from apps.core.config import get_setting
from apps.geo.models import Landmark


def near_sensitive_place(point, radius_m):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT name, kind FROM geo_landmark WHERE kind = ANY(%s) AND "
            "ST_DWithin(point::geography, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s) LIMIT 1",
            [list(Landmark.SENSITIVE), point.x, point.y, radius_m])
        return cur.fetchone()


def compute(report):
    w = get_setting("priority_weights")
    parts = {}
    parts["hazard"] = round(report.category.hazard_weight / 5 * w["hazard"] * 5, 2)  # 0..50
    parts["danger"] = report.danger_level * w["danger"]  # 0..24
    place = near_sensitive_place(report.point, w["sensitive_radius_m"]) if report.point else None
    parts["place"] = w["sensitive_place"] if place else 0
    start = report.submitted_at or report.created_at or timezone.now()
    days = max(0.0, (timezone.now() - start).total_seconds() / 86400)
    parts["age"] = round(min(days, w["age_days_cap"]) / w["age_days_cap"] * w["age_max"], 2)
    parts["recurrence"] = min(report.reopen_count * w["recurrence"], w["recurrence_cap"])
    parts["confirmations"] = round(min(math.log2(1 + report.confirmations_count) * 2, w["confirm_cap"]), 2)
    score = round(sum(parts.values()), 2)
    if place:
        parts["place_name"] = place[0]
    return score, parts


def update(report, save=True):
    report.priority_score, report.priority_breakdown = compute(report)
    if save:
        type(report).objects.filter(pk=report.pk).update(priority_score=report.priority_score,
                                                         priority_breakdown=report.priority_breakdown)
    return report
