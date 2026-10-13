"""Idempotent POST handling: clients send `Idempotency-Key` (UUID) and may retry safely after a
dropped connection; the original response is replayed instead of creating a duplicate."""
import functools
import hashlib
import json

from django.db import connection, transaction
from rest_framework.response import Response

from .exceptions import Conflict
from .models import IdempotencyRecord


def _hash_body(request):
    try:
        body = json.dumps(request.data, sort_keys=True, default=str)
    except Exception:  # multipart etc.
        body = str(sorted((k, str(v)) for k, v in request.data.items()))
    return hashlib.sha256(body.encode()).hexdigest()


def idempotent(scope):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(self, request, *args, **kwargs):
            key = request.headers.get("Idempotency-Key") or (request.data.get("client_id") if hasattr(request.data, "get") else None)
            if not key or not request.user.is_authenticated:
                return fn(self, request, *args, **kwargs)
            key = str(key)[:80]
            h = _hash_body(request)
            with transaction.atomic():
                # Serialise concurrent retries of the same key: the second waits, then replays the first.
                lock_id = int(hashlib.sha256(f"{request.user.pk}:{scope}:{key}".encode()).hexdigest()[:15], 16)
                with connection.cursor() as cur:
                    cur.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])
                existing = IdempotencyRecord.objects.filter(user=request.user, scope=scope, key=key).first()
                if existing:
                    if existing.request_hash != h and scope != "report":
                        raise Conflict("مفتاح التكرار استُخدم لطلب مختلف.")
                    resp = Response(existing.response, status=existing.status_code)
                    resp["Idempotent-Replay"] = "true"
                    return resp
                response = fn(self, request, *args, **kwargs)
                if 200 <= response.status_code < 300:
                    IdempotencyRecord.objects.create(user=request.user, scope=scope, key=key, request_hash=h,
                                                     status_code=response.status_code,
                                                     response=json.loads(json.dumps(response.data, default=str)))
            return response
        return wrapper
    return deco
