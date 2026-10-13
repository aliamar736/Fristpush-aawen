"""AI assistance (advisory only).

Capabilities: category suggestion, audio transcription, similarity hints, sensitive-data warnings.
Hard limits (enforced by design + tests): this module never changes report status, never verifies
incidents, never closes reports, never moves money. Every feature has a manual path when AI is off."""
import json
import logging
import re
import urllib.request

from django.conf import settings

from apps.core.config import feature_enabled

log = logging.getLogger("aawen.ai")

DEFAULT_KEYWORDS = {
    "garbage": ["قمامة", "زبالة", "كناسة", "نفايات", "قمايم", "حاوية", "صندوق زبالة", "ريحة", "garbage", "trash"],
    "pothole": ["حفرة", "حفر", "جورة", "طريق مكسر", "اسفلت", "زفت", "pothole"],
    "obstacle": ["عائق", "سد", "ركام", "حجر", "سيارة متروكة", "مسكر", "obstacle", "debris"],
    "lighting": ["انارة", "إنارة", "ضو", "ضي", "عمود", "لمبة", "ظلام", "مظلم", "light", "lamp"],
    "water-sewage": ["مية", "ماء", "تسرب", "صرف", "مجاري", "بالوعة", "طفح", "تسريب", "ماسورة", "sewage", "leak"],
    "sidewalk": ["رصيف", "منحدر", "كرسي متحرك", "مشاة", "sidewalk", "ramp", "wheelchair"],
}

_PHONE = re.compile(r"(?:\+?218|00218|0)?[\s-]?9[1-6][\s-]?\d{3}[\s-]?\d{4}\b")
_NID = re.compile(r"\b[12]\d{11}\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PLATE = re.compile(r"\b\d{1,3}\s*[-–]\s*\d{4,6}\b")
_INJURY = ["مصاب", "مصابين", "جريح", "جرحى", "دم", "جثة", "متوفي", "ميت", "injured", "blood", "dead"]
_NAME_HINT = re.compile(r"(اسمه|اسمها|السيد|الحاج)\s+\S+")


def _normalize(text):
    t = (text or "").lower()
    t = re.sub("[إأآا]", "ا", t)
    t = t.replace("ة", "ه").replace("ى", "ي")
    return t


def detect_sensitive(text):
    """Returns flags that require human review before publishing text/media."""
    flags = []
    if not text:
        return flags
    norm = _normalize(text)
    if _PHONE.search(text):
        flags.append("phone_number")
    if _NID.search(text):
        flags.append("national_id")
    if _EMAIL.search(text):
        flags.append("email")
    if _PLATE.search(text):
        flags.append("vehicle_plate")
    if any(_normalize(w) in norm for w in _INJURY):
        flags.append("possible_injury")
    if _NAME_HINT.search(text):
        flags.append("personal_name")
    return flags


def mask_sensitive(text):
    text = _PHONE.sub("[رقم محجوب]", text or "")
    text = _NID.sub("[رقم وطني محجوب]", text)
    text = _EMAIL.sub("[بريد محجوب]", text)
    text = _PLATE.sub("[لوحة محجوبة]", text)
    return _NAME_HINT.sub(lambda m: m.group(1) + " [اسم محجوب]", text)


def _local_category(text, categories):
    norm = _normalize(text)
    scores = []
    for c in categories:
        words = list(c.keywords or []) + DEFAULT_KEYWORDS.get(c.slug, [])
        hits = sum(1 for w in words if w and _normalize(w) in norm)
        if hits:
            scores.append((hits, c))
    scores.sort(key=lambda x: -x[0])
    if not scores:
        return None
    hits, cat = scores[0]
    return {"slug": cat.slug, "category_id": cat.pk, "confidence": min(0.4 + 0.15 * hits, 0.9), "provider": "local"}


def _anthropic_category(text, categories):
    if not settings.ANTHROPIC_API_KEY:
        return None
    options = ", ".join(f"{c.slug} ({c.name_ar})" for c in categories)
    body = {"model": settings.AI_MODEL, "max_tokens": 50,
            "messages": [{"role": "user", "content": (
                "Classify this Libyan street-problem report into exactly one category slug from: "
                f"{options}. Reply with the slug only, or 'unknown'.\n\nReport: {text[:1000]}")}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", method="POST",
                                 data=json.dumps(body).encode(),
                                 headers={"x-api-key": settings.ANTHROPIC_API_KEY,
                                          "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            out = json.loads(resp.read())
        slug = out["content"][0]["text"].strip().split()[0]
    except Exception as exc:  # noqa: BLE001 — AI is optional, fall back silently
        log.info("AI category fallback: %s", exc)
        return None
    for c in categories:
        if c.slug == slug:
            return {"slug": c.slug, "category_id": c.pk, "confidence": 0.75, "provider": "anthropic"}
    return None


def suggest_category(text, user=None):
    from apps.reports.models import Category

    from .models import AiSuggestion
    if not text or not feature_enabled("ai_assist"):
        return None
    cats = list(Category.objects.filter(active=True))
    result = None
    if settings.AI_PROVIDER == "anthropic":
        result = _anthropic_category(text, cats)
    result = result or _local_category(text, cats)
    if result:
        AiSuggestion.objects.create(kind="category", provider=result["provider"], user=user,
                                    input_excerpt=text[:200], output=result)
    return result


def transcribe(asset, user=None):
    """Returns {'text', 'provider'} or None when transcription is unavailable (manual entry stays possible)."""
    from .models import AiSuggestion
    provider = settings.TRANSCRIPTION_PROVIDER
    text = None
    if provider == "simulated":
        text = "[تفريغ تجريبي من المحاكي — ليس نصًا حقيقيًا] يرجى مراجعة التسجيل وكتابة الوصف."
    elif provider == "http" and settings.TRANSCRIPTION_HTTP_URL:
        with asset.file.open("rb") as fh:
            req = urllib.request.Request(settings.TRANSCRIPTION_HTTP_URL, method="POST", data=fh.read(),
                                         headers={"Content-Type": asset.content_type})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = json.loads(resp.read()).get("text")
        except Exception as exc:  # noqa: BLE001
            log.info("transcription failed: %s", exc)
    if not text:
        return None
    AiSuggestion.objects.create(kind="transcript", provider=provider, user=user, output={"text": text[:2000]})
    return {"text": text, "provider": provider, "flags": detect_sensitive(text)}
