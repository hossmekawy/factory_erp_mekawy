from rest_framework.permissions import BasePermission

from hr.permissions import role_of

# Roles allowed into مرحلة القص. Managers/supervisors see everything;
# the plain "cutting" role only sees records they created.
CUTTING_ROLES = {"admin", "production_manager", "cutting_supervisor", "cutting"}
CUTTING_MANAGER_ROLES = {"admin", "production_manager", "cutting_supervisor"}


class IsCuttingStaff(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and role_of(u) in CUTTING_ROLES


class CanTouchCutting(BasePermission):
    """Object-level: a cutting employee may only touch their own cuttings."""

    def has_object_permission(self, request, view, obj):
        role = role_of(request.user)
        if role in CUTTING_MANAGER_ROLES:
            return True
        return obj.created_by_id == request.user.id


def visible_cuttings(user, queryset):
    if role_of(user) in CUTTING_MANAGER_ROLES:
        return queryset
    return queryset.filter(created_by=user)
