"""Upload validation and processing: type sniffing, size caps, EXIF/GPS stripping, downscaling,
and moderator blur. Original uploads are kept private; only approved derivatives become public."""
import io

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

from .models import MediaAsset

AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/aac", "audio/x-m4a", "audio/wav", "audio/3gpp"}
DOC_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAGIC = {
    b"\x1aE\xdf\xa3": "audio/webm", b"OggS": "audio/ogg", b"ID3": "audio/mpeg", b"RIFF": "audio/wav",
    b"%PDF": "application/pdf",
}


def _sniff(head: bytes):
    for sig, ctype in MAGIC.items():
        if head.startswith(sig):
            return ctype
    if head[4:8] == b"ftyp":
        return "audio/mp4"
    return None


def process_image(data: bytes):
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValidationError({"file": "الملف ليس صورة صالحة."})
    if img.width * img.height > 50_000_000:
        raise ValidationError({"file": "أبعاد الصورة كبيرة جدًا."})
    img = ImageOps.exif_transpose(img)  # apply orientation, then drop all metadata (incl. GPS)
    img = img.convert("RGB")
    img.thumbnail((settings.AAWEN_IMAGE_MAX_SIDE, settings.AAWEN_IMAGE_MAX_SIDE))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=80, optimize=True, progressive=True)
    return out.getvalue(), img.width, img.height


def create_asset(owner, upload, kind):
    data = upload.read()
    limits = {"image": settings.AAWEN_MAX_IMAGE_BYTES, "audio": settings.AAWEN_MAX_AUDIO_BYTES,
              "document": settings.AAWEN_MAX_DOC_BYTES}
    if kind not in limits:
        raise ValidationError({"kind": "نوع غير مدعوم."})
    if len(data) == 0:
        raise ValidationError({"file": "الملف فارغ."})
    if len(data) > limits[kind]:
        raise ValidationError({"file": f"حجم الملف أكبر من الحد المسموح ({limits[kind] // (1024 * 1024)} ميغابايت)."})
    asset = MediaAsset(owner=owner, kind=kind, sha256=MediaAsset.hash_bytes(data))
    if kind == "image":
        jpeg, w, h = process_image(data)
        asset.width, asset.height, asset.content_type = w, h, "image/jpeg"
        asset.file.save("upload.jpg", ContentFile(jpeg), save=False)
        asset.size_bytes = len(jpeg)
    elif kind == "audio":
        ctype = _sniff(data[:16])
        if ctype not in AUDIO_TYPES:
            raise ValidationError({"file": "صيغة الصوت غير مدعومة."})
        asset.content_type = ctype
        asset.size_bytes = len(data)
        asset.file.save("upload." + ctype.split("/")[-1], ContentFile(data), save=False)
    else:
        ctype = _sniff(data[:16])
        if ctype != "application/pdf":
            try:
                jpeg, w, h = process_image(data)
                data, ctype = jpeg, "image/jpeg"
            except ValidationError:
                raise ValidationError({"file": "المستند يجب أن يكون PDF أو صورة."})
        asset.content_type = ctype
        asset.size_bytes = len(data)
        asset.file.save("doc." + ("pdf" if ctype == "application/pdf" else "jpg"), ContentFile(data), save=False)
    asset.save()
    return asset


def blur_regions(asset: MediaAsset, regions, radius=24):
    """regions: list of {x,y,w,h} in 0..1 fractions of image size. Writes a blurred public derivative."""
    if asset.kind != "image":
        raise ValidationError("الطمس متاح للصور فقط.")
    with asset.file.open("rb") as fh:
        img = Image.open(io.BytesIO(fh.read())).convert("RGB")
    for r in regions:
        try:
            x, y, w, h = (float(r[k]) for k in ("x", "y", "w", "h"))
        except (KeyError, TypeError, ValueError):
            raise ValidationError("منطقة طمس غير صالحة.")
        if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
            raise ValidationError("منطقة طمس خارج حدود الصورة.")
        box = (int(x * img.width), int(y * img.height), int(min(1, x + w) * img.width), int(min(1, y + h) * img.height))
        region = img.crop(box)
        # pixelate + blur so the content is not recoverable
        small = region.resize((max(1, region.width // 16), max(1, region.height // 16)))
        region = small.resize(region.size).filter(ImageFilter.GaussianBlur(radius))
        img.paste(region, box)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=80)
    asset.public_file.save("public.jpg", ContentFile(out.getvalue()), save=False)
    asset.blurred_regions = list(regions)
