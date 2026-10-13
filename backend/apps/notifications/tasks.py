from celery import shared_task

from .channels import send_push
from .models import DeviceToken, Notification


@shared_task
def push_notification(notification_id):
    n = Notification.objects.filter(pk=notification_id).select_related("user").first()
    if not n:
        return 0
    sent = 0
    for d in DeviceToken.objects.filter(user=n.user):
        send_push(d.token, n.title, n.body, {"kind": n.kind, **n.data})
        sent += 1
    return sent
