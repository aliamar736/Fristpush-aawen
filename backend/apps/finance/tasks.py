import json

from celery import shared_task

from .providers import SimulatorProvider, sign


@shared_task
def simulator_emit(event):
    """Simulator only: delivers a signed webhook to our own handler, as a gateway would."""
    from django.conf import settings

    from .services import handle_webhook
    body = json.dumps(event).encode()
    return handle_webhook("simulator", body, {SimulatorProvider.header: sign(body, settings.PAYMENT_WEBHOOK_SECRET)})
