"""Role gates for the cutting API, built on the existing hr group system.

SRS section 3:
  cutting supervisor — the main user: enters, closes, counts, and may edit
                       after closing with a mandatory reason. The `cutting`
                       group is the same thing under the other name and has
                       the same rights.
  production manager — reads everything, changes nothing.
  admin              — all of the above plus the catalogues (banks, models,
                       size sets, settings).

`cutting` sits lowest in ROLE_ORDER, so a user in both it and
`cutting_supervisor` resolves to the supervisor — which is the same set of
rights either way.
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from hr.permissions import role_of

READ_ROLES = {"admin", "production_manager", "cutting_supervisor", "cutting"}
# `cutting` is the group the real supervisor will be in, so it carries the same
# rights as `cutting_supervisor`: enter, close, count, and correct the
# catalogue. Deleting from the catalogue stays with the admin for both.
WRITE_ROLES = {"admin", "cutting_supervisor", "cutting"}
CATALOGUE_ROLES = {"admin"}


def _role(request) -> str:
    user = request.user
    if not (user and user.is_authenticated):
        return ""
    return role_of(user)


class CanViewCutting(BasePermission):
    message = "مالكش صلاحية على موديول القص"

    def has_permission(self, request, view):
        return _role(request) in READ_ROLES


class CanEditLays(CanViewCutting):
    """Read for anyone in the module, writes for the supervisor and the admin."""

    message = "مالكش صلاحية تعدّل الفرشات"

    def has_permission(self, request, view):
        role = _role(request)
        if request.method in SAFE_METHODS:
            return role in READ_ROLES
        return role in WRITE_ROLES


class CanManageCatalogue(CanViewCutting):
    """Banks, size sets and settings — admin only."""

    message = "إدارة الأكواد والمقاسات للأدمن بس"

    def has_permission(self, request, view):
        role = _role(request)
        if request.method in SAFE_METHODS:
            return role in READ_ROLES
        return role in CATALOGUE_ROLES


class CanAddToCatalogue(CanViewCutting):
    """Read for the module, add and correct for the supervisor, delete for the
    admin.

    SRS 3 puts catalogue management with the admin, while 7.2 lets the
    supervisor add a model from the new-lay screen. Once he can add one he can
    also mistype one, and refusing to let him fix his own typo just leaves the
    wrong name in every report — so editing is his too. Deleting is not: it is
    the one action that cannot be walked back, and a model that is actually in
    use is protected by the database anyway.
    """

    message = "حذف الكتالوج للأدمن بس"

    def has_permission(self, request, view):
        role = _role(request)
        if request.method in SAFE_METHODS:
            return role in READ_ROLES
        if request.method == "DELETE":
            return role in CATALOGUE_ROLES
        return role in WRITE_ROLES
