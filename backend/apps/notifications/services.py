from django.db import transaction

from apps.accounts.models import RoleAssignment

from .models import Notification


def notify(user, kind, title, body="", data=None):
    if user is None or not user.is_active:
        return None
    n = Notification.objects.create(user=user, kind=kind, title=title[:200], body=body or "", data=data or {})
    from .tasks import push_notification
    transaction.on_commit(lambda: push_notification.delay(n.pk))
    return n


def notify_role(role, kind, title, body="", data=None, area_id=None, agency_id=None):
    qs = RoleAssignment.objects.filter(role=role, active=True).select_related("user")
    if agency_id is not None:
        qs = qs.filter(agency_id=agency_id)
    if area_id is not None:
        from django.db.models import Q
        qs = qs.filter(Q(area_id=area_id) | Q(area__isnull=True))
    seen = set()
    for ra in qs:
        if ra.user_id not in seen:
            seen.add(ra.user_id)
            notify(ra.user, kind, title, body, data)
    return len(seen)
