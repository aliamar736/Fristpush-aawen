import json

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Point
from django.db import connection
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import HasRole, has_role
from apps.core.audit import audit

from .models import Area, City, Landmark


class CitySerializer(serializers.ModelSerializer):
    lat = serializers.FloatField(source="center.y", read_only=True)
    lng = serializers.FloatField(source="center.x", read_only=True)

    class Meta:
        model = City
        fields = ["id", "name_ar", "name_en", "slug", "lat", "lng", "active"]


class AreaSerializer(serializers.ModelSerializer):
    geometry = serializers.SerializerMethodField()
    centroid = serializers.SerializerMethodField()
    geojson = serializers.JSONField(write_only=True, required=False)

    class Meta:
        model = Area
        fields = ["id", "city", "name_ar", "name_en", "slug", "population", "boundary_source", "active", "geometry",
                  "centroid", "geojson", "is_demo"]
        read_only_fields = ["is_demo"]

    def get_geometry(self, obj):
        if self.context.get("with_geometry"):
            return json.loads(obj.geom.simplify(0.0002, preserve_topology=True).geojson)
        return None

    def get_centroid(self, obj):
        c = obj.geom.point_on_surface
        return {"lat": c.y, "lng": c.x}

    def validate(self, attrs):
        gj = attrs.pop("geojson", None)
        if gj is not None:
            try:
                g = GEOSGeometry(json.dumps(gj.get("geometry", gj)), srid=4326)
            except Exception:  # noqa: BLE001
                raise ValidationError({"geojson": "GeoJSON غير صالح."})
            if g.geom_type == "Polygon":
                g = MultiPolygon(g, srid=4326)
            if g.geom_type != "MultiPolygon" or not g.valid:
                raise ValidationError({"geojson": "يجب أن يكون مضلعًا صالحًا."})
            attrs["geom"] = g
        elif not self.instance:
            raise ValidationError({"geojson": "حدود المنطقة مطلوبة."})
        return attrs


class CityViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    queryset = City.objects.filter(active=True)
    serializer_class = CitySerializer


class AreaViewSet(viewsets.ModelViewSet):
    serializer_class = AreaSerializer
    filterset_fields = ["city", "active"]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "summary", "locate"):
            return [AllowAny()]
        return [HasRole.of(Role.SYSADMIN)()]

    def get_queryset(self):
        return Area.objects.all() if self.action not in ("list", "retrieve") else Area.objects.filter(active=True)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["with_geometry"] = self.request.query_params.get("geometry") == "1" or self.action == "retrieve"
        return ctx

    def perform_create(self, serializer):
        a = serializer.save()
        audit(self.request.user, "area.created", a)

    def perform_update(self, serializer):
        a = serializer.save()
        audit(self.request.user, "area.updated", a)

    @action(detail=False, methods=["get"])
    def locate(self, request):
        try:
            p = Point(float(request.query_params["lng"]), float(request.query_params["lat"]), srid=4326)
        except (KeyError, ValueError):
            raise ValidationError("lat/lng مطلوبة.")
        a = Area.objects.filter(active=True, geom__contains=p).first()
        return Response(AreaSerializer(a).data if a else None)

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        """حومتي — area dashboard."""
        from apps.agencies.models import AgencyAnnouncement, ServiceDirectoryEntry
        from apps.community.models import Initiative, Proposal
        from apps.reports.models import Report, Status
        area = self.get_object()
        now = timezone.now()
        reports = Report.objects.filter(area=area, status__in=Status.PUBLIC)
        by_status = dict(reports.values_list("status").annotate(n=Count("id")).values_list("status", "n"))
        resolved_recent = reports.filter(status=Status.RESOLVED).order_by("-resolved_at")[:5]
        return Response({
            "area": AreaSerializer(area).data,
            "reports": {"open": sum(v for k, v in by_status.items() if k in Status.ACTIVE),
                        "resolved": by_status.get(Status.RESOLVED, 0), "by_status": by_status},
            "initiatives": list(Initiative.objects.filter(area=area, status__in=["approved", "active"])
                                .values("id", "title", "summary", "status")[:5]),
            "announcements": list(AgencyAnnouncement.objects.filter(
                areas=area, published=True, starts_at__lte=now).filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
                .values("id", "title", "body", "agency__name", "starts_at", "ends_at")[:10]),
            "services": list(ServiceDirectoryEntry.objects.filter(Q(area=area) | Q(area__isnull=True), active=True,
                                                                  verified_at__isnull=False)
                             .values("id", "name", "service", "phone", "address", "hours", "verified_at")[:20]),
            "proposals": list(Proposal.objects.filter(area=area).exclude(status="rejected")
                              .values("id", "title", "status", "votes_count")[:5]),
            "recently_resolved": [{"id": r.pk, "tracking_number": r.tracking_number,
                                   "category": r.category.name_ar, "resolved_at": r.resolved_at}
                                  for r in resolved_recent],
        })


class LandmarkSerializer(serializers.ModelSerializer):
    lat = serializers.FloatField(source="point.y", read_only=True)
    lng = serializers.FloatField(source="point.x", read_only=True)

    class Meta:
        model = Landmark
        fields = ["id", "name", "kind", "lat", "lng", "area", "verified"]


class LandmarkViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = LandmarkSerializer
    queryset = Landmark.objects.all()

    @action(detail=False, methods=["get"])
    def near(self, request):
        try:
            lat, lng = float(request.query_params["lat"]), float(request.query_params["lng"])
        except (KeyError, ValueError):
            raise ValidationError("lat/lng مطلوبة.")
        with connection.cursor() as cur:
            cur.execute("SELECT id, ST_Distance(point::geography, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography) d "
                        "FROM geo_landmark WHERE ST_DWithin(point::geography, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, 400) "
                        "ORDER BY d LIMIT 5", [lng, lat, lng, lat])
            rows = cur.fetchall()
        by_id = {l.pk: l for l in Landmark.objects.filter(pk__in=[r[0] for r in rows])}
        return Response([{**LandmarkSerializer(by_id[i]).data, "distance_m": round(d)} for i, d in rows])


class PlaceProfileView(APIView):
    """ملف المكان — history of problems and works linked to a location."""
    permission_classes = [AllowAny]

    def get(self, request):
        from apps.community.models import Initiative
        from apps.reports.models import Report, Status
        from apps.reports.serializers import PublicReportSerializer
        try:
            lat, lng = float(request.query_params["lat"]), float(request.query_params["lng"])
        except (KeyError, ValueError):
            raise ValidationError("lat/lng مطلوبة.")
        radius = min(float(request.query_params.get("radius", 60)), 300)
        with connection.cursor() as cur:
            cur.execute("SELECT id FROM reports_report WHERE status <> 'draft' AND ST_DWithin(point::geography, "
                        "ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s)", [lng, lat, radius])
            ids = [r[0] for r in cur.fetchall()]
        reports = Report.objects.filter(pk__in=ids).select_related("category", "area", "agency").order_by("-submitted_at")
        inis = Initiative.objects.filter(reports__in=ids).distinct().values("id", "title", "status")
        cats = {}
        for r in reports:
            cats.setdefault(r.category.name_ar, 0)
            cats[r.category.name_ar] += 1
        return Response({
            "radius_m": radius,
            "total_reports": len(ids),
            "recurrences": sum(r.reopen_count for r in reports),
            "by_category": cats,
            "open": sum(1 for r in reports if r.status in Status.ACTIVE),
            "reports": PublicReportSerializer(reports[:50], many=True, context={"request": request}).data,
            "initiatives": list(inis),
        })
