"""OpenAPI helpers: describe plain APIViews (free-form JSON) so every endpoint appears in the API docs."""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view

METHODS = ("get", "post", "put", "patch", "delete")


def document(view_cls, summary=None, tags=None):
    present = {m: extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT, summary=summary, tags=tags)
               for m in METHODS if hasattr(view_cls, m)}
    return extend_schema_view(**present)(view_cls)
