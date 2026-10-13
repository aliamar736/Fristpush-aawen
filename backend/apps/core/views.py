from django.conf import settings
from django.db import connection
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import HasRole, has_role

from .audit import audit
from .config import DEFAULTS, get_setting, set_setting
from .media import blur_regions, create_asset
from .models import AuditLog, MediaAsset


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        db_ok = True
        try:
            with connection.cursor() as c:
                c.execute("SELECT 1")
        except Exception:  # noqa: BLE001
            db_ok = False
        return Response({"status": "ok" if db_ok else "degraded", "db": db_ok, "env": settings.AAWEN_ENV,
                         "time": timezone.now()}, status=200 if db_ok else 503)


class PublicConfigView(APIView):
    """Everything a client needs at start-up (feature flags, integrations status, emergency notice)."""
    permission_classes = [AllowAny]

    def get(self, request):
        from apps.finance.providers import payments_status
        return Response({
            "env": settings.AAWEN_ENV,
            "demo_data_allowed": settings.DEMO_DATA_ALLOWED,
            "features": get_setting("features"),
            "emergency_notice": get_setting("emergency_notice"),
            "payments": payments_status(),
            "finance_policies": get_setting("finance_policies"),
            "integrations": {
                "sms": settings.SMS_PROVIDER, "push": settings.PUSH_PROVIDER, "ai": settings.AI_PROVIDER,
                "transcription": settings.TRANSCRIPTION_PROVIDER, "storage": "s3" if settings.USE_S3 else "local",
            },
            "limits": {"image_mb": settings.AAWEN_MAX_IMAGE_BYTES // 2**20, "audio_mb": settings.AAWEN_MAX_AUDIO_BYTES // 2**20},
        })


class MediaSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = ["uid", "kind", "content_type", "size_bytes", "width", "height", "status", "sensitive_flags",
                  "created_at", "url", "transcript", "moderation_note"]

    def get_url(self, obj):
        return f"/api/v1/media/{obj.uid}/file"


def can_view_original(user, asset):
    if not user or not user.is_authenticated:
        return False
    return asset.owner_id == user.pk or has_role(user, Role.REVIEWER, Role.COORDINATOR, Role.AGENCY_STAFF,
                                                 Role.ACCOUNTANT, Role.FINANCIAL_AUDITOR, any_scope=True)


class MediaViewSet(viewsets.GenericViewSet):
    queryset = MediaAsset.objects.all()
    serializer_class = MediaSerializer
    lookup_field = "uid"
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        if self.action == "create":
            self.throttle_scope = "upload"
        return super().get_throttles()

    def create(self, request):
        f = request.FILES.get("file")
        if not f:
            raise ValidationError({"file": "لم يُرفق ملف."})
        kind = request.data.get("kind", "image")
        asset = create_asset(request.user, f, kind)
        if kind == "image":
            ctx = request.data.get("context", "")
            if ctx in ("accident", "injury"):
                asset.sensitive_flags = ["possible_injured_person"]
                asset.save(update_fields=["sensitive_flags"])
        return Response(MediaSerializer(asset).data, status=201)

    @action(detail=True, methods=["get"], permission_classes=[AllowAny])
    def file(self, request, uid=None):
        asset = MediaAsset.objects.filter(uid=uid).first()
        if not asset:
            raise Http404
        if asset.status == MediaAsset.APPROVED:
            f = asset.public_file if asset.public_file else asset.file
        elif can_view_original(request.user, asset):
            f = asset.file
        else:
            raise Http404  # do not reveal existence of unmoderated media
        if request.query_params.get("original") == "1" and can_view_original(request.user, asset):
            f = asset.file
        resp = FileResponse(f.open("rb"), content_type=asset.content_type)
        resp["Cache-Control"] = "private, max-age=300"
        resp["X-Content-Type-Options"] = "nosniff"
        return resp

    @action(detail=True, methods=["post"], url_path="transcribe")
    def transcribe(self, request, uid=None):
        asset = self.get_object()
        if asset.owner_id != request.user.pk:
            raise PermissionDenied()
        if asset.kind != "audio":
            raise ValidationError("التفريغ للتسجيلات الصوتية فقط.")
        from apps.ai.services import transcribe
        out = transcribe(asset, request.user)
        if out is None:
            return Response({"available": False, "message": "التفريغ الآلي غير متاح؛ اكتب الوصف يدويًا."})
        asset.transcript = out["text"]
        asset.save(update_fields=["transcript"])
        return Response({"available": True, **out})


class ModerationViewSet(viewsets.ReadOnlyModelViewSet):
    """Media moderation queue: approve, reject, or blur regions (faces, injured people, plates)."""
    permission_classes = [HasRole.of(Role.REVIEWER, Role.COORDINATOR)]
    serializer_class = MediaSerializer
    lookup_field = "uid"

    def get_queryset(self):
        qs = MediaAsset.objects.exclude(kind=MediaAsset.KIND_DOC).order_by("created_at")
        st = self.request.query_params.get("status", MediaAsset.PENDING)
        return qs.filter(status=st) if st != "all" else qs

    @action(detail=True, methods=["post"])
    def decide(self, request, uid=None):
        asset = self.get_object()
        decision = request.data.get("decision")
        regions = request.data.get("regions") or []
        if decision == "blur":
            if not regions:
                raise ValidationError({"regions": "حدد مناطق الطمس."})
            blur_regions(asset, regions)
            asset.status = MediaAsset.APPROVED
        elif decision == "approve":
            if "possible_injured_person" in asset.sensitive_flags and not request.data.get("confirm_no_injured"):
                raise ValidationError({"confirm_no_injured": "هذه الصورة مُعلَّمة باحتمال وجود مصاب. اطمسها أو أكد خلوها من مصابين وبيانات شخصية."})
            asset.status = MediaAsset.APPROVED
        elif decision == "reject":
            asset.status = MediaAsset.REJECTED
        else:
            raise ValidationError({"decision": "قرار غير صحيح."})
        asset.moderated_by, asset.moderated_at = request.user, timezone.now()
        asset.moderation_note = (request.data.get("note") or "")[:300]
        asset.save()
        audit(request.user, "media.moderated", asset, decision=decision, regions=len(regions))
        return Response(MediaSerializer(asset).data)


class SettingsView(APIView):
    """Admin-tunable settings (road rules, routing tolerance, follow-up days, feature flags...)."""
    permission_classes = [HasRole.of(Role.SYSADMIN, Role.COORDINATOR)]

    def get(self, request):
        return Response({k: get_setting(k) for k in DEFAULTS})

    def patch(self, request):
        if not has_role(request.user, Role.SYSADMIN, any_scope=True):
            raise PermissionDenied("تعديل الإعدادات لمدير النظام.")
        changed = []
        for key, value in request.data.items():
            if key not in DEFAULTS:
                raise ValidationError({key: "إعداد غير معروف."})
            if type(value) is not type(DEFAULTS[key]):
                raise ValidationError({key: "نوع القيمة غير صحيح."})
            set_setting(key, value, request.user)
            changed.append(key)
        audit(request.user, "settings.changed", ("settings", ",".join(changed)), keys=changed, values=request.data)
        return Response({k: get_setting(k) for k in DEFAULTS})


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.__str__", default=None, read_only=True)

    class Meta:
        model = AuditLog
        fields = ["id", "at", "actor", "actor_name", "action", "target_type", "target_id", "data", "ip"]


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [HasRole.of(Role.SYSADMIN, Role.FINANCIAL_AUDITOR)]
    serializer_class = AuditLogSerializer
    filterset_fields = ["action", "target_type", "target_id", "actor"]

    def get_queryset(self):
        qs = AuditLog.objects.select_related("actor")
        if not has_role(self.request.user, Role.SYSADMIN, any_scope=True):
            qs = qs.filter(action__startswith="finance.")
        prefix = self.request.query_params.get("prefix")
        if prefix:
            qs = qs.filter(action__startswith=prefix)
        return qs
