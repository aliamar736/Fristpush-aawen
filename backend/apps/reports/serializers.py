from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.ai.services import mask_sensitive
from apps.core.models import MediaAsset

from . import workflow
from .models import (Category, CompletionCheck, CompletionProof, Objection, Report, ReportBundle, ReportEvent,
                     ReportMedia, Status)

ROLE_LABELS = {"owner": "المبلّغ", "reviewer": "فريق المراجعة", "coordinator": "المنسق", "agency": "الجهة المختصة",
               "field": "الفريق الميداني", "public": "أحد السكان", "": "النظام"}


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "slug", "name_ar", "name_en", "layer", "hazard_weight", "followup_days", "icon", "keywords",
                  "sort_order", "active"]


class MediaLinkSerializer(serializers.Serializer):
    def to_representation(self, link):
        a = link.asset
        return {"uid": str(a.uid), "kind": a.kind, "role": link.role, "status": a.status,
                "url": f"/api/v1/media/{a.uid}/file", "added_at": link.added_at}


def public_media(report):
    return [MediaLinkSerializer().to_representation(m) for m in report.media.all()
            if m.asset.status == MediaAsset.APPROVED]


class PublicEventSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()
    to_label = serializers.SerializerMethodField()

    class Meta:
        model = ReportEvent
        fields = ["id", "at", "kind", "from_status", "to_status", "to_label", "note", "actor"]

    def get_actor(self, e):
        return ROLE_LABELS.get(e.actor_role, "")

    def get_to_label(self, e):
        return Status.LABELS.get(e.to_status, "")

    def to_representation(self, e):
        d = super().to_representation(e)
        d["note"] = mask_sensitive(d["note"]) if e.kind in ("status", "evidence", "recurrence") else ""
        return d


class PublicReportSerializer(serializers.ModelSerializer):
    """Never exposes the reporter's identity. Description is shown only after human verification
    and with personal data masked."""
    category = serializers.SerializerMethodField()
    lat = serializers.FloatField(source="point.y")
    lng = serializers.FloatField(source="point.x")
    area_name = serializers.CharField(source="area.name_ar", default=None)
    agency_name = serializers.CharField(source="agency.name", default=None)
    status_label = serializers.CharField()
    description = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = ["id", "tracking_number", "category", "status", "status_label", "lat", "lng", "area", "area_name",
                  "agency_name", "landmark_text", "description", "observed_at", "submitted_at", "status_changed_at",
                  "confirmations_count", "reopen_count", "priority_score", "danger_level", "resolved_at", "media",
                  "is_demo"]

    def get_category(self, r):
        return {"id": r.category_id, "slug": r.category.slug, "name": r.category.name_ar, "layer": r.category.layer,
                "icon": r.category.icon}

    def get_description(self, r):
        if r.status in Status.DESCRIPTION_PUBLIC:
            return mask_sensitive(r.description)
        return None

    def get_media(self, r):
        return public_media(r)


class MapReportSerializer(serializers.ModelSerializer):
    lat = serializers.FloatField(source="point.y")
    lng = serializers.FloatField(source="point.x")

    class Meta:
        model = Report
        fields = ["id", "tracking_number", "category_id", "status", "lat", "lng", "submitted_at", "priority_score",
                  "is_demo"]


class ReportDetailSerializer(PublicReportSerializer):
    events = serializers.SerializerMethodField()
    referral = serializers.SerializerMethodField()
    completion = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()
    viewer = serializers.SerializerMethodField()
    open_objections = serializers.SerializerMethodField()

    class Meta(PublicReportSerializer.Meta):
        fields = PublicReportSerializer.Meta.fields + ["events", "referral", "completion", "actions", "viewer",
                                                       "needs_info_question", "status_reason", "resolution_round",
                                                       "open_objections"]

    def _user(self):
        req = self.context.get("request")
        return req.user if req and req.user.is_authenticated else None

    def get_events(self, r):
        return PublicEventSerializer(r.events.filter(is_public=True), many=True).data

    def get_referral(self, r):
        ref = r.referrals.filter(active=True).select_related("agency").first()
        if not ref:
            return None
        return {"agency": ref.agency.name, "referred_at": ref.referred_at, "acknowledged_at": ref.acknowledged_at,
                "agency_linked": ref.agency.is_linked, "channel": ref.channel}

    def get_completion(self, r):
        proofs = CompletionProof.objects.filter(report=r, round=r.resolution_round)
        checks = CompletionCheck.objects.filter(report=r, round=r.resolution_round)
        return {"round": r.resolution_round, "proofs": [{"note": p.note, "at": p.created_at} for p in proofs],
                "checks": {"fixed": checks.filter(verdict="fixed").count(),
                           "not_fixed": checks.filter(verdict="not_fixed").count(),
                           "partial": checks.filter(verdict="partial").count()}}

    def get_actions(self, r):
        u = self._user()
        return workflow.available_actions(u, r) if u else []

    def get_open_objections(self, r):
        return r.objections.filter(status=Objection.OPEN).count()

    def get_viewer(self, r):
        u = self._user()
        if not u:
            return {"authenticated": False}
        kinds = workflow.actor_kinds(u, r)
        return {"authenticated": True, "is_owner": workflow.OWNER in kinds, "kinds": sorted(kinds),
                "confirmed": r.confirmations.filter(user=u).exists(),
                "checked": r.completion_checks.filter(user=u, round=r.resolution_round).exists(),
                "is_executor": CompletionProof.objects.filter(report=r, round=r.resolution_round, submitted_by=u).exists()}


class StaffReportSerializer(ReportDetailSerializer):
    """For reviewers / coordinators / agency staff: adds routing, flags and all media (with moderation state)."""
    reporter_name = serializers.SerializerMethodField()
    all_media = serializers.SerializerMethodField()
    raw_description = serializers.CharField(source="description")
    internal_events = serializers.SerializerMethodField()

    class Meta(ReportDetailSerializer.Meta):
        fields = ReportDetailSerializer.Meta.fields + [
            "reporter_name", "raw_description", "routing_status", "routing_notes", "routing_candidates", "agency",
            "sensitive_flags", "priority_breakdown", "field_assignee", "follow_up_owner", "escalated_at", "all_media",
            "internal_events"]

    def get_reporter_name(self, r):
        return r.reporter.public_name if r.reporter else None

    def get_all_media(self, r):
        return [MediaLinkSerializer().to_representation(m) for m in r.media.select_related("asset")]

    def get_internal_events(self, r):
        return [{"at": e.at, "kind": e.kind, "note": e.note, "actor_role": e.actor_role, "data": e.data}
                for e in r.events.filter(is_public=False)]


class MyReportSerializer(ReportDetailSerializer):
    raw_description = serializers.CharField(source="description")

    class Meta(ReportDetailSerializer.Meta):
        fields = ReportDetailSerializer.Meta.fields + ["raw_description", "client_id"]


class CreateReportSerializer(serializers.Serializer):
    client_id = serializers.UUIDField(required=False)
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.filter(active=True))
    description = serializers.CharField(max_length=2000, allow_blank=True, required=False, default="")
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    location_edited = serializers.BooleanField(required=False, default=False)
    landmark = serializers.IntegerField(required=False, allow_null=True)
    landmark_text = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    observed_at = serializers.DateTimeField(required=False)
    danger_level = serializers.IntegerField(min_value=0, max_value=3, required=False, default=1)
    media = serializers.ListField(child=serializers.UUIDField(), required=False, default=list, max_length=6)
    submit = serializers.BooleanField(required=False, default=True)

    def validate_observed_at(self, v):
        if v > timezone.now() + timedelta(minutes=5):
            raise serializers.ValidationError("لا يمكن أن يكون في المستقبل.")
        return v

    def validate(self, attrs):
        attrs["category"] = attrs["category"].pk
        return attrs


class BundleSerializer(serializers.ModelSerializer):
    reports_detail = serializers.SerializerMethodField()

    class Meta:
        model = ReportBundle
        fields = ["id", "title", "kind", "area", "agency", "coordinator", "scheduled_for", "status", "reports",
                  "reports_detail", "notes", "created_at", "is_demo"]
        read_only_fields = ["coordinator", "created_at", "is_demo"]

    def get_reports_detail(self, b):
        return [{"id": r.pk, "tracking_number": r.tracking_number, "status": r.status, "status_label": r.status_label,
                 "category": r.category.name_ar} for r in b.reports.select_related("category")]


class ObjectionSerializer(serializers.ModelSerializer):
    report_tracking = serializers.CharField(source="report.tracking_number", read_only=True)

    class Meta:
        model = Objection
        fields = ["id", "report", "report_tracking", "reason", "status", "decided_at", "decision_note", "created_at"]
