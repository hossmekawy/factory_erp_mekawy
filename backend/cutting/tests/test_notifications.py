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
