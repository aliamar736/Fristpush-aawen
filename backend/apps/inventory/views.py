from django.db.models import Q
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import has_role
from apps.core.idempotency import idempotent

from . import services
from .models import Reservation, Resource


class ResourceSerializer(serializers.ModelSerializer):
    available_quantity = serializers.IntegerField(read_only=True)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    custodian_name = serializers.CharField(source="custodian.public_name", read_only=True, default=None)
    can_manage = serializers.SerializerMethodField()

    class Meta:
        model = Resource
        fields = ["id", "title", "description", "kind", "kind_label", "unit", "total_quantity", "reserved_quantity",
                  "out_quantity", "consumed_quantity", "available_quantity", "condition", "custodian", "custodian_name",
                  "area", "pickup_location", "initiative", "max_loan_days", "active", "can_manage", "is_demo"]
        read_only_fields = ["reserved_quantity", "out_quantity", "consumed_quantity", "is_demo"]

    def get_can_manage(self, r):
        req = self.context.get("request")
        return bool(req and req.user.is_authenticated and services._can_manage(req.user, r))


class ReservationSerializer(serializers.ModelSerializer):
    resource_title = serializers.CharField(source="resource.title", read_only=True)
    resource_kind = serializers.CharField(source="resource.kind", read_only=True)
    user_name = serializers.CharField(source="user.public_name", read_only=True)
    pickup_location = serializers.CharField(source="resource.pickup_location", read_only=True)

    class Meta:
        model = Reservation
        fields = ["id", "resource", "resource_title", "resource_kind", "user_name", "quantity", "status", "purpose",
                  "pickup_by", "due_return_at", "picked_up_at", "returned_at", "return_condition", "pickup_location",
                  "created_at"]


class ResourceViewSet(viewsets.ModelViewSet):
    """مخزن الخير"""
    serializer_class = ResourceSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filterset_fields = ["kind", "area", "initiative"]
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        qs = Resource.objects.select_related("custodian")
        if self.action == "list":
            qs = qs.filter(active=True)
        return qs.order_by("-created_at")

    def perform_create(self, s):
        if not has_role(self.request.user, Role.COORDINATOR, Role.INITIATIVE_MANAGER, Role.AMBASSADOR, any_scope=True):
            ini = s.validated_data.get("initiative")
            if not (ini and ini.manager_id == self.request.user.pk):
                raise PermissionDenied("إضافة الموارد للمنسقين ومسؤولي المبادرات.")
        s.save(custodian=s.validated_data.get("custodian") or self.request.user)

    def perform_update(self, s):
        if not services._can_manage(self.request.user, s.instance):
            raise PermissionDenied()
        new_total = s.validated_data.get("total_quantity", s.instance.total_quantity)
        used = s.instance.reserved_quantity + s.instance.out_quantity + s.instance.consumed_quantity
        if new_total < used:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"total_quantity": f"لا يمكن أن تقل عن الكمية المستخدمة ({used})."})
        s.save()

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    @idempotent("reservation")
    def reserve(self, request, pk=None):
        r, created = services.reserve(request.user, pk, request.data.get("quantity", 1), request.data.get("purpose", ""),
                                      request.data.get("client_id"))
        return Response(ReservationSerializer(r).data, status=201 if created else 200)

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated])
    def reservations(self, request, pk=None):
        res = self.get_object()
        if not services._can_manage(request.user, res):
            raise PermissionDenied()
        return Response(ReservationSerializer(res.reservations.select_related("user").order_by("-created_at"),
                                              many=True).data)


class ReservationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ReservationSerializer

    def get_queryset(self):
        u = self.request.user
        return Reservation.objects.filter(Q(user=u) | Q(resource__custodian=u)).select_related("resource", "user")

    @action(detail=False, methods=["get"])
    def mine(self, request):
        return Response(ReservationSerializer(Reservation.objects.filter(user=request.user).select_related("resource")
                                              .order_by("-created_at"), many=True).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(ReservationSerializer(services.cancel(request.user, pk)).data)

    @action(detail=True, methods=["post"])
    def pickup(self, request, pk=None):
        return Response(ReservationSerializer(services.confirm_pickup(request.user, pk)).data)

    @action(detail=True, methods=["post"], url_path="return")
    def return_item(self, request, pk=None):
        return Response(ReservationSerializer(services.confirm_return(request.user, pk,
                                                                      request.data.get("condition", "good"))).data)
