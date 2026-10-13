from datetime import timedelta

from django.contrib.gis.geos import Point
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, User
from apps.accounts.permissions import HasRole, area_scope_of, has_role
from apps.core.audit import audit
from apps.core.idempotency import idempotent

from . import services
from .models import (BudgetCycle, CarePoint, HelpOffer, Initiative, Need, Proposal, Skill, SurplusOffer,
                     SurveyAssignment, Task, TaskBooking, VolunteerProfile)


class PointField(serializers.Field):
    def to_representation(self, value):
        return {"lat": value.y, "lng": value.x} if value else None

    def to_internal_value(self, data):
        try:
            return Point(float(data["lng"]), float(data["lat"]), srid=4326)
        except (KeyError, TypeError, ValueError):
            raise serializers.ValidationError("موقع غير صحيح.")


class NeedSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    initiative_title = serializers.CharField(source="initiative.title", read_only=True)
    offers_count = serializers.SerializerMethodField()

    class Meta:
        model = Need
        fields = ["id", "initiative", "initiative_title", "kind", "kind_label", "title", "details", "quantity_needed",
                  "quantity_fulfilled", "unit", "is_blocking", "status", "offers_count"]
        read_only_fields = ["quantity_fulfilled", "status"]

    def get_offers_count(self, n):
        return n.offers.exclude(status__in=["declined", "withdrawn"]).count()


class InitiativeSerializer(serializers.ModelSerializer):
    point = PointField(required=False, allow_null=True)
    area_name = serializers.CharField(source="area.name_ar", read_only=True, default=None)
    manager_name = serializers.CharField(source="manager.public_name", read_only=True, default=None)
    needs = NeedSerializer(many=True, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    finance = serializers.SerializerMethodField()
    is_manager = serializers.SerializerMethodField()

    class Meta:
        model = Initiative
        fields = ["id", "title", "summary", "description", "area", "area_name", "point", "status", "status_label",
                  "manager", "manager_name", "starts_at", "ends_at", "funding_target", "funding_deadline", "approved_at",
                  "needs", "reports", "results_summary", "finance", "is_manager", "created_at", "is_demo"]
        read_only_fields = ["status", "manager", "approved_at", "is_demo"]

    def get_finance(self, ini):
        if not self.context.get("detail"):
            return None
        from apps.finance.services import initiative_summary
        return initiative_summary(ini)

    def get_is_manager(self, ini):
        req = self.context.get("request")
        return bool(req and req.user.is_authenticated and ini.manager_id == req.user.pk)


class InitiativeViewSet(viewsets.ModelViewSet):
    serializer_class = InitiativeSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filterset_fields = ["area", "status"]
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        u = self.request.user
        qs = Initiative.objects.select_related("area", "manager").prefetch_related("needs")
        public = Q(status__in=[Initiative.APPROVED, Initiative.ACTIVE, Initiative.COMPLETED])
        if u.is_authenticated:
            if has_role(u, Role.COORDINATOR, any_scope=True):
                return qs
            return qs.filter(public | Q(manager=u))
        return qs.filter(public)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["detail"] = self.action == "retrieve"
        return ctx

    def perform_create(self, s):
        s.save(manager=self.request.user, status=Initiative.DRAFT)

    def perform_update(self, s):
        if not services.can_manage_initiative(self.request.user, s.instance):
            raise PermissionDenied()
        if s.instance.status not in (Initiative.DRAFT, Initiative.APPROVED, Initiative.ACTIVE):
            raise ValidationError("لا يمكن تعديل المبادرة في حالتها الحالية.")
        s.save()

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return Response(InitiativeSerializer(services.submit_initiative(request.user, self.get_object()),
                                             context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        ini = services.decide_initiative(request.user, self.get_object(), bool(request.data.get("approve")),
                                         request.data.get("note", ""))
        return Response(InitiativeSerializer(ini, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="set-status")
    def set_status(self, request, pk=None):
        ini = self.get_object()
        to = request.data.get("status")
        if not services.can_manage_initiative(request.user, ini):
            raise PermissionDenied()
        allowed = {Initiative.APPROVED: {Initiative.ACTIVE, Initiative.CANCELLED},
                   Initiative.ACTIVE: {Initiative.COMPLETED, Initiative.CANCELLED}}
        if to not in allowed.get(ini.status, set()):
            raise ValidationError({"status": "انتقال غير مسموح."})
        ini.status = to
        if "results_summary" in request.data:
            ini.results_summary = request.data["results_summary"]
        ini.save()
        audit(request.user, "initiative.status", ini, to=to)
        return Response(InitiativeSerializer(ini, context={"request": request}).data)

    @action(detail=True, methods=["get"])
    def ledger(self, request, pk=None):
        """Public spending log: disbursements and their results (no personal data)."""
        from apps.finance.models import Disbursement
        ini = self.get_object()
        rows = Disbursement.objects.filter(initiative=ini, status=Disbursement.PAID).order_by("-paid_at")
        return Response([{"id": d.pk, "amount": str(d.amount), "purpose": d.purpose, "payee": d.payee_name,
                          "paid_at": d.paid_at, "result": d.public_result, "has_receipt": bool(d.receipt_id)}
                         for d in rows])


class NeedViewSet(viewsets.ModelViewSet):
    serializer_class = NeedSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filterset_fields = ["initiative", "kind", "status", "is_blocking"]
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        return Need.objects.filter(initiative__status__in=Initiative.ACCEPTING | {Initiative.COMPLETED, Initiative.DRAFT,
                                                                                 Initiative.PENDING}).select_related("initiative")

    def perform_create(self, s):
        if not services.can_manage_initiative(self.request.user, s.validated_data["initiative"]):
            raise PermissionDenied()
        s.save()

    def perform_update(self, s):
        if not services.can_manage_initiative(self.request.user, s.instance.initiative):
            raise PermissionDenied()
        s.save()

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def blocking(self, request):
        """«شن ناقص؟»"""
        qs = services.blocking_needs(request.query_params.get("area"))
        return Response(NeedSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def offer(self, request, pk=None):
        o = services.offer_help(request.user, self.get_object(), request.data.get("message", ""),
                                request.data.get("quantity", 1), request.data.get("kind", "in_kind"),
                                request.data.get("organization_name", ""))
        return Response(HelpOfferSerializer(o).data, status=201)


class HelpOfferSerializer(serializers.ModelSerializer):
    need_title = serializers.CharField(source="need.title", read_only=True)
    initiative = serializers.IntegerField(source="need.initiative_id", read_only=True)
    user_name = serializers.CharField(source="user.public_name", read_only=True)

    class Meta:
        model = HelpOffer
        fields = ["id", "need", "need_title", "initiative", "user_name", "organization_name", "kind", "message",
                  "quantity", "status", "received_at", "created_at"]


class HelpOfferViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = HelpOfferSerializer

    def get_queryset(self):
        u = self.request.user
        if self.request.query_params.get("mine") == "1":
            return HelpOffer.objects.filter(user=u).select_related("need")
        return HelpOffer.objects.filter(Q(user=u) | Q(need__initiative__manager=u)).select_related("need")

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        o = services.decide_offer(request.user, HelpOffer.objects.get(pk=pk), request.data.get("action"))
        return Response(HelpOfferSerializer(o).data)


class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ["id", "slug", "name_ar", "name_en"]


class SkillViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    queryset = Skill.objects.all().order_by("name_ar")
    serializer_class = SkillSerializer
    pagination_class = None


class VolunteerProfileView(APIView):
    """مهاراتي"""
    permission_classes = [IsAuthenticated]

    def _ser(self, p):
        return {"skills": list(p.skills.values_list("id", flat=True)), "availability": p.availability,
                "preferred_areas": list(p.preferred_areas.values_list("id", flat=True)), "preferences": p.preferences,
                "bio": p.bio}

    def get(self, request):
        p, _ = VolunteerProfile.objects.get_or_create(user=request.user)
        return Response(self._ser(p))

    def put(self, request):
        p, _ = VolunteerProfile.objects.get_or_create(user=request.user)
        av = request.data.get("availability", {})
        if not isinstance(av, dict) or any(d not in range(7) for d in av.get("days", [])) or any(
                s not in ("morning", "afternoon", "evening") for s in av.get("slots", [])):
            raise ValidationError({"availability": "صيغة غير صحيحة."})
        p.availability, p.preferences = av, request.data.get("preferences", {})
        p.bio = (request.data.get("bio") or "")[:300]
        p.save()
        p.skills.set(Skill.objects.filter(pk__in=request.data.get("skills", [])))
        from apps.geo.models import Area
        p.preferred_areas.set(Area.objects.filter(pk__in=request.data.get("preferred_areas", [])))
        return Response(self._ser(p))


class TaskSerializer(serializers.ModelSerializer):
    point = PointField(required=False, allow_null=True)
    skill_name = serializers.CharField(source="skill.name_ar", read_only=True, default=None)
    booked = serializers.SerializerMethodField()
    my_booking = serializers.SerializerMethodField()
    owner_name = serializers.CharField(source="owner.public_name", read_only=True, default=None)
    match_reasons = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = ["id", "initiative", "title", "description", "point", "area", "location_text", "starts_at",
                  "duration_minutes", "skill", "skill_name", "owner", "owner_name", "capacity", "status", "booked",
                  "my_booking", "match_reasons", "is_demo"]
        read_only_fields = ["owner", "status", "is_demo"]

    def get_booked(self, t):
        return t.bookings.filter(status__in=TaskBooking.ACTIVE).count()

    def get_my_booking(self, t):
        req = self.context.get("request")
        if not req or not req.user.is_authenticated:
            return None
        b = t.bookings.filter(user=req.user).first()
        return {"id": b.pk, "status": b.status} if b else None

    def get_match_reasons(self, t):
        return getattr(t, "match_reasons", None)


class BookingSerializer(serializers.ModelSerializer):
    task_title = serializers.CharField(source="task.title", read_only=True)
    starts_at = serializers.DateTimeField(source="task.starts_at", read_only=True)
    user_name = serializers.CharField(source="user.public_name", read_only=True)

    class Meta:
        model = TaskBooking
        fields = ["id", "task", "task_title", "starts_at", "user", "user_name", "status", "completion_note", "created_at"]


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filterset_fields = ["initiative", "area", "skill", "status"]
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        qs = Task.objects.select_related("skill", "owner")
        if self.action == "list" and self.request.query_params.get("all") != "1":
            qs = qs.filter(starts_at__gte=timezone.now() - timedelta(hours=12))
        return qs

    def perform_create(self, s):
        ini = s.validated_data.get("initiative")
        if not (has_role(self.request.user, Role.COORDINATOR, Role.AMBASSADOR, any_scope=True)
                or (ini and ini.manager_id == self.request.user.pk and ini.status in Initiative.ACCEPTING)):
            raise PermissionDenied("إنشاء المهام لمسؤولي المبادرات المعتمدة والمنسقين.")
        s.save(owner=self.request.user)

    def perform_update(self, s):
        if not services._task_manager(self.request.user, s.instance):
            raise PermissionDenied()
        s.save()

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    @idempotent("task_booking")
    def book(self, request, pk=None):
        b = services.book_task(request.user, pk)
        return Response(BookingSerializer(b).data, status=201)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def recommended(self, request):
        return Response(TaskSerializer(services.recommend_tasks(request.user), many=True,
                                       context={"request": request}).data)

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated])
    def bookings(self, request, pk=None):
        t = self.get_object()
        if not services._task_manager(request.user, t):
            raise PermissionDenied()
        return Response(BookingSerializer(t.bookings.select_related("user", "task"), many=True).data)


class BookingViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = BookingSerializer

    def get_queryset(self):
        u = self.request.user
        return TaskBooking.objects.filter(Q(user=u) | Q(task__owner=u)).select_related("task", "user")

    @action(detail=False, methods=["get"])
    def mine(self, request):
        return Response(BookingSerializer(TaskBooking.objects.filter(user=request.user).select_related("task"),
                                          many=True).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(BookingSerializer(services.cancel_booking(request.user, TaskBooking.objects.get(pk=pk))).data)

    @action(detail=True, methods=["post"])
    def attendance(self, request, pk=None):
        b = services.mark_attendance(request.user, TaskBooking.objects.get(pk=pk), bool(request.data.get("attended")))
        return Response(BookingSerializer(b).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        b = services.complete_booking(request.user, TaskBooking.objects.get(pk=pk), request.data.get("note", ""),
                                      request.data.get("media", []))
        return Response(BookingSerializer(b).data)


class CarePointSerializer(serializers.ModelSerializer):
    point = PointField()
    area_name = serializers.CharField(source="area.name_ar", read_only=True, default=None)

    class Meta:
        model = CarePoint
        fields = ["id", "name", "host_type", "area", "area_name", "point", "services", "hours", "contact",
                  "verified_at", "active", "is_demo"]
        read_only_fields = ["verified_at", "is_demo"]


class CarePointViewSet(viewsets.ModelViewSet):
    serializer_class = CarePointSerializer
    http_method_names = ["get", "post", "patch"]
    filterset_fields = ["area"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return [HasRole.of(Role.COORDINATOR, Role.AMBASSADOR)()]

    def get_queryset(self):
        qs = CarePoint.objects.select_related("area")
        if not has_role(self.request.user, Role.COORDINATOR, Role.AMBASSADOR, any_scope=True):
            qs = qs.filter(active=True, verified_at__isnull=False)
        return qs

    def perform_create(self, s):
        s.save(verified_at=None)

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        c = self.get_object()
        if not has_role(request.user, Role.COORDINATOR, area=c.area_id):
            raise PermissionDenied("التحقق للمنسق.")
        c.verified_at, c.verified_by = timezone.now(), request.user
        c.save()
        audit(request.user, "carepoint.verified", c)
        return Response(CarePointSerializer(c).data)


class CycleSerializer(serializers.ModelSerializer):
    is_voting_open = serializers.SerializerMethodField()

    class Meta:
        model = BudgetCycle
        fields = ["id", "title", "area", "budget_amount", "budget_source", "voting_opens", "voting_closes", "status",
                  "is_voting_open", "is_demo"]
        read_only_fields = ["is_demo"]

    def get_is_voting_open(self, c):
        return c.voting_open()


class CycleViewSet(viewsets.ModelViewSet):
    serializer_class = CycleSerializer
    queryset = BudgetCycle.objects.all().order_by("-voting_opens")
    http_method_names = ["get", "post", "patch"]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "results"):
            return [AllowAny()]
        return [HasRole.of(Role.COORDINATOR)()]

    def perform_update(self, s):
        c = s.save()
        audit(self.request.user, "budget_cycle.updated", c, fields=list(self.request.data.keys()))

    @action(detail=True, methods=["get"])
    def results(self, request, pk=None):
        return Response(services.cycle_results(self.get_object()))


class ProposalSerializer(serializers.ModelSerializer):
    point = PointField(required=False, allow_null=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    voted = serializers.SerializerMethodField()

    class Meta:
        model = Proposal
        fields = ["id", "cycle", "area", "title", "description", "point", "estimated_cost", "status", "status_label",
                  "feasibility_ok", "permit_ok", "cost_verified", "maintenance_plan", "review_note", "votes_count",
                  "voted", "created_at", "is_demo"]
        read_only_fields = ["status", "feasibility_ok", "permit_ok", "cost_verified", "maintenance_plan", "review_note",
                            "votes_count", "is_demo"]

    def get_voted(self, p):
        req = self.context.get("request")
        return bool(req and req.user.is_authenticated and p.votes.filter(user=req.user).exists())


class ProposalViewSet(viewsets.ModelViewSet):
    serializer_class = ProposalSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filterset_fields = ["cycle", "area", "status"]
    http_method_names = ["get", "post"]

    def get_queryset(self):
        return Proposal.objects.all().order_by("-votes_count", "-created_at")

    def perform_create(self, s):
        s.save(proposer=self.request.user)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        fields = {k: request.data[k] for k in ("feasibility_ok", "permit_ok", "cost_verified", "maintenance_plan",
                                               "review_note") if k in request.data}
        p = services.review_proposal(request.user, self.get_object(), request.data.get("decision"), **fields)
        return Response(ProposalSerializer(p, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def vote(self, request, pk=None):
        services.vote_proposal(request.user, self.get_object())
        return Response(ProposalSerializer(Proposal.objects.get(pk=pk), context={"request": request}).data)


class SurplusSerializer(serializers.ModelSerializer):
    mine = serializers.SerializerMethodField()
    reserved_by_me = serializers.SerializerMethodField()

    class Meta:
        model = SurplusOffer
        fields = ["id", "title", "kind", "quantity", "area", "pickup_location", "pickup_window", "available_until",
                  "status", "mine", "reserved_by_me", "created_at", "is_demo"]
        read_only_fields = ["status", "is_demo"]

    def _u(self):
        req = self.context.get("request")
        return req.user if req and req.user.is_authenticated else None

    def get_mine(self, o):
        return bool(self._u() and o.owner_id == self._u().pk)

    def get_reserved_by_me(self, o):
        return bool(self._u() and o.reserved_by_id == self._u().pk)

    def to_representation(self, o):
        d = super().to_representation(o)
        if not (d["mine"] or d["reserved_by_me"]):
            d["pickup_location"] = "يظهر بعد الحجز"
        return d


class SurplusViewSet(viewsets.ModelViewSet):
    serializer_class = SurplusSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    http_method_names = ["get", "post"]

    def get_queryset(self):
        from apps.core.config import feature_enabled
        qs = SurplusOffer.objects.all().order_by("-created_at")
        if not feature_enabled("surplus_food"):
            qs = qs.exclude(kind="food")
        if self.action == "list":
            u = self.request.user
            mine = Q(owner=u) | Q(reserved_by=u) if u.is_authenticated else Q(pk__in=[])
            qs = qs.filter(Q(status=SurplusOffer.AVAILABLE, available_until__gt=timezone.now()) | mine)
        return qs

    def create(self, request):
        s = SurplusSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        o = services.create_surplus(request.user, s.validated_data)
        return Response(SurplusSerializer(o, context={"request": request}).data, status=201)

    @action(detail=True, methods=["post"])
    def reserve(self, request, pk=None):
        return Response(SurplusSerializer(services.reserve_surplus(request.user, self.get_object()),
                                          context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def handover(self, request, pk=None):
        return Response(SurplusSerializer(services.handover_surplus(request.user, self.get_object(),
                                                                    cancel=bool(request.data.get("cancel"))),
                                          context={"request": request}).data)


class CoverageView(APIView):
    permission_classes = [HasRole.of(Role.COORDINATOR, Role.SYSADMIN, Role.REVIEWER)]

    def get(self, request):
        return Response(services.coverage())


class SurveySerializer(serializers.ModelSerializer):
    area_name = serializers.CharField(source="area.name_ar", read_only=True)
    ambassador_name = serializers.CharField(source="ambassador.public_name", read_only=True)

    class Meta:
        model = SurveyAssignment
        fields = ["id", "area", "area_name", "ambassador", "ambassador_name", "due_at", "instructions", "status",
                  "findings_note", "completed_at", "is_demo"]
        read_only_fields = ["completed_at", "is_demo"]


class SurveyViewSet(viewsets.ModelViewSet):
    serializer_class = SurveySerializer
    permission_classes = [HasRole.of(Role.COORDINATOR, Role.AMBASSADOR)]
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        u = self.request.user
        if has_role(u, Role.COORDINATOR, any_scope=True):
            return SurveyAssignment.objects.select_related("area", "ambassador")
        return SurveyAssignment.objects.filter(ambassador=u).select_related("area")

    def perform_create(self, s):
        if not has_role(self.request.user, Role.COORDINATOR, area=s.validated_data["area"]):
            raise PermissionDenied("التكليف للمنسق.")
        amb = s.validated_data["ambassador"]
        if not has_role(amb, Role.AMBASSADOR, any_scope=True):
            raise ValidationError({"ambassador": "المستخدم ليس سفيرًا."})
        a = s.save(assigned_by=self.request.user)
        from apps.notifications.services import notify
        notify(amb, "survey", f"تكليف مسح ميداني: {a.area.name_ar}", a.instructions, {"survey_id": a.pk})
        audit(self.request.user, "survey.assigned", a)

    def perform_update(self, s):
        a = s.instance
        u = self.request.user
        if a.ambassador_id != u.pk and not has_role(u, Role.COORDINATOR, any_scope=True):
            raise PermissionDenied()
        st = s.validated_data.get("status")
        s.save(completed_at=timezone.now() if st == SurveyAssignment.DONE else a.completed_at)
