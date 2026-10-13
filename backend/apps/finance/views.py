import csv
import io
from decimal import Decimal

from django.conf import settings
from django.http import HttpResponse
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import HasRole, has_role
from apps.community.models import Initiative
from apps.core.exceptions import ServiceDisabled
from apps.core.idempotency import idempotent
from apps.core.models import MediaAsset

from . import services
from .models import Disbursement, LedgerEntry, Payment, Pledge, Refund, TransferProof
from .providers import SimulatorProvider, payments_status

FIN = (Role.ACCOUNTANT, Role.FINANCIAL_AUDITOR)


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "pledge", "provider", "provider_payment_id", "amount", "fee", "refunded_amount", "status",
                  "failure_reason", "confirmed_at", "receipt_number", "is_simulated", "checkout_url", "created_at"]


class PledgeSerializer(serializers.ModelSerializer):
    initiative_title = serializers.CharField(source="initiative.title", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    transfer_proofs = serializers.SerializerMethodField()

    class Meta:
        model = Pledge
        fields = ["id", "initiative", "initiative_title", "need", "amount", "currency", "method", "status",
                  "status_label", "organization_name", "is_corporate", "is_anonymous", "payments", "transfer_proofs",
                  "created_at", "is_demo"]

    def get_transfer_proofs(self, p):
        return [{"id": t.pk, "status": t.status, "claimed_reference": t.claimed_reference, "created_at": t.created_at}
                for t in p.transfer_proofs.all()]


class PledgeViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PledgeSerializer

    def get_queryset(self):
        u = self.request.user
        qs = Pledge.objects.select_related("initiative").prefetch_related("payments", "transfer_proofs")
        if has_role(u, *FIN, any_scope=True) and self.request.query_params.get("all") == "1":
            return qs
        return qs.filter(contributor=u)

    @idempotent("pledge")
    def create(self, request):
        d = request.data
        p, created = services.create_pledge(request.user, d.get("initiative"), d.get("amount"), d.get("method", "online"),
                                            d.get("need"), d.get("organization_name", ""),
                                            bool(d.get("is_anonymous", True)), d.get("client_id"))
        return Response(PledgeSerializer(p).data, status=201 if created else 200)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(PledgeSerializer(services.cancel_pledge(request.user, self.get_object())).data)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        payment = services.start_online_payment(request.user, self.get_object())
        return Response(PaymentSerializer(payment).data, status=201)

    @action(detail=True, methods=["post"], url_path="transfer-proof")
    def transfer_proof(self, request, pk=None):
        asset = MediaAsset.objects.filter(uid=request.data.get("media"), owner=request.user).first()
        if not asset:
            raise ValidationError({"media": "ارفع صورة الإيصال أولًا."})
        proof = services.upload_transfer_proof(request.user, self.get_object(), asset,
                                               request.data.get("claimed_reference", ""))
        return Response({"id": proof.pk, "status": proof.status,
                         "message": "استلمنا الإثبات. لا تُعد الدفعة مؤكدة حتى يطابقها المحاسب مع كشف الحساب."}, status=201)


class WebhookView(APIView):
    """Provider webhooks. Signature verified; duplicate deliveries are acknowledged but not re-applied."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "webhook"

    def post(self, request, provider):
        try:
            result = services.handle_webhook(provider, request.body, request.headers)
        except ServiceDisabled:
            return Response({"error": "payments disabled"}, status=503)
        return Response({"result": result})


class SimulatorView(APIView):
    """Development simulator for the hosted checkout. Disabled unless PAYMENTS_MODE=simulated."""
    permission_classes = [IsAuthenticated]

    def post(self, request, provider_payment_id):
        if settings.PAYMENTS_MODE != "simulated" or settings.IS_PRODUCTION:
            raise ServiceDisabled("المحاكي غير متاح.")
        payment = Payment.objects.filter(provider="simulator", provider_payment_id=provider_payment_id).first()
        if not payment or payment.pledge.contributor_id != request.user.pk:
            raise PermissionDenied()
        outcome = request.data.get("outcome", "success")
        repeat = min(int(request.data.get("deliveries", 1)), 5)
        if outcome == "success":
            fee = (payment.amount * Decimal(str(settings.PLATFORM_FEE_PERCENT)) / 100).quantize(Decimal("0.01"))
            body, headers = SimulatorProvider.build_event("payment.succeeded", provider_payment_id, payment.amount, fee)
        elif outcome == "failure":
            body, headers = SimulatorProvider.build_event("payment.failed", provider_payment_id,
                                                          reason="رُفضت البطاقة (محاكاة)")
        else:
            raise ValidationError({"outcome": "success|failure"})
        results = [services.handle_webhook("simulator", body, headers) for _ in range(repeat)]
        payment.refresh_from_db()
        return Response({"results": results, "payment": PaymentSerializer(payment).data})


class PaymentsStatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(payments_status())


class TransferProofViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [HasRole.of(*FIN)]

    def get_queryset(self):
        st = self.request.query_params.get("status", "pending")
        qs = TransferProof.objects.select_related("pledge__initiative", "asset")
        return qs if st == "all" else qs.filter(status=st)

    def _ser(self, t):
        return {"id": t.pk, "pledge": t.pledge_id, "initiative": t.pledge.initiative.title, "amount": str(t.pledge.amount),
                "claimed_reference": t.claimed_reference, "status": t.status, "image": f"/api/v1/media/{t.asset.uid}/file",
                "created_at": t.created_at, "note": t.note}

    def list(self, request):
        return Response([self._ser(t) for t in self.get_queryset()[:200]])

    @action(detail=True, methods=["post"])
    def match(self, request, pk=None):
        t = services.match_transfer(request.user, TransferProof.objects.get(pk=pk), request.data.get("bank_reference", ""),
                                    request.data.get("amount", "0") if request.data.get("matched", True) else "1",
                                    matched=bool(request.data.get("matched", True)), note=request.data.get("note", ""))
        return Response(self._ser(t))


class DisbursementSerializer(serializers.ModelSerializer):
    initiative_title = serializers.CharField(source="initiative.title", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Disbursement
        fields = ["id", "initiative", "initiative_title", "need", "amount", "purpose", "payee_name", "status",
                  "status_label", "requested_by", "approved_by", "approved_at", "decision_note", "paid_by", "paid_at",
                  "payment_reference", "receipt", "public_result", "created_at"]
        read_only_fields = fields


class DisbursementViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = DisbursementSerializer

    def get_queryset(self):
        u = self.request.user
        qs = Disbursement.objects.select_related("initiative")
        if has_role(u, *FIN, any_scope=True):
            return qs
        return qs.filter(initiative__manager=u)

    def create(self, request):
        ini = Initiative.objects.get(pk=request.data.get("initiative"))
        d = services.request_disbursement(request.user, ini, request.data.get("amount"), request.data.get("purpose", ""),
                                          request.data.get("payee_name", ""), request.data.get("need"))
        return Response(DisbursementSerializer(d).data, status=201)

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        d = services.decide_disbursement(request.user, self.get_object(), bool(request.data.get("approve")),
                                         request.data.get("note", ""))
        return Response(DisbursementSerializer(d).data)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        receipt = MediaAsset.objects.filter(uid=request.data.get("receipt"), owner=request.user).first() \
            if request.data.get("receipt") else None
        d = services.pay_disbursement(request.user, self.get_object(), request.data.get("payment_reference", ""), receipt,
                                      request.data.get("public_result", ""))
        return Response(DisbursementSerializer(d).data)


class RefundViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [HasRole.of(*FIN)]

    def get_queryset(self):
        return Refund.objects.select_related("payment__pledge__initiative").order_by("-created_at")

    def _ser(self, r):
        return {"id": r.pk, "payment": r.payment_id, "amount": str(r.amount), "reason": r.reason, "status": r.status,
                "initiative": r.payment.pledge.initiative.title, "provider": r.payment.provider,
                "requested_by": r.requested_by_id, "approved_by": r.approved_by_id, "completed_at": r.completed_at}

    def list(self, request):
        return Response([self._ser(r) for r in self.get_queryset()[:200]])

    def create(self, request):
        payment = Payment.objects.get(pk=request.data.get("payment"))
        r = services.request_refund(request.user, payment, request.data.get("amount"), request.data.get("reason", ""))
        return Response(self._ser(r), status=201)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        r = services.approve_refund(request.user, Refund.objects.get(pk=pk), bool(request.data.get("approve", True)),
                                    request.data.get("note", ""))
        r.refresh_from_db()
        return Response(self._ser(r))

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        r = services.complete_manual_refund(request.user, Refund.objects.get(pk=pk), request.data.get("reference", ""))
        return Response(self._ser(r))


class LedgerView(APIView):
    """Auditable ledger; ?format=csv for export. Public summary per initiative is at /initiatives/{id}/."""
    permission_classes = [HasRole.of(*FIN)]

    def get(self, request):
        qs = LedgerEntry.objects.select_related("initiative").order_by("created_at", "id")
        if request.query_params.get("initiative"):
            qs = qs.filter(initiative_id=request.query_params["initiative"])
        rows = [{"id": e.pk, "at": e.created_at, "initiative": e.initiative.title, "type": e.entry_type,
                 "direction": e.direction, "amount": str(e.amount), "currency": e.currency, "payment": e.payment_id,
                 "disbursement": e.disbursement_id, "refund": e.refund_id, "memo": e.memo,
                 "simulated": e.is_simulated} for e in qs[:5000]]
        if request.query_params.get("export") == "csv":
            buf = io.StringIO()
            buf.write("﻿")
            w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()) if rows else ["id"])
            w.writeheader()
            w.writerows(rows)
            resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
            resp["Content-Disposition"] = 'attachment; filename="aawen-ledger.csv"'
            return resp
        return Response(rows)


class ReconciliationView(APIView):
    permission_classes = [HasRole.of(*FIN)]

    def get(self, request):
        return Response(services.reconciliation_report())


class PaymentAdminViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [HasRole.of(*FIN)]
    serializer_class = PaymentSerializer
    queryset = Payment.objects.all().order_by("-created_at")
    filterset_fields = ["status", "provider"]
