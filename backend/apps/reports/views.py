from datetime import timedelta

from django.contrib.gis.geos import Point, Polygon
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from apps.accounts.models import Role, User
from apps.accounts.permissions import HasRole, agency_ids_of, area_scope_of, has_role
from apps.agencies.models import Agency
from apps.core.audit import audit
from apps.core.config import get_setting
from apps.core.idempotency import idempotent

from . import priority, routing, services, workflow
from .models import Category, FollowUpReview, Objection, Report, ReportBundle, ReportEvent, Status
from .serializers import (BundleSerializer, CategorySerializer, CreateReportSerializer, MapReportSerializer,
                          MyReportSerializer, ObjectionSerializer, PublicReportSerializer, ReportDetailSerializer,
                          StaffReportSerializer)


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        qs = Category.objects.all()
        if not has_role(self.request.user, Role.SYSADMIN, Role.COORDINATOR, any_scope=True):
            qs = qs.filter(active=True)
        return qs

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return [HasRole.of(Role.SYSADMIN, Role.COORDINATOR)()]

    def perform_create(self, s):
        c = s.save()
        audit(self.request.user, "category.created", c)

    def perform_update(self, s):
        c = s.save()
        audit(self.request.user, "category.updated", c, fields=list(self.request.data.keys()))


def _staff_view(user, report):
    return (has_role(user, Role.REVIEWER, Role.COORDINATOR, area=report.area_id)
            or (report.agency_id and has_role(user, Role.AGENCY_STAFF, agency=report.agency_id))
            or report.field_assignee_id == getattr(user, "pk", None))


class ReportViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = ReportDetailSerializer
    queryset = Report.objects.select_related("category", "area", "agency").prefetch_related("media__asset")

    def get_throttles(self):
        if self.action == "create":
            self.throttle_scope = "report_submit"
        return super().get_throttles()

    def _public_qs(self):
        qs = self.get_queryset().filter(status__in=Status.PUBLIC)
        p = self.request.query_params
        if p.get("category"):
            qs = qs.filter(category_id__in=p["category"].split(","))
        if p.get("layer"):
            qs = qs.filter(category__layer__in=p["layer"].split(","))
        if p.get("status"):
            wanted = p["status"].split(",")
            if "open" in wanted:
                wanted = list(Status.ACTIVE) + [w for w in wanted if w != "open"]
            qs = qs.filter(status__in=wanted)
        if p.get("area"):
            qs = qs.filter(area_id=p["area"])
        if p.get("since"):
            since = parse_datetime(p["since"]) or (timezone.now() - timedelta(days=int(p["since"]))
                                                   if p["since"].isdigit() else None)
            if since:
                qs = qs.filter(submitted_at__gte=since)
        if p.get("bbox"):
            try:
                w, s, e, n = (float(x) for x in p["bbox"].split(","))
                qs = qs.filter(point__within=Polygon.from_bbox((w, s, e, n)))
            except ValueError:
                raise ValidationError({"bbox": "صيغة bbox: west,south,east,north"})
        if p.get("demo") == "0":
            qs = qs.filter(is_demo=False)
        return qs

    def list(self, request):
        qs = self._public_qs()
        if request.query_params.get("format_") == "map" or request.query_params.get("view") == "map":
            qs = qs.order_by("-submitted_at")[:3000]
            return Response(MapReportSerializer(qs, many=True).data)
        page = self.paginate_queryset(qs.order_by("-submitted_at"))
        return self.get_paginated_response(PublicReportSerializer(page, many=True, context={"request": request}).data)

    def retrieve(self, request, pk=None):
        r = self.get_object()
        user = request.user
        if r.status == Status.DRAFT and r.reporter_id != getattr(user, "pk", None):
            raise PermissionDenied()
        if user.is_authenticated and _staff_view(user, r):
            ser = StaffReportSerializer
        elif user.is_authenticated and r.reporter_id == user.pk:
            ser = MyReportSerializer
        else:
            ser = ReportDetailSerializer
        return Response(ser(r, context={"request": request}).data)

    def get_object(self):
        obj = Report.objects.select_related("category", "area", "agency").filter(pk=self.kwargs["pk"]).first()
        if obj is None:
            from django.http import Http404
            raise Http404
        return obj

    @idempotent("report")
    def create(self, request):
        s = CreateReportSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        submit = data.pop("submit", True)
        report, created = services.create_report(request.user, data, submit=submit)
        body = MyReportSerializer(report, context={"request": request}).data
        body["created"] = created
        return Response(body, status=201 if created else 200)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def submit(self, request, pk=None):
        r = self.get_object()
        workflow.transition(r, Status.SUBMITTED, request.user)
        priority.update(r)
        r.refresh_from_db()
        return Response(MyReportSerializer(r, context={"request": request}).data)

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def similar(self, request):
        try:
            pt = Point(float(request.query_params["lng"]), float(request.query_params["lat"]), srid=4326)
        except (KeyError, ValueError):
            raise ValidationError("lat/lng مطلوبة.")
        cat = request.query_params.get("category")
        rows = services.similar_reports(pt, int(cat) if cat else None)
        out = []
        for r in rows:
            d = PublicReportSerializer(r, context={"request": request}).data
            d["distance_m"] = r.distance_m
            out.append(d)
        return Response({"radius_m": get_setting("similar_radius_m"), "results": out})

    @action(detail=False, methods=["post"], permission_classes=[AllowAny], url_path="suggest-category")
    def suggest_category(self, request):
        """AI-assisted category hint. Advisory only; the user always chooses manually."""
        from apps.ai.services import detect_sensitive, suggest_category
        text = (request.data.get("text") or "")[:2000]
        user = request.user if request.user.is_authenticated else None
        return Response({"suggestion": suggest_category(text, user), "sensitive_flags": detect_sensitive(text)})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def confirm(self, request, pk=None):
        r = services.confirm_existing(self.get_object(), request.user, request.data.get("note", ""))
        return Response({"confirmations_count": r.confirmations_count})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated], url_path="add-info")
    def add_info(self, request, pk=None):
        r = services.add_info(self.get_object(), request.user, request.data.get("note", ""),
                              request.data.get("media", []))
        r.refresh_from_db()
        return Response(MyReportSerializer(r, context={"request": request}).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def transition(self, request, pk=None):
        r = self.get_object()
        agency = None
        if request.data.get("agency"):
            agency = Agency.objects.filter(pk=request.data["agency"], active=True).first()
            if agency is None:
                raise ValidationError({"agency": "جهة غير موجودة."})
        r, _ = workflow.transition(r, request.data.get("to", ""), request.user,
                                   reason=request.data.get("reason", ""), note=request.data.get("note", ""),
                                   agency=agency, data={k: request.data[k] for k in ("channel", "agency_reference")
                                                        if k in request.data})
        return Response(StaffReportSerializer(r, context={"request": request}).data
                        if _staff_view(request.user, r) else MyReportSerializer(r, context={"request": request}).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def proof(self, request, pk=None):
        services.submit_completion_proof(self.get_object(), request.user, request.data.get("note", ""),
                                         request.data.get("media", []))
        return Response(StaffReportSerializer(self.get_object(), context={"request": request}).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def check(self, request, pk=None):
        services.completion_check(self.get_object(), request.user, request.data.get("verdict"),
                                  request.data.get("note", ""), request.data.get("media", []))
        return Response(ReportDetailSerializer(self.get_object(), context={"request": request}).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def object(self, request, pk=None):
        obj = services.object_to_resolution(self.get_object(), request.user, request.data.get("reason", ""))
        return Response(ObjectionSerializer(obj).data, status=201)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def recurrence(self, request, pk=None):
        rec = services.report_recurrence(self.get_object(), request.user, request.data.get("note", ""),
                                         request.data.get("media", []))
        return Response({"recurrence_id": rec.pk, "status": Status.REOPENED}, status=201)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def assign(self, request, pk=None):
        r = self.get_object()
        if not has_role(request.user, Role.COORDINATOR, area=r.area_id) and not (
                r.agency_id and has_role(request.user, Role.AGENCY_STAFF, agency=r.agency_id)):
            raise PermissionDenied()
        changes = {}
        for field in ("field_assignee", "follow_up_owner"):
            if field in request.data:
                uid = request.data[field]
                u = User.objects.filter(pk=uid, is_active=True).first() if uid else None
                if uid and not u:
                    raise ValidationError({field: "مستخدم غير موجود."})
                if field == "follow_up_owner" and not has_role(request.user, Role.COORDINATOR, area=r.area_id):
                    raise PermissionDenied("تعيين مسؤول المتابعة للمنسق.")
                setattr(r, field, u)
                changes[field] = u.pk if u else None
        r.save()
        ReportEvent.objects.create(report=r, actor=request.user, kind="assignment", data=changes, is_public=False)
        audit(request.user, "report.assigned", r, **changes)
        return Response(StaffReportSerializer(r, context={"request": request}).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def route(self, request, pk=None):
        """Re-run automatic routing, or set agency/area manually (boundary cases)."""
        r = self.get_object()
        if not has_role(request.user, Role.REVIEWER, Role.COORDINATOR, area=r.area_id) and not has_role(
                request.user, Role.COORDINATOR):
            raise PermissionDenied()
        if request.data.get("auto"):
            r.routing_status = Report.ROUTING_PENDING
            routing.route(r)
        else:
            if request.data.get("area"):
                from apps.geo.models import Area
                r.area = Area.objects.get(pk=request.data["area"])
            if request.data.get("agency"):
                r.agency = Agency.objects.get(pk=request.data["agency"])
            r.routing_status = Report.ROUTING_MANUAL
            r.routing_notes = (request.data.get("note") or "توجيه يدوي")[:300]
            r.save()
        ReportEvent.objects.create(report=r, actor=request.user, kind="routing", is_public=False,
                                   data={"area": r.area_id, "agency": r.agency_id, "status": r.routing_status})
        audit(request.user, "report.routed", r, area=r.area_id, agency=r.agency_id, mode=r.routing_status)
        return Response(StaffReportSerializer(r, context={"request": request}).data)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def mine(self, request):
        qs = Report.objects.filter(reporter=request.user).select_related("category", "area", "agency").order_by("-created_at")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(MyReportSerializer(page, many=True, context={"request": request}).data)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def confirmed(self, request):
        qs = Report.objects.filter(confirmations__user=request.user).select_related("category", "area", "agency")
        return Response(PublicReportSerializer(qs[:100], many=True, context={"request": request}).data)

    @action(detail=False, methods=["get"], permission_classes=[HasRole.of(Role.REVIEWER, Role.COORDINATOR)])
    def queue(self, request):
        """Staff work queues, scoped to the reviewer's areas."""
        q = request.query_params.get("queue", "review")
        scope = area_scope_of(request.user, Role.REVIEWER, Role.COORDINATOR)
        qs = Report.objects.select_related("category", "area", "agency").prefetch_related("media__asset")
        if scope is not None:
            qs = qs.filter(Q(area_id__in=scope))
        if q == "review":
            qs = qs.filter(status__in=[Status.SUBMITTED, Status.UNDER_REVIEW, Status.NEEDS_INFO, Status.REOPENED])
        elif q == "routing":
            qs = qs.filter(routing_status=Report.ROUTING_REVIEW).exclude(status__in=[Status.DRAFT, Status.RESOLVED,
                                                                                    Status.UNRESOLVABLE])
        elif q == "to_refer":
            qs = qs.filter(status=Status.VERIFIED)
        elif q == "verify_done":
            qs = qs.filter(status=Status.DONE_PENDING)
        elif q == "disputed":
            qs = qs.filter(status=Status.DISPUTED)
        elif q == "stale":
            days = int(get_setting("referral_escalation_days"))
            qs = qs.filter(status=Status.REFERRED, status_changed_at__lt=timezone.now() - timedelta(days=days))
        elif q == "active":
            qs = qs.filter(status__in=Status.ACTIVE)
        else:
            raise ValidationError({"queue": "قائمة غير معروفة."})
        if request.query_params.get("unscoped_only") == "1" and scope is None:
            qs = qs.filter(area__isnull=True)
        page = self.paginate_queryset(qs.order_by("-priority_score", "submitted_at"))
        return self.get_paginated_response(StaffReportSerializer(page, many=True, context={"request": request}).data)

    @action(detail=False, methods=["get"], permission_classes=[HasRole.of(Role.AGENCY_STAFF)], url_path="agency")
    def agency_inbox(self, request):
        """Agency portal inbox: only reports referred to the staff member's own agency(ies)."""
        ids = agency_ids_of(request.user)
        qs = Report.objects.filter(agency_id__in=ids, referrals__agency_id__in=ids, referrals__active=True).distinct()
        st = request.query_params.get("status")
        if st:
            qs = qs.filter(status__in=st.split(","))
        qs = qs.select_related("category", "area", "agency").order_by("-priority_score")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(StaffReportSerializer(page, many=True, context={"request": request}).data)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def field(self, request):
        qs = Report.objects.filter(field_assignee=request.user).exclude(
            status__in=[Status.RESOLVED, Status.UNRESOLVABLE]).select_related("category", "area", "agency")
        return Response(StaffReportSerializer(qs, many=True, context={"request": request}).data)

    @action(detail=False, methods=["get"], permission_classes=[HasRole.of(Role.REVIEWER, Role.COORDINATOR, Role.SYSADMIN)])
    def stats(self, request):
        from django.db.models import Count
        qs = Report.objects.exclude(status=Status.DRAFT)
        by_status = dict(qs.values_list("status").annotate(n=Count("id")).values_list("status", "n"))
        by_cat = list(qs.values("category__name_ar").annotate(n=Count("id")).order_by("-n"))
        return Response({"by_status": by_status, "by_category": by_cat,
                         "routing_review": qs.filter(routing_status=Report.ROUTING_REVIEW).count(),
                         "total": qs.count(), "demo": qs.filter(is_demo=True).count()})


class ObjectionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ObjectionSerializer

    def get_queryset(self):
        u = self.request.user
        if has_role(u, Role.REVIEWER, Role.COORDINATOR, any_scope=True):
            scope = area_scope_of(u, Role.REVIEWER, Role.COORDINATOR)
            qs = Objection.objects.all() if scope is None else Objection.objects.filter(report__area_id__in=scope)
            if self.request.query_params.get("mine") == "1":
                qs = qs.filter(user=u)
            return qs.select_related("report")
        return Objection.objects.filter(user=u).select_related("report")

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        obj = services.decide_objection(self.get_object(), request.user, bool(request.data.get("accept")),
                                        request.data.get("note", ""))
        return Response(ObjectionSerializer(obj).data)


class FollowUpViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ObjectionSerializer  # schema placeholder; responses are built by _ser()
    permission_classes = [HasRole.of(Role.REVIEWER, Role.COORDINATOR, Role.AMBASSADOR)]

    def get_queryset(self):
        scope = area_scope_of(self.request.user, Role.REVIEWER, Role.COORDINATOR, Role.AMBASSADOR)
        qs = FollowUpReview.objects.select_related("report__category", "report__area")
        if scope is not None:
            qs = qs.filter(Q(report__area_id__in=scope) | Q(assigned_to=self.request.user))
        st = self.request.query_params.get("status", "pending")
        if st == "due":
            qs = qs.filter(status=FollowUpReview.PENDING, due_at__lte=timezone.now())
        elif st != "all":
            qs = qs.filter(status=st)
        return qs.order_by("due_at")

    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response([self._ser(f) for f in page])

    def _ser(self, f):
        return {"id": f.pk, "report": f.report_id, "tracking_number": f.report.tracking_number,
                "category": f.report.category.name_ar, "area": f.report.area.name_ar if f.report.area else None,
                "round": f.round, "due_at": f.due_at, "status": f.status, "note": f.note,
                "lat": f.report.point.y, "lng": f.report.point.x}

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        f = FollowUpReview.objects.get(pk=pk)
        services.complete_followup(f, request.user, bool(request.data.get("ok")), request.data.get("note", ""),
                                   request.data.get("media", []))
        f.refresh_from_db()
        return Response(self._ser(f))


class BundleViewSet(viewsets.ModelViewSet):
    """حزمة حل للحومة: grouping keeps each report's own status untouched."""
    serializer_class = BundleSerializer
    queryset = ReportBundle.objects.select_related("area").prefetch_related("reports__category")
    http_method_names = ["get", "post", "patch"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return [HasRole.of(Role.COORDINATOR)()]

    def perform_create(self, s):
        b = s.save(coordinator=self.request.user)
        for r in b.reports.all():
            ReportEvent.objects.create(report=r, actor=self.request.user, actor_role="coordinator", kind="bundle",
                                       note=f"أُضيف إلى {b.get_kind_display()}: {b.title}", data={"bundle": b.pk})
        audit(self.request.user, "bundle.created", b, reports=list(b.reports.values_list("id", flat=True)))

    def perform_update(self, s):
        before = set(s.instance.reports.values_list("id", flat=True))
        b = s.save()
        for r in b.reports.exclude(id__in=before):
            ReportEvent.objects.create(report=r, actor=self.request.user, actor_role="coordinator", kind="bundle",
                                       note=f"أُضيف إلى {b.get_kind_display()}: {b.title}", data={"bundle": b.pk})
        audit(self.request.user, "bundle.updated", b)

    @action(detail=False, methods=["get"])
    def candidates(self, request):
        """Suggests nearby open reports to bundle (same area, verified/referred/acknowledged)."""
        area = request.query_params.get("area")
        qs = Report.objects.filter(status__in=[Status.VERIFIED, Status.REFERRED, Status.ACKNOWLEDGED,
                                               Status.IN_PROGRESS, Status.WAITING])
        if area:
            qs = qs.filter(area_id=area)
        return Response(PublicReportSerializer(qs.select_related("category", "area", "agency")[:200], many=True,
                                               context={"request": request}).data)
