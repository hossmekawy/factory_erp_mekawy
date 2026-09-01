"""Once-a-day cutting digest (SRS 11.1).

Two jobs, in order:
  1. sweep for lays that have sat closed over 24 hours without a count and
     raise the in-system alert for them — that event has no moment to hang
     off, because what happened is that nothing happened;
  2. send one email per recipient covering every alert they have not been
     emailed yet.

**One email a day, not one per lay**, which is the whole point: a message per
shortage is a message nobody reads by the end of the week.

SRS 11.1 names Celery or django-q. Neither is installed, and neither is worth
installing for a job that runs once a day — a queue is for work that must
happen soon and might fail, not for a scheduled digest. This is a management
command on a systemd timer, which is what the box already knows how to run.

    ./manage.py send_cutting_digest            # sweep, then email
    ./manage.py send_cutting_digest --dry-run  # print, send nothing
    ./manage.py send_cutting_digest --no-sweep # email only
"""
from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.management.base import BaseCommand
from django.utils import timezone

from cutting import notifications
from cutting.models import CuttingSettings, Notification

# Email is for the two events worth interrupting someone over. The
# "still not numbered" nag stays in-system: it repeats every day until
# somebody acts, and daily mail about it becomes noise people filter away.
EMAILED_KINDS = [Notification.KIND_SHORTAGE, Notification.KIND_PIECES_LOSS]


class Command(BaseCommand):
    help = "Sweep for stale lays and send the daily cutting digest email."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Show what would be sent without sending it.")
        parser.add_argument("--no-sweep", action="store_true",
                            help="Skip the awaiting-count sweep.")
        parser.add_argument("--hours", type=int, default=24,
                            help="How long a closed lay may wait before it is stale.")

    def handle(self, *args, **options):
        dry = options["dry_run"]

        if not options["no_sweep"]:
            made = notifications.sweep_awaiting_count(options["hours"])
            self.stdout.write(f"مستنية ترقيم: {len(made)} تنبيه جديد")

        pending = (
            Notification.objects.filter(emailed_at__isnull=True, kind__in=EMAILED_KINDS)
            .select_related("recipient")
            .order_by("recipient_id", "created_at")
        )

        by_recipient = {}
        for note in pending:
            by_recipient.setdefault(note.recipient, []).append(note)

        if not by_recipient:
            self.stdout.write("مفيش تنبيهات جديدة تتبعت")
            return

        extra = _extra_addresses()
        sent_ids = []
        connection = None if dry else get_connection()

        for user, notes in by_recipient.items():
            to = [a for a in [user.email, *extra] if a]
            subject = f"تنبيهات القص — {len(notes)} فرشة"
            body = _body(user, notes)

            if dry or not to:
                reason = "معاينة" if dry else "مفيش إيميل للمستخدم ده"
                self.stdout.write(f"[{reason}] {user.username}: {len(notes)} تنبيه")
                self.stdout.write(body)
                if dry:
                    continue
                # No address to send to, but the alert is still in the system;
                # marking it stops it queueing up forever.
                sent_ids += [n.id for n in notes]
                continue

            try:
                EmailMessage(
                    subject=subject, body=body,
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                    to=to, connection=connection,
                ).send()
            except Exception as exc:  # noqa: BLE001 — one bad address must not
                self.stderr.write(f"فشل إرسال إيميل {user.username}: {exc}")  # stop the rest
                continue
            sent_ids += [n.id for n in notes]
            self.stdout.write(f"اتبعت لـ {user.username} ({len(notes)} تنبيه)")

        if sent_ids and not dry:
            Notification.objects.filter(id__in=sent_ids).update(emailed_at=timezone.now())
        self.stdout.write(self.style.SUCCESS(f"تم: {len(sent_ids)} تنبيه"))


def _extra_addresses():
    raw = CuttingSettings.get_solo().notify_emails or ""
    return [a.strip() for a in raw.replace("\n", ",").split(",") if a.strip()]


def _body(user, notes) -> str:
    lines = [f"أهلاً {user.get_full_name() or user.username}،", ""]
    lines.append(f"فيه {len(notes)} تنبيه من موديول القص:")
    lines.append("")
    for note in notes:
        lines.append(f"• {note.title}")
        if note.body:
            lines.append(f"  {note.body}")
        lines.append("")
    lines.append("الرسالة دي بتتبعت مرة واحدة في اليوم مجمّعة.")
    return "\n".join(lines)
