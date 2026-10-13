from celery import shared_task

from .services import process_due_deletions


@shared_task
def process_deletion_requests():
    return process_due_deletions()
