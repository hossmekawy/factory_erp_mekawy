"""Alerts from SRS 11.1: who gets told what, and when.

Three events:
  * a lay closes with a fabric shortage past the tolerance
  * a count comes in with a piece loss past its tolerance
  * a lay has sat closed for more than 24 hours without being numbered

The first two are raised where they happen (services.close_lay,
services.record_output). The third has no moment to hang off — nothing
happens, which is the point — so it is swept by the daily command.

Creating an alert never raises. A notification failing must not roll back the
close that triggered it.
"""
import logging

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.utils import timezone

from hr.permissions import role_of

logger = logging.getLogger(__name__)

# SRS 11.1 sends these to the cutting supervisor and the production manager.
# Admins are included because they have every other permission in the module,
# and on a small install they may be the only accounts that exist — without
# this the alerts would be written for nobody.
ALERT_ROLES = {"admin", "cutting_supervisor", "production_manager"}


def recipients():
    return [u for u in User.objects.filter(is_active=True) if role_of(u) in ALERT_ROLES]


def _create(lay, kind, title, body):
    from .models import Notification

    made = []
    for user in recipients():
        try:
            notification, created = Notification.objects.get_or_create(
                lay=lay, kind=kind, recipient=user,
                defaults={"title": title, "body": body},
            )
        except IntegrityError:  # raced with another writer; the row exists
            continue
        if created:
            made.append(notification)
    return made


def _lay_label(lay) -> str:
    model = lay.garment_model
    return f"فرشة {lay.pk} · {model.code} {model.name}".strip()


def notify_shortage(lay):
    """Fabric on the table that the lay cannot account for (SRS 5.3)."""
    if not lay.has_shortage:
        return []
    return _create(
        lay,
        "shortage",
        f"عجز في القماش — {_lay_label(lay)}",
        f"أطوال الأتواب {lay.total_roll_length_m} م، والمستهلك + البواقي "
        f"{lay.consumed_m + lay.total_remnant_m} م. "
        f"العجز {lay.fabric_shortage_m} م، وده تعدّى نسبة التسامح.",
    )


def notify_pieces_loss(lay, loss: dict):
    """Counted pieces short of the theoretical total past tolerance."""
    if not loss.get("exceeds_tolerance"):
        return []
    return _create(
        lay,
        "pieces_loss",
        f"فاقد في القطع — {_lay_label(lay)}",
        f"القطع النظرية {lay.theoretical_pieces}، والفعلية "
        f"{lay.output.actual_pieces}. الفاقد {loss['pieces_loss']} قطعة "
        f"({loss['pieces_loss_pct']}%)، وده تعدّى نسبة التسامح.",
    )


def notify_awaiting_count(lay, hours: int):
    """Closed and still not numbered. In-system only — SRS 11.1 gives this one
    no email, because it repeats until someone acts and would become noise."""
    return _create(
        lay,
        "awaiting_count",
        f"مستنية ترقيم من {hours} ساعة — {_lay_label(lay)}",
        f"الفرشة اتقفلت يوم {lay.closed_at:%Y-%m-%d %H:%M} ولسه القطع الفعلية "
        f"متسجلتش. الميتراج الحقيقي مش هيتحسب من غيرها.",
    )


def sweep_awaiting_count(hours: int = 24):
    """Find lays closed longer than `hours` ago with no count, and alert once."""
    from .models import Lay

    cutoff = timezone.now() - timezone.timedelta(hours=hours)
    stale = Lay.objects.filter(
        status=Lay.STATUS_CLOSED, output__isnull=True, closed_at__lt=cutoff
    ).select_related("garment_model")

    made = []
    for lay in stale:
        age = int((timezone.now() - lay.closed_at).total_seconds() // 3600)
        made += notify_awaiting_count(lay, age)
    return made


def mark_read(user, ids=None):
    from .models import Notification

    qs = Notification.objects.filter(recipient=user, is_read=False)
    if ids is not None:
        qs = qs.filter(id__in=ids)
    return qs.update(is_read=True, read_at=timezone.now())


def safe(fn, *args, **kwargs):
    """Run an alert rule without letting it break the thing that triggered it."""
    try:
        return fn(*args, **kwargs)
    except Exception:  # noqa: BLE001 — an alert is never worth losing a close
        logger.exception("cutting: failed to raise a notification")
        return []
