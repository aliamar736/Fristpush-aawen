from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.audit import audit
from apps.notifications.models import DeviceToken

from . import services
from .models import DeletionRequest, Role, RoleAssignment, User, normalize_phone
from .permissions import HasRole, clear_role_cache, has_role


class RoleAssignmentSerializer(serializers.ModelSerializer):
    area_name = serializers.CharField(source="area.name_ar", read_only=True, default=None)
    agency_name = serializers.CharField(source="agency.name", read_only=True, default=None)
    role_label = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = RoleAssignment
        fields = ["id", "user", "role", "role_label", "area", "area_name", "agency", "agency_name", "active", "granted_at"]
        read_only_fields = ["granted_at"]


class MeSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    pending_deletion = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "phone", "email", "display_name", "preferred_language", "date_joined", "roles",
                  "pending_deletion", "is_demo"]
        read_only_fields = ["id", "username", "phone", "date_joined", "roles", "is_demo"]

    def get_roles(self, obj):
        return RoleAssignmentSerializer(obj.role_assignments.filter(active=True).select_related("area", "agency"),
                                        many=True).data

    def get_pending_deletion(self, obj):
        r = obj.deletion_requests.filter(status=DeletionRequest.PENDING).first()
        return r.scheduled_for if r else None


class OTPRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "otp"

    def post(self, request):
        return Response(services.request_otp(request.data.get("phone", "")))


class OTPVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        user, created = services.verify_otp(request.data.get("phone", ""), request.data.get("code", ""),
                                            request.data.get("display_name", ""))
        return Response({**services.tokens_for(user), "user": MeSerializer(user).data, "created": created})


class PasswordLoginView(APIView):
    """Password login for staff accounts that set a password (citizens use OTP)."""
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        username = request.data.get("username", "")
        try:
            username = normalize_phone(username)
        except ValueError:
            pass
        user = authenticate(request, username=username, password=request.data.get("password", ""))
        if not user:
            raise AuthenticationFailed("بيانات الدخول غير صحيحة.")
        return Response({**services.tokens_for(user), "user": MeSerializer(user).data})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get("refresh")
        if token:
            try:
                RefreshToken(token).blacklist()
            except Exception:  # noqa: BLE001 — already invalid
                pass
        return Response(status=status.HTTP_204_NO_CONTENT)


class SessionsView(APIView):
    """Session management: list active refresh tokens (devices) and revoke them."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        rows = OutstandingToken.objects.filter(user=request.user, expires_at__gt=now, blacklistedtoken__isnull=True)
        return Response([{"jti": t.jti, "created_at": t.created_at, "expires_at": t.expires_at} for t in rows])

    def delete(self, request):
        jti = request.data.get("jti") or request.query_params.get("jti")
        qs = OutstandingToken.objects.filter(user=request.user)
        if jti:
            qs = qs.filter(jti=jti)
        n = 0
        for t in qs:
            _, made = BlacklistedToken.objects.get_or_create(token=t)
            n += int(made)
        audit(request.user, "account.sessions_revoked", request.user, count=n)
        return Response({"revoked": n})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(MeSerializer(request.user).data)

    def patch(self, request):
        s = MeSerializer(request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)


class SetPasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        pw = request.data.get("password", "")
        if request.user.has_usable_password() and not request.user.check_password(request.data.get("current_password", "")):
            raise PermissionDenied("كلمة المرور الحالية غير صحيحة.")
        validate_password(pw, request.user)
        request.user.set_password(pw)
        request.user.save()
        audit(request.user, "account.password_set", request.user)
        return Response(status=204)


class DeletionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        req = services.request_deletion(request.user)
        return Response({"scheduled_for": req.scheduled_for,
                         "message": "سيُحذف حسابك وتُزال بياناتك الشخصية بعد 7 أيام ما لم تلغِ الطلب."}, status=201)

    def delete(self, request):
        n = DeletionRequest.objects.filter(user=request.user, status=DeletionRequest.PENDING).update(
            status=DeletionRequest.CANCELLED)
        return Response({"cancelled": n})


class DeviceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = (request.data.get("token") or "")[:400]
        platform = request.data.get("platform", "android")
        if not token or platform not in ("android", "ios", "web"):
            raise ValidationError({"token": "رمز الجهاز مطلوب."})
        DeviceToken.objects.update_or_create(token=token, defaults={"user": request.user, "platform": platform})
        return Response(status=201)


# ---------- administration of users & roles (sysadmin) ----------
class AdminUserSerializer(serializers.ModelSerializer):
    roles = RoleAssignmentSerializer(source="role_assignments", many=True, read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "phone", "email", "display_name", "is_active", "date_joined", "last_login",
                  "roles", "is_demo"]
        read_only_fields = ["username", "date_joined", "last_login", "is_demo"]


class AdminUserViewSet(viewsets.ModelViewSet):
    permission_classes = [HasRole.of(Role.SYSADMIN, Role.COORDINATOR)]
    serializer_class = AdminUserSerializer
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        qs = User.objects.prefetch_related("role_assignments__area", "role_assignments__agency").order_by("-date_joined")
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(display_name__icontains=q) | Q(phone__icontains=q) | Q(email__icontains=q))
        role = self.request.query_params.get("role")
        if role:
            qs = qs.filter(role_assignments__role=role, role_assignments__active=True).distinct()
        return qs

    def create(self, request):
        """Create a staff/partner account by phone. No password is set: the person signs in with an OTP
        to their own phone (no default passwords)."""
        if not has_role(request.user, Role.SYSADMIN, any_scope=True):
            raise PermissionDenied()
        try:
            phone = normalize_phone(request.data.get("phone", ""))
        except ValueError as exc:
            raise ValidationError({"phone": str(exc)})
        user, created = User.objects.get_or_create(phone=phone, defaults={
            "username": phone, "display_name": request.data.get("display_name", "")[:80],
            "email": request.data.get("email") or None})
        audit(request.user, "admin.user_created" if created else "admin.user_exists", user)
        return Response(AdminUserSerializer(user).data, status=201 if created else 200)

    def partial_update(self, request, *args, **kwargs):
        if not has_role(request.user, Role.SYSADMIN, any_scope=True):
            raise PermissionDenied()
        user = self.get_object()
        if "is_active" in request.data and user.pk == request.user.pk:
            raise ValidationError({"is_active": "لا يمكنك تعطيل حسابك."})
        resp = super().partial_update(request, *args, **kwargs)
        audit(request.user, "admin.user_updated", user, fields=list(request.data.keys()))
        return resp


class RoleAssignmentViewSet(viewsets.ModelViewSet):
    """Only the system administrator grants/revokes roles; every change is audited."""
    permission_classes = [HasRole.of(Role.SYSADMIN)]
    serializer_class = RoleAssignmentSerializer
    queryset = RoleAssignment.objects.select_related("area", "agency", "user")
    filterset_fields = ["user", "role", "area", "agency", "active"]
    http_method_names = ["get", "post", "delete"]

    def get_serializer(self, *args, **kwargs):
        s = super().get_serializer(*args, **kwargs)
        if self.action == "create":
            s.validators = []  # uniqueness handled below (re-activation of revoked roles)
        return s

    def perform_create(self, serializer):
        v = serializer.validated_data
        if v["role"] == Role.AGENCY_STAFF and not v.get("agency"):
            raise ValidationError({"agency": "موظف الجهة يجب ربطه بجهة."})
        existing = RoleAssignment.objects.filter(user=v["user"], role=v["role"], area=v.get("area"),
                                                 agency=v.get("agency")).first()
        if existing:
            existing.active, existing.granted_by, existing.granted_at = True, self.request.user, timezone.now()
            existing.save()
            serializer.instance = existing
            ra = existing
        else:
            ra = serializer.save(granted_by=self.request.user)
        clear_role_cache(ra.user)
        audit(self.request.user, "role.granted", ra, user=ra.user_id, role=ra.role, area=ra.area_id, agency=ra.agency_id)

    def perform_destroy(self, instance):
        if instance.role == Role.SYSADMIN and RoleAssignment.objects.filter(role=Role.SYSADMIN, active=True).count() <= 1:
            raise ValidationError("لا يمكن إزالة آخر مدير نظام.")
        audit(self.request.user, "role.revoked", instance, user=instance.user_id, role=instance.role)
        instance.active = False
        instance.save()
