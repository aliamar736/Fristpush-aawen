from datetime import timedelta

from django.contrib.gis.geos import Polygon
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.services import mask_sensitive
from apps.core.config import get_setting
from apps.core.idempotency import idempotent

from . import services
from .models import RoadAlert


class RoadAlertSerializer(serializers.ModelSerializer):
    lat = serializers.FloatField(source="point.y")
    lng = serializers.FloatField(source="point.x")
    type_label = serializers.CharField(source="get_type_display")
    source_label = serializers.CharField(source="get_source_display")
    verification_label = serializers.CharField(source="get_verification_display")
    status_label = serializers.CharField(source="get_status_display")
    minutes_since_confirmed = serializers.SerializerMethodField()
    is_live = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()

    class Meta:
        model = RoadAlert
        fields = ["id", "type", "type_label", "lat", "lng", "area", "description", "direction", "observed_at",
                  "reported_at", "last_confirmed_at", "expires_at", "source", "source_label", "verification",
                  "verification_label", "status", "status_label", "still_there_count", "cleared_count",
                  "minutes_since_confirmed", "is_live", "is_demo"]

    def get_minutes_since_confirmed(self, a):
        return int((timezone.now() - a.last_confirmed_at).total_seconds() // 60)

    def get_is_live(self, a):
        return a.status == RoadAlert.ACTIVE and a.expires_at > timezone.now()

    def get_description(self, a):
        return mask_sensitive(a.description)


class RoadAlertViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = RoadAlertSerializer

    def get_throttles(self):
        if self.action == "create":
            self.throttle_scope = "road_alert"
        elif self.action == "vote":
            self.throttle_scope = "vote"
        return super().get_throttles()

    def get_queryset(self):
        return RoadAlert.objects.all()

    def list(self, request):
        """Live alerts by default (status=active and not expired). ?history=1 includes expired/cleared/late."""
        now = timezone.now()
        qs = RoadAlert.objects.all()
        if request.query_params.get("history") != "1":
            qs = qs.filter(status=RoadAlert.ACTIVE, expires_at__gt=now)
        else:
            qs = qs.filter(reported_at__gte=now - timedelta(days=2))
        t = request.query_params.get("type")
        if t:
            qs = qs.filter(type__in=t.split(","))
        bbox = request.query_params.get("bbox")
        if bbox:
            try:
                w, s, e, n = (float(x) for x in bbox.split(","))
            except ValueError:
                raise ValidationError({"bbox": "west,south,east,north"})
            qs = qs.filter(point__within=Polygon.from_bbox((w, s, e, n)))
        return Response(RoadAlertSerializer(qs[:1000], many=True).data)

    def retrieve(self, request, pk=None):
        return Response(RoadAlertSerializer(RoadAlert.objects.get(pk=pk)).data)

    @idempotent("road_alert")
    def create(self, request):
        data = dict(request.data)
        if data.get("observed_at"):
            from django.utils.dateparse import parse_datetime
            data["observed_at"] = parse_datetime(str(data["observed_at"]))
            if data["observed_at"] is None:
                raise ValidationError({"observed_at": "تاريخ غير صحيح."})
        for k in ("lat", "lng"):
            if k not in data:
                raise ValidationError({k: "مطلوب."})
        alert, created = services.create_alert(request.user, data)
        body = RoadAlertSerializer(alert).data
        if alert.status == RoadAlert.HISTORICAL:
            body["notice"] = "وصل البلاغ متأخرًا عن وقت الرصد، فسُجّل في السجل ولم يُنشر كحدث مباشر."
        return Response(body, status=201 if created else 200)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def vote(self, request, pk=None):
        alert = services.vote(RoadAlert.objects.get(pk=pk), request.user, request.data.get("vote"))
        return Response(RoadAlertSerializer(alert).data)


class EmergencyInfoView(APIView):
    """The map is NOT an emergency service. Shows official contacts configured by the admin only."""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(get_setting("emergency_notice"))
