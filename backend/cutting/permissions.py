"""Role gates for the cutting API, built on the existing hr group system.

SRS section 3:
  cutting supervisor — the main user: enters, closes, counts, and may edit
                       after closing with a mandatory reason.
  production manager — reads everything, changes nothing.
  admin              — all of the above plus the catalogues (banks, models,
                       size sets, settings).

The `cutting` group is the lowest role in ROLE_ORDER and is not one of the
SRS's four. It is treated as read-only until someone says otherwise.
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from hr.permissions import role_of

READ_ROLES = {"admin", "production_manager", "cutting_supervisor", "cutting"}
WRITE_ROLES = {"admin", "cutting_supervisor"}
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
    """Same, but the supervisor may also *create*.

    SRS 3 puts catalogue management with the admin, while SRS 7.2 gives the
    new-lay screen a "quick add" for a model the supervisor is holding in his
    hand right now. Both hold if he can add but not rewrite: a wrong new row
    is a nuisance, a rewritten one silently changes closed lays.
    """

    message = "تعديل الكتالوج للأدمن بس — تقدر تضيف جديد بس"

    def has_permission(self, request, view):
        role = _role(request)
        if request.method in SAFE_METHODS:
            return role in READ_ROLES
        if request.method == "POST":
            return role in WRITE_ROLES
        return role in CATALOGUE_ROLES
