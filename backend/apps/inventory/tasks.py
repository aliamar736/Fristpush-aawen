from celery import shared_task

from .services import mark_overdue as _mark


@shared_task
def mark_overdue():
    return _mark()
