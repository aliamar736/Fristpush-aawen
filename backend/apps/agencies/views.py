from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import HasRole, agency_ids_of, has_role
from apps.core.audit import audit

from .models import Agency, AgencyAnnouncement, JurisdictionRule, ServiceDirectoryEntry


class AgencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Agency
        fields = ["id", "name", "kind", "city", "contact_phone", "contact_email", "is_linked", "active", "is_demo"]
        read_only_fields = ["is_demo"]


class RuleSerializer(serializers.ModelSerializer):
    agency_name = serializers.CharField(source="agency.name", read_only=True)
    category_name = serializers.CharField(source="category.name_ar", read_only=True)
    area_name = serializers.CharField(source="area.name_ar", read_only=True, default=None)

    class Meta:
        model = JurisdictionRule
        fields = ["id", "category", "category_name", "area", "area_name", "city", "agency", "agency_name", "priority",
                  "note", "active"]

    def validate(self, attrs):
        if not attrs.get("area") and not attrs.get("city") and not (self.instance and (self.instance.area or self.instance.city)):
            raise serializers.ValidationError("حدد منطقة أو مدينة للقاعدة.")
        return attrs


class AnnouncementSerializer(serializers.ModelSerializer):
    agency_name = serializers.CharField(source="agency.name", read_only=True)

    class Meta:
        model = AgencyAnnouncement
        fields = ["id", "agency", "agency_name", "areas", "title", "body", "starts_at", "ends_at", "published",
                  "created_at", "is_demo"]
        read_only_fields = ["is_demo", "created_at"]


class ServiceEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceDirectoryEntry
        fields = ["id", "name", "service", "agency", "area", "phone", "address", "hours", "verified_at", "active",
                  "is_demo"]
        read_only_fields = ["verified_at", "is_demo"]


class AdminWriteMixin:
    write_roles = (Role.SYSADMIN, Role.COORDINATOR)

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return [HasRole.of(*self.write_roles)()]

    def perform_create(self, serializer):
        obj = serializer.save()
        audit(self.request.user, f"{obj._meta.model_name}.created", obj)

    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request.user, f"{obj._meta.model_name}.updated", obj, fields=list(self.request.data.keys()))


class AgencyViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = Agency.objects.all().order_by("name")
    serializer_class = AgencySerializer
    http_method_names = ["get", "post", "patch"]


class RuleViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = JurisdictionRule.objects.select_related("agency", "category", "area")
    serializer_class = RuleSerializer
    filterset_fields = ["category", "area", "agency", "active"]
    http_method_names = ["get", "post", "patch", "delete"]


class AnnouncementViewSet(viewsets.ModelViewSet):
    serializer_class = AnnouncementSerializer
    filterset_fields = ["agency", "areas"]
    http_method_names = ["get", "post", "patch"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return [HasRole.of(Role.AGENCY_STAFF, Role.COORDINATOR)()]

    def get_queryset(self):
        now = timezone.now()
        qs = AgencyAnnouncement.objects.select_related("agency").prefetch_related("areas")
        if self.request.query_params.get("mine") == "1" and self.request.user.is_authenticated:
            return qs.filter(agency_id__in=agency_ids_of(self.request.user))
        return qs.filter(published=True).filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))

    def _check(self, agency):
        if not (has_role(self.request.user, Role.COORDINATOR, any_scope=True)
                or has_role(self.request.user, Role.AGENCY_STAFF, agency=agency)):
            raise PermissionDenied("يمكنك النشر باسم جهتك فقط.")

    def perform_create(self, serializer):
        self._check(serializer.validated_data["agency"])
        obj = serializer.save(created_by=self.request.user)
        audit(self.request.user, "announcement.created", obj)

    def perform_update(self, serializer):
        self._check(serializer.instance.agency)
        serializer.save()


class ServiceDirectoryViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    serializer_class = ServiceEntrySerializer
    filterset_fields = ["area", "agency"]
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        qs = ServiceDirectoryEntry.objects.all().order_by("service", "name")
        if self.action == "list" and not has_role(self.request.user, Role.COORDINATOR, Role.SYSADMIN, any_scope=True):
            qs = qs.filter(active=True, verified_at__isnull=False)
        return qs

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        e = self.get_object()
        e.verified_at, e.verified_by = timezone.now(), request.user
        e.save()
        audit(request.user, "service_directory.verified", e)
        return Response(ServiceEntrySerializer(e).data)
