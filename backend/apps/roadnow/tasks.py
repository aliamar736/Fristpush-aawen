from celery import shared_task

from .services import expire_alerts as _expire


@shared_task
def expire_alerts():
    return _expire()
