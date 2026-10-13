"""Admin-tunable settings with safe defaults.  Values are stored in SystemSetting and cached briefly."""
import copy

from django.core.cache import cache

DEFAULTS = {
    # Road-now alert lifetime rules, per alert type (minutes)
    "road_rules": {
        "accident":   {"ttl": 60,  "extend": 30, "max_lifetime": 360,  "stale_after": 45,  "clear_votes": 2},
        "congestion": {"ttl": 30,  "extend": 20, "max_lifetime": 180,  "stale_after": 30,  "clear_votes": 2},
        "closure":    {"ttl": 240, "extend": 120, "max_lifetime": 2880, "stale_after": 180, "clear_votes": 3},
        "obstacle":   {"ttl": 120, "extend": 60, "max_lifetime": 1440, "stale_after": 120, "clear_votes": 2},
    },
    # Distance (m) from an area boundary under which routing is flagged for human review
    "routing_boundary_tolerance_m": 30,
    # Radius (m) and window (days) for "similar nearby reports"
    "similar_radius_m": 75,
    "similar_window_days": 90,
    # Days after resolution when a follow-up check is scheduled (category may override)
    "followup_days_default": 30,
    # Days after referral without acknowledgement before escalating to the coordinator (never closes!)
    "referral_escalation_days": 5,
    # Priority weights — votes/confirmations are capped so they are never the only factor
    "priority_weights": {"hazard": 10, "danger": 8, "sensitive_place": 10, "sensitive_radius_m": 150,
                         "age_max": 10, "age_days_cap": 30, "recurrence": 5, "recurrence_cap": 10,
                         "confirm_cap": 6},
    # Feature flags
    "features": {
        "surplus_food": False,        # needs food-safety procedure + partner before enabling
        "public_registration": True,
        "english_ui": True,
        "ai_assist": True,
    },
    "emergency_notice": {
        "ar": "إذا كان هناك خطر على الحياة اتصل بخدمات الطوارئ الرسمية مباشرة. بلاغ الخريطة لا يرسل إسعافًا ولا فرق طوارئ.",
        "en": "If life is at risk, call official emergency services directly. A map report does not dispatch ambulances or emergency teams.",
        "contacts": [],  # [{"name": "...", "phone": "..."}] — set by admin from verified official sources only
    },
    "finance_policies": {
        "cancellation": "يمكن إلغاء التعهد قبل الدفع في أي وقت. بعد الدفع المؤكد يُطلب الاسترداد عبر الدعم ويُراجع من المحاسب.",
        "surplus": "أي فائض بعد اكتمال المبادرة يُحوّل لاحتياج معلن في نفس الحومة بعد إشعار المساهمين، أو يُسترد عند الطلب.",
        "underfunding": "إذا لم يكتمل التمويل حتى الموعد المعلن تُخيَّر المبادرة بين تقليص النطاق المعلن أو إعادة المبالغ.",
    },
}

_CACHE_KEY = "aawen:setting:{}"


def get_setting(key):
    from .models import SystemSetting
    cached = cache.get(_CACHE_KEY.format(key))
    if cached is not None:
        return cached
    default = copy.deepcopy(DEFAULTS.get(key))
    row = SystemSetting.objects.filter(key=key).first()
    value = row.value if row else default
    if isinstance(default, dict) and isinstance(value, dict):
        merged = default
        merged.update(value)
        value = merged
    cache.set(_CACHE_KEY.format(key), value, 30)
    return value


def set_setting(key, value, user=None):
    from .models import SystemSetting
    if key not in DEFAULTS:
        raise KeyError(key)
    SystemSetting.objects.update_or_create(key=key, defaults={"value": value, "updated_by": user})
    cache.delete(_CACHE_KEY.format(key))


def feature_enabled(name):
    return bool(get_setting("features").get(name, False))
