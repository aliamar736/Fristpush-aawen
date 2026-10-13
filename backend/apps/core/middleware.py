import threading

_local = threading.local()


def current_ip():
    return getattr(_local, "ip", None)


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
        _local.ip = (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")) or None
        try:
            return self.get_response(request)
        finally:
            _local.ip = None
