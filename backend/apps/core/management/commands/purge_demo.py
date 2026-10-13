"""Delete all demo rows (is_demo=True) and everything hanging off them. Development only."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.accounts.models import User
from apps.agencies.models import Agency, AgencyAnnouncement, ServiceDirectoryEntry
from apps.community.models import (BudgetCycle, CarePoint, Initiative, Proposal, SurplusOffer, SurveyAssignment, Task)
from apps.finance.models import Disbursement, LedgerEntry, Payment, Pledge, Refund, TransferProof
from apps.geo.models import Area, Landmark
from apps.inventory.models import Reservation, Resource
from apps.reports.models import Report, ReportBundle
from apps.roadnow.models import RoadAlert


class Command(BaseCommand):
    def handle(self, *a, **o):
        if settings.IS_PRODUCTION:
            raise CommandError("not allowed in production")
        with transaction.atomic():
            demo_inis = Initiative.objects.filter(is_demo=True)
            if LedgerEntry.objects.filter(initiative__in=demo_inis).exists():
                with connection.cursor() as c:
                    c.execute("SET CONSTRAINTS ALL IMMEDIATE")
                    c.execute("ALTER TABLE finance_ledgerentry DISABLE TRIGGER ledger_immutable")
                LedgerEntry.objects.filter(initiative__in=demo_inis)._raw_delete(LedgerEntry.objects.db)
                with connection.cursor() as c:
                    c.execute("ALTER TABLE finance_ledgerentry ENABLE TRIGGER ledger_immutable")
            Refund.objects.filter(payment__pledge__initiative__in=demo_inis).delete()
            TransferProof.objects.filter(pledge__initiative__in=demo_inis).delete()
            Payment.objects.filter(pledge__initiative__in=demo_inis).delete()
            Pledge.objects.filter(initiative__in=demo_inis).delete()
            Disbursement.objects.filter(initiative__in=demo_inis).delete()
            Reservation.objects.filter(resource__is_demo=True).delete()
            for m in (ReportBundle, Report, RoadAlert, Task, Resource, CarePoint, Proposal, BudgetCycle, SurplusOffer,
                      SurveyAssignment, AgencyAnnouncement, ServiceDirectoryEntry, Landmark):
                m.objects.filter(is_demo=True).delete()
            demo_inis.delete()
            from apps.agencies.models import JurisdictionRule
            JurisdictionRule.objects.filter(agency__is_demo=True).delete()
            Agency.objects.filter(is_demo=True).delete()
            Area.objects.filter(is_demo=True).delete()
            n = User.objects.filter(is_demo=True).count()
            with connection.cursor() as c:
                c.execute("SET CONSTRAINTS ALL IMMEDIATE")
                c.execute("ALTER TABLE core_auditlog DISABLE TRIGGER audit_immutable")
            User.objects.filter(is_demo=True).delete()
            with connection.cursor() as c:
                c.execute("SET CONSTRAINTS ALL IMMEDIATE")
                c.execute("ALTER TABLE core_auditlog ENABLE TRIGGER audit_immutable")
        self.stdout.write(self.style.SUCCESS(f"demo data purged ({n} demo users)"))
