"""Alerts and the daily digest (SRS 11.1)."""
import datetime

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from cutting import notifications, services
from cutting.models import Lay, Notification
from cutting.tests.conftest import TODAY

pytestmark = pytest.mark.django_db


class TestShortageAlert:
    def test_closing_with_a_shortage_raises_one(self, make_lay, user, as_role):
        as_role("cutting_supervisor")  # somebody exists to receive it
        lay = make_lay(lines=[
            {"roll_length_m": "101.00", "plies": 20, "remnant_m": "0.50"},
        ])
        assert lay.has_shortage is True
        services.close_lay(lay, user, override_reason="اختبار")
        assert Notification.objects.filter(kind="shortage", lay=lay).exists()

    def test_a_clean_lay_raises_nothing(self, make_lay, user, as_role):
        as_role("cutting_supervisor")
        lay = make_lay()
        services.close_lay(lay, user, override_reason="اختبار")
        assert not Notification.objects.filter(lay=lay).exists()

    def test_it_is_not_raised_twice_for_the_same_lay(self, make_lay, user, as_role):
        as_role("cutting_supervisor")
        lay = make_lay(lines=[
            {"roll_length_m": "101.00", "plies": 20, "remnant_m": "0.50"},
        ])
        services.close_lay(lay, user, override_reason="اختبار")
        notifications.notify_shortage(lay)
        notifications.notify_shortage(lay)
        assert Notification.objects.filter(kind="shortage", lay=lay).count() == 1

    def test_it_reaches_the_roles_the_srs_names(self, make_lay, user, as_role):
        for role in ["cutting_supervisor", "production_manager", "admin"]:
            as_role(role)
        as_role("hr")  # not a cutting role
        lay = make_lay(lines=[
            {"roll_length_m": "101.00", "plies": 20, "remnant_m": "0.50"},
        ])
        services.close_lay(lay, user, override_reason="اختبار")
        got = set(
            Notification.objects.filter(lay=lay).values_list(
                "recipient__username", flat=True
            )
        )
        assert "u_cutting_supervisor" in got
        assert "u_production_manager" in got
        assert "u_hr" not in got

    def test_a_failing_alert_never_rolls_back_the_close(
        self, make_lay, user, as_role, monkeypatch
    ):
        as_role("cutting_supervisor")
        lay = make_lay(lines=[
            {"roll_length_m": "101.00", "plies": 20, "remnant_m": "0.50"},
        ])

        def boom(*a, **k):
            raise RuntimeError("mail server on fire")

        monkeypatch.setattr(notifications, "notify_shortage", boom)
        services.close_lay(lay, user, override_reason="اختبار")
        lay.refresh_from_db()
        assert lay.status == Lay.STATUS_CLOSED


class TestPiecesLossAlert:
    def test_a_loss_past_tolerance_raises_one(self, make_lay, user, as_role):
        as_role("cutting_supervisor")
        lay = make_lay(status=Lay.STATUS_CLOSED)  # 120 theoretical
        services.record_output(lay, user, actual_pieces=100)  # 16.7% loss
        assert Notification.objects.filter(kind="pieces_loss", lay=lay).exists()

    def test_a_loss_inside_tolerance_does_not(self, make_lay, user, as_role):
        as_role("cutting_supervisor")
        lay = make_lay(status=Lay.STATUS_CLOSED)
        services.record_output(lay, user, actual_pieces=119)  # 0.8%
        assert not Notification.objects.filter(kind="pieces_loss", lay=lay).exists()


class TestAwaitingCountSweep:
    def test_a_lay_closed_over_a_day_ago_is_flagged(self, make_lay, user, as_role):
        as_role("cutting_supervisor")
        lay = make_lay(status=Lay.STATUS_CLOSED)
        Lay.objects.filter(pk=lay.pk).update(
            closed_at=timezone.now() - datetime.timedelta(hours=30)
        )
        made = notifications.sweep_awaiting_count(hours=24)
        assert made
        assert Notification.objects.filter(kind="awaiting_count", lay=lay).exists()

    def test_a_recently_closed_lay_is_left_alone(self, make_lay, user, as_role):
        as_role("cutting_supervisor")
        lay = make_lay(status=Lay.STATUS_CLOSED)
        Lay.objects.filter(pk=lay.pk).update(closed_at=timezone.now())
        notifications.sweep_awaiting_count(hours=24)
        assert not Notification.objects.filter(kind="awaiting_count").exists()

    def test_a_counted_lay_is_never_flagged(self, make_lay, user, as_role):
        as_role("cutting_supervisor")
        lay = make_lay(status=Lay.STATUS_CLOSED)
        services.record_output(lay, user, actual_pieces=119)
        Lay.objects.filter(pk=lay.pk).update(
            closed_at=timezone.now() - datetime.timedelta(hours=30)
        )
        notifications.sweep_awaiting_count(hours=24)
        assert not Notification.objects.filter(kind="awaiting_count").exists()

    def test_sweeping_twice_does_not_nag_twice(self, make_lay, user, as_role):
        as_role("cutting_supervisor")
        lay = make_lay(status=Lay.STATUS_CLOSED)
        Lay.objects.filter(pk=lay.pk).update(
            closed_at=timezone.now() - datetime.timedelta(hours=30)
        )
        notifications.sweep_awaiting_count()
        notifications.sweep_awaiting_count()
        assert Notification.objects.filter(kind="awaiting_count", lay=lay).count() == 1


class TestDigest:
    @pytest.fixture
    def with_alerts(self, make_lay, user, as_role):
        recipient = as_role("cutting_supervisor")
        from django.contrib.auth.models import User as U

        U.objects.filter(username="u_cutting_supervisor").update(
            email="sup@example.com"
        )
        lay = make_lay(lines=[
            {"roll_length_m": "101.00", "plies": 20, "remnant_m": "0.50"},
        ])
        services.close_lay(lay, user, override_reason="اختبار")
        return lay

    def test_it_sends_one_email_per_person(self, with_alerts):
        call_command("send_cutting_digest")
        assert len(mail.outbox) >= 1
        assert "sup@example.com" in mail.outbox[0].to

    def test_the_alerts_are_marked_and_not_sent_again(self, with_alerts):
        call_command("send_cutting_digest")
        first = len(mail.outbox)
        assert Notification.objects.filter(
            kind="shortage", emailed_at__isnull=False
        ).exists()
        call_command("send_cutting_digest")
        assert len(mail.outbox) == first  # nothing new to say

    def test_several_lays_arrive_as_one_email_not_one_each(
        self, make_lay, user, as_role
    ):
        """The whole point of a digest (SRS 11.1)."""
        as_role("cutting_supervisor")
        from django.contrib.auth.models import User as U

        U.objects.filter(username="u_cutting_supervisor").update(email="s@example.com")
        for _ in range(3):
            lay = make_lay(lines=[
                {"roll_length_m": "101.00", "plies": 20, "remnant_m": "0.50"},
            ])
            services.close_lay(lay, user, override_reason="اختبار")

        call_command("send_cutting_digest")
        to_sup = [m for m in mail.outbox if "s@example.com" in m.to]
        assert len(to_sup) == 1
        assert "3" in to_sup[0].subject

    def test_one_address_gets_one_email_however_many_people_share_it(
        self, make_lay, user, as_role
    ):
        """notify_emails routes several people to one inbox on a small
        install. Grouping by user would send that inbox a copy each — the
        exact pile-up a digest exists to prevent."""
        from cutting.models import CuttingSettings

        for role in ["cutting_supervisor", "production_manager", "admin"]:
            as_role(role)
        settings_row = CuttingSettings.get_solo()
        settings_row.notify_emails = "shared@example.com"
        settings_row.save()

        lay = make_lay(lines=[
            {"roll_length_m": "101.00", "plies": 20, "remnant_m": "0.50"},
        ])
        services.close_lay(lay, user, override_reason="اختبار")

        call_command("send_cutting_digest")
        to_shared = [m for m in mail.outbox if "shared@example.com" in m.to]
        assert len(to_shared) == 1, [m.to for m in mail.outbox]
        # and the one email names the lay once, not three times
        assert to_shared[0].body.count(f"فرشة {lay.pk}") == 1

    def test_an_alert_with_nobody_to_mail_is_not_left_queued_forever(
        self, make_lay, user, as_role
    ):
        as_role("cutting_supervisor")  # no email address on the account
        lay = make_lay(lines=[
            {"roll_length_m": "101.00", "plies": 20, "remnant_m": "0.50"},
        ])
        services.close_lay(lay, user, override_reason="اختبار")
        call_command("send_cutting_digest")
        assert Notification.objects.filter(
            kind="shortage", emailed_at__isnull=True
        ).count() == 0

    def test_dry_run_sends_nothing_and_marks_nothing(self, with_alerts):
        call_command("send_cutting_digest", "--dry-run")
        assert mail.outbox == []
        assert not Notification.objects.filter(emailed_at__isnull=False).exists()

    def test_the_nag_stays_in_system_and_is_never_emailed(
        self, make_lay, user, as_role
    ):
        as_role("cutting_supervisor")
        from django.contrib.auth.models import User as U

        U.objects.filter(username="u_cutting_supervisor").update(email="s@example.com")
        lay = make_lay(status=Lay.STATUS_CLOSED)
        Lay.objects.filter(pk=lay.pk).update(
            closed_at=timezone.now() - datetime.timedelta(hours=30)
        )
        call_command("send_cutting_digest")
        assert Notification.objects.filter(kind="awaiting_count").exists()
        assert mail.outbox == []


class TestNotificationApi:
    def test_a_user_sees_only_their_own(self, make_lay, user, as_role, api, make_user):
        as_role("cutting_supervisor")
        as_role("production_manager")
        lay = make_lay(lines=[
            {"roll_length_m": "101.00", "plies": 20, "remnant_m": "0.50"},
        ])
        services.close_lay(lay, user, override_reason="اختبار")

        api.force_authenticate(make_user("cutting_supervisor"))
        mine = api.get("/api/cutting/notifications/")
        assert mine.data["count"] == 1
        assert mine.data["results"][0]["kind"] == "shortage"

    def test_unread_count_and_marking_read(self, make_lay, user, as_role, api, make_user):
        as_role("cutting_supervisor")
        lay = make_lay(lines=[
            {"roll_length_m": "101.00", "plies": 20, "remnant_m": "0.50"},
        ])
        services.close_lay(lay, user, override_reason="اختبار")
        api.force_authenticate(make_user("cutting_supervisor"))

        assert api.get("/api/cutting/notifications/unread_count/").data["unread"] == 1
        assert api.post("/api/cutting/notifications/mark-read/", {},
                        format="json").data["marked"] == 1
        assert api.get("/api/cutting/notifications/unread_count/").data["unread"] == 0

    def test_they_are_read_only(self, as_role):
        assert as_role("admin").post("/api/cutting/notifications/", {},
                                     format="json").status_code == 405


class TestResendBackend:
    """The Resend adapter (config/email_backends.py). No network here — the
    library call is stubbed; what is under test is the payload we hand it."""

    def _backend(self, monkeypatch, sent, api_key="re_test"):
        from config.email_backends import ResendBackend

        class FakeEmails:
            @staticmethod
            def send(payload):
                sent.append(payload)
                return {"id": "fake"}

        import resend

        monkeypatch.setattr(resend, "Emails", FakeEmails)
        backend = ResendBackend()
        backend.api_key = api_key
        return backend

    def test_a_plain_message_becomes_a_text_payload(self, monkeypatch, settings):
        from django.core.mail import EmailMessage

        sent = []
        backend = self._backend(monkeypatch, sent)
        count = backend.send_messages([
            EmailMessage(subject="عنوان", body="نص", from_email="a@b.c", to=["x@y.z"])
        ])
        assert count == 1
        assert sent[0]["to"] == ["x@y.z"]
        assert sent[0]["subject"] == "عنوان"
        assert sent[0]["text"] == "نص"
        assert "html" not in sent[0]

    def test_an_html_message_becomes_an_html_payload(self, monkeypatch):
        from django.core.mail import EmailMessage

        sent = []
        backend = self._backend(monkeypatch, sent)
        msg = EmailMessage(subject="s", body="<b>hi</b>", from_email="a@b.c", to=["x@y.z"])
        msg.content_subtype = "html"
        backend.send_messages([msg])
        assert sent[0]["html"] == "<b>hi</b>"

    def test_cc_bcc_and_reply_to_are_carried(self, monkeypatch):
        from django.core.mail import EmailMessage

        sent = []
        backend = self._backend(monkeypatch, sent)
        backend.send_messages([
            EmailMessage(subject="s", body="b", from_email="a@b.c", to=["x@y.z"],
                         cc=["c@y.z"], bcc=["d@y.z"], reply_to=["r@y.z"])
        ])
        assert sent[0]["cc"] == ["c@y.z"]
        assert sent[0]["bcc"] == ["d@y.z"]
        assert sent[0]["reply_to"] == ["r@y.z"]

    def test_one_failure_does_not_stop_the_rest(self, monkeypatch):
        from django.core.mail import EmailMessage

        from config.email_backends import ResendBackend

        calls = []

        class FlakyEmails:
            @staticmethod
            def send(payload):
                calls.append(payload)
                if payload["to"] == ["bad@y.z"]:
                    raise RuntimeError("rejected")
                return {"id": "ok"}

        import resend

        monkeypatch.setattr(resend, "Emails", FlakyEmails)
        backend = ResendBackend(fail_silently=True)
        backend.api_key = "re_test"
        count = backend.send_messages([
            EmailMessage(subject="s", body="b", from_email="a@b.c", to=["bad@y.z"]),
            EmailMessage(subject="s", body="b", from_email="a@b.c", to=["good@y.z"]),
        ])
        assert len(calls) == 2      # it tried both
        assert count == 1           # and reported only the one that landed

    def test_a_missing_key_is_refused_not_silently_dropped(self, monkeypatch):
        from django.core.mail import EmailMessage

        sent = []
        backend = self._backend(monkeypatch, sent, api_key="")
        with pytest.raises(ValueError):
            backend.send_messages([
                EmailMessage(subject="s", body="b", from_email="a@b.c", to=["x@y.z"])
            ])
        assert sent == []

    def test_nothing_to_send_is_not_an_error(self, monkeypatch):
        sent = []
        assert self._backend(monkeypatch, sent, api_key="").send_messages([]) == 0
