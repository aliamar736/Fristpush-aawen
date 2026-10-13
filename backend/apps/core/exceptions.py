from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_handler


class Conflict(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "تعارض مع حالة البيانات الحالية."
    default_code = "conflict"


class InvalidTransition(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "هذا الانتقال غير مسموح من الحالة الحالية."
    default_code = "invalid_transition"


class ServiceDisabled(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "هذه الخدمة غير مفعّلة حاليًا."
    default_code = "service_disabled"


def exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied(str(exc) or None)
    response = drf_handler(exc, context)
    if response is None:
        return None
    data = response.data
    code = getattr(exc, "default_code", "error")
    if isinstance(exc, exceptions.APIException):
        codes = exc.get_codes()
        if isinstance(codes, str):
            code = codes
    if isinstance(data, dict) and "detail" in data:
        body = {"error": {"code": code, "message": str(data["detail"])}}
    else:
        body = {"error": {"code": "validation_error", "message": "بعض البيانات غير صحيحة.", "fields": data}}
    return Response(body, status=response.status_code, headers=getattr(response, "headers", None) and
                    {k: v for k, v in response.headers.items() if k.lower() in ("retry-after", "www-authenticate")})
