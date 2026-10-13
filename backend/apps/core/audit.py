from .middleware import current_ip
from .models import AuditLog


def audit(actor, action, target=None, **data):
    """Record a sensitive change. `target` may be a model instance or a (type, id) tuple."""
    if isinstance(target, tuple):
        t_type, t_id = target
    elif target is not None:
        t_type, t_id = target._meta.label_lower, target.pk
    else:
        t_type, t_id = "", ""
    clean = {k: (str(v) if not isinstance(v, (int, float, bool, str, list, dict, type(None))) else v)
             for k, v in data.items()}
    return AuditLog.objects.create(
        actor=actor if (actor is not None and getattr(actor, "is_authenticated", False)) else None,
        action=action, target_type=t_type, target_id=str(t_id or ""), data=clean, ip=current_ip())
