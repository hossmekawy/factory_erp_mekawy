from rest_framework.permissions import BasePermission

# All login roles in the system, highest privilege first. A user's effective
# role is the first of these groups they belong to (superusers are admin).
ROLE_ORDER = ["admin", "hr", "production_manager", "cutting_supervisor", "cutting"]


def role_of(user) -> str:
    if user.is_superuser:
        return "admin"
    names = set(user.groups.values_list("name", flat=True))
    for role in ROLE_ORDER:
        if role in names:
            return role
    return ""


def _in_group(user, name: str) -> bool:
    return user.groups.filter(name=name).exists()


class IsAdmin(BasePermission):
    """Full access: superusers or members of the 'admin' group."""

    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and (u.is_superuser or _in_group(u, "admin"))


class IsAdminOrHR(BasePermission):
    """Admins plus HR clerks (group 'hr')."""

    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and (
            u.is_superuser or _in_group(u, "admin") or _in_group(u, "hr")
        )
