"""Server-side role & scope checks. Every privileged API path goes through these helpers."""
from rest_framework.permissions import BasePermission

from .models import Role, RoleAssignment


def _assignments(user):
    if not user or not user.is_authenticated:
        return []
    cache = getattr(user, "_aawen_roles", None)
    if cache is None:
        cache = list(RoleAssignment.objects.filter(user=user, active=True).values_list("role", "area_id", "agency_id"))
        user._aawen_roles = cache
    return cache


def clear_role_cache(user):
    if hasattr(user, "_aawen_roles"):
        del user._aawen_roles


def roles_of(user):
    return {r for r, _, _ in _assignments(user)}


def has_role(user, *roles, area=None, agency=None, any_scope=False):
    """True if the user holds one of `roles`.
    - area: the target object's area (Area or id). A global assignment (area=None) covers every area.
      If the target has no area, only global assignments qualify.
    - agency: the target agency (Agency or id); agency-scoped roles must match it.
    - any_scope=True ignores scope (used for "can this user see the console at all")."""
    area_id = getattr(area, "pk", area)
    agency_id = getattr(agency, "pk", agency)
    for role, a_id, ag_id in _assignments(user):
        if role not in roles:
            continue
        if any_scope:
            return True
        if a_id is not None and a_id != area_id:
            continue
        if agency is not None and ag_id is not None and ag_id != agency_id:
            continue
        if agency is not None and role == Role.AGENCY_STAFF and ag_id is None:
            continue  # agency staff must be attached to a specific agency
        return True
    return False


def agency_ids_of(user):
    return {ag for r, _, ag in _assignments(user) if r == Role.AGENCY_STAFF and ag}


def area_scope_of(user, *roles):
    """Returns None for global scope, otherwise the set of area ids the roles cover."""
    ids = set()
    for role, a_id, _ in _assignments(user):
        if role in roles:
            if a_id is None:
                return None
            ids.add(a_id)
    return ids


class HasRole(BasePermission):
    """Usage: permission_classes = [HasRole.of(Role.REVIEWER, Role.COORDINATOR)] (scope-agnostic gate;
    object-level scope checks happen in the views)."""
    roles = ()
    message = "ليس لديك صلاحية لهذا الإجراء."

    @classmethod
    def of(cls, *roles):
        return type(f"HasRole_{'_'.join(roles)}", (cls,), {"roles": roles})

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and has_role(request.user, *self.roles, any_scope=True))
