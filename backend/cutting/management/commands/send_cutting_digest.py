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

        if not pending:
            self.stdout.write("مفيش تنبيهات جديدة تتبعت")
            return

        # Group by ADDRESS, not by user. Five people can share one inbox — the
        # notify_emails setting routes everyone to the same address on a small
        # install — and grouping by user sends that address five copies of the
        # same lay, which is exactly the pile-up a digest exists to prevent.
        extra = _extra_addresses()
        by_address = {}
        no_address = []
        for note in pending:
            addresses = [a for a in [note.recipient.email, *extra] if a]
            if not addresses:
                no_address.append(note)
                continue
            for address in addresses:
                bucket = by_address.setdefault(address, {})
                # Keyed by the EVENT, not the row. One shortage writes a row
                # per recipient, and when those recipients share an inbox the
                # same lay would otherwise be listed once per person.
                bucket.setdefault((note.lay_id, note.kind), []).append(note)

        sent_ids = set()
        connection = None if dry else get_connection()

        for address, bucket in by_address.items():
            groups = sorted(bucket.values(), key=lambda g: g[0].created_at)
            notes = [g[0] for g in groups]           # one representative each
            covered = [n.id for g in groups for n in g]  # every row it stands for
            subject = f"تنبيهات القص — {len(notes)} فرشة"
            body = _body(address, notes)

            if dry:
                self.stdout.write(f"[معاينة] {address}: {len(notes)} تنبيه")
                self.stdout.write(body)
                continue

            try:
                EmailMessage(
                    subject=subject, body=body,
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                    to=[address], connection=connection,
                ).send()
            except Exception as exc:  # noqa: BLE001 — one bad address must not
                self.stderr.write(f"فشل إرسال إيميل {address}: {exc}")  # stop the rest
                continue
            sent_ids.update(covered)
            self.stdout.write(f"اتبعت لـ {address} ({len(notes)} تنبيه)")

        if no_address and not dry:
            # Nobody to mail, but the alert is in the system and visible there;
            # marking it stops it queueing up forever.
            self.stdout.write(f"{len(no_address)} تنبيه مالوش إيميل — اتساب في السيستم بس")
            sent_ids.update(n.id for n in no_address)

        if sent_ids and not dry:
            Notification.objects.filter(id__in=sent_ids).update(emailed_at=timezone.now())
        self.stdout.write(self.style.SUCCESS(f"تم: {len(sent_ids)} تنبيه"))


def _extra_addresses():
    raw = CuttingSettings.get_solo().notify_emails or ""
    return [a.strip() for a in raw.replace("\n", ",").split(",") if a.strip()]


def _body(address, notes) -> str:
    lines = ["أهلاً،", ""]
    lines.append(f"فيه {len(notes)} تنبيه من موديول القص:")
    lines.append("")
    for note in notes:
        lines.append(f"• {note.title}")
        if note.body:
            lines.append(f"  {note.body}")
        lines.append("")
    lines.append("الرسالة دي بتتبعت مرة واحدة في اليوم مجمّعة.")
    return "\n".join(lines)
