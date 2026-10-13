from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts import views as acc
from apps.agencies import views as ag
from apps.community import views as com
from apps.core import views as core
from apps.finance import views as fin
from apps.geo import views as geo
from apps.inventory import views as inv
from apps.notifications import views as notif
from apps.reports import views as rep
from apps.roadnow import views as road

router = DefaultRouter()
router.register("media", core.MediaViewSet, basename="media")
router.register("admin/moderation", core.ModerationViewSet, basename="moderation")
router.register("admin/audit", core.AuditLogViewSet, basename="audit")
router.register("admin/users", acc.AdminUserViewSet, basename="admin-users")
router.register("admin/roles", acc.RoleAssignmentViewSet, basename="roles")
router.register("cities", geo.CityViewSet, basename="cities")
router.register("areas", geo.AreaViewSet, basename="areas")
router.register("landmarks", geo.LandmarkViewSet, basename="landmarks")
router.register("agencies", ag.AgencyViewSet, basename="agencies")
router.register("jurisdiction-rules", ag.RuleViewSet, basename="rules")
router.register("announcements", ag.AnnouncementViewSet, basename="announcements")
router.register("service-directory", ag.ServiceDirectoryViewSet, basename="service-directory")
router.register("categories", rep.CategoryViewSet, basename="categories")
router.register("reports", rep.ReportViewSet, basename="reports")
router.register("objections", rep.ObjectionViewSet, basename="objections")
router.register("followups", rep.FollowUpViewSet, basename="followups")
router.register("bundles", rep.BundleViewSet, basename="bundles")
router.register("road-alerts", road.RoadAlertViewSet, basename="road-alerts")
router.register("initiatives", com.InitiativeViewSet, basename="initiatives")
router.register("needs", com.NeedViewSet, basename="needs")
router.register("help-offers", com.HelpOfferViewSet, basename="help-offers")
router.register("skills", com.SkillViewSet, basename="skills")
router.register("tasks", com.TaskViewSet, basename="tasks")
router.register("bookings", com.BookingViewSet, basename="bookings")
router.register("care-points", com.CarePointViewSet, basename="care-points")
router.register("budget-cycles", com.CycleViewSet, basename="budget-cycles")
router.register("proposals", com.ProposalViewSet, basename="proposals")
router.register("surplus", com.SurplusViewSet, basename="surplus")
router.register("surveys", com.SurveyViewSet, basename="surveys")
router.register("resources", inv.ResourceViewSet, basename="resources")
router.register("reservations", inv.ReservationViewSet, basename="reservations")
router.register("pledges", fin.PledgeViewSet, basename="pledges")
router.register("finance/transfer-proofs", fin.TransferProofViewSet, basename="transfer-proofs")
router.register("finance/disbursements", fin.DisbursementViewSet, basename="disbursements")
router.register("finance/refunds", fin.RefundViewSet, basename="refunds")
router.register("finance/payments", fin.PaymentAdminViewSet, basename="payments")
router.register("notifications", notif.NotificationViewSet, basename="notifications")

api = [
    path("health", core.HealthView.as_view()),
    path("config", core.PublicConfigView.as_view()),
    path("admin/settings", core.SettingsView.as_view()),
    path("auth/otp/request", acc.OTPRequestView.as_view()),
    path("auth/otp/verify", acc.OTPVerifyView.as_view()),
    path("auth/login", acc.PasswordLoginView.as_view()),
    path("auth/logout", acc.LogoutView.as_view()),
    path("auth/sessions", acc.SessionsView.as_view()),
    path("auth/refresh", TokenRefreshView.as_view()),
    path("me", acc.MeView.as_view()),
    path("me/password", acc.SetPasswordView.as_view()),
    path("me/deletion", acc.DeletionView.as_view()),
    path("me/devices", acc.DeviceView.as_view()),
    path("me/volunteer-profile", com.VolunteerProfileView.as_view()),
    path("places/profile", geo.PlaceProfileView.as_view()),
    path("emergency", road.EmergencyInfoView.as_view()),
    path("coverage", com.CoverageView.as_view()),
    path("finance/status", fin.PaymentsStatusView.as_view()),
    path("finance/webhooks/<str:provider>", fin.WebhookView.as_view()),
    path("finance/simulator/<str:provider_payment_id>", fin.SimulatorView.as_view()),
    path("finance/ledger", fin.LedgerView.as_view()),
    path("finance/reconciliation", fin.ReconciliationView.as_view()),
    path("schema", SpectacularAPIView.as_view(), name="schema"),
    path("docs", SpectacularSwaggerView.as_view(url_name="schema")),
    path("", include(router.urls)),
]

urlpatterns = [
    path("api/v1/", include(api)),
    path("django-admin/", admin.site.urls),
]
