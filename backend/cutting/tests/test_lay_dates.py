"""Multi-day lays, intersection filtering, and team-leader hours (SRS 5.6, 6)."""
import datetime

import pytest

from cutting import services
from cutting.models import Lay
from cutting.tests.conftest import TODAY
from hr import attendance

pytestmark = pytest.mark.django_db

DAY = datetime.timedelta(days=1)


class TestLayPeriod:
    def test_a_same_day_lay_fills_end_date_from_start(self, make_lay):
        """Stored, never null: an intersection filter on COALESCE cannot use
        the index."""
        lay = Lay.objects.get(pk=make_lay().pk)
        assert lay.end_date == lay.start_date
        assert lay.working_days == 1
        assert lay.is_multi_day is False

    def test_end_date_defaults_on_save_when_left_out(self, make_lay, bank,
                                                    garment_model, leader, user, size_set):
        from decimal import Decimal

        lay = Lay(
            start_date=TODAY, bank=bank, garment_model=garment_model,
            size_set=size_set, team_leader=leader, entered_by=user,
            lay_width_cm=Decimal("167"), lay_length_m=Decimal("4.95"),
            pieces_per_ply=6,
        )
        lay.save()
        assert lay.end_date == TODAY

    def test_a_two_day_lay_counts_both_days(self, make_lay):
        lay = make_lay(end_date=TODAY + DAY)
        assert lay.working_days == 2
        assert lay.is_multi_day is True

    def test_an_end_date_before_the_start_is_refused(self, make_lay):
        from django.core.exceptions import ValidationError

        lay = make_lay()
        lay.end_date = lay.start_date - DAY
        with pytest.raises(ValidationError):
            lay.clean()

    def test_the_database_refuses_it_too(self, make_lay):
        from django.db import IntegrityError, transaction

        lay = make_lay()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Lay.objects.filter(pk=lay.pk).update(end_date=lay.start_date - DAY)


class TestIntersectionFilter:
    """A lay belongs to every period its days touch, not just the one it began in."""

    @pytest.fixture
    def spread(self, make_lay):
        # Runs 20 → 22 August.
        return make_lay(start_date=TODAY, end_date=TODAY + 2 * DAY)

    def test_found_by_its_start_day(self, spread):
        qs = services.lays_intersecting(Lay.objects.all(), TODAY, TODAY)
        assert list(qs) == [spread]

    def test_found_by_a_middle_day_it_never_started_on(self, spread):
        """The plain `start_date` filter everyone writes first would miss this."""
        qs = services.lays_intersecting(Lay.objects.all(), TODAY + DAY, TODAY + DAY)
        assert list(qs) == [spread]
        assert not Lay.objects.filter(start_date=TODAY + DAY).exists()

    def test_found_by_its_end_day(self, spread):
        qs = services.lays_intersecting(Lay.objects.all(), TODAY + 2 * DAY, TODAY + 2 * DAY)
        assert list(qs) == [spread]

    def test_found_by_a_window_that_merely_overlaps_it(self, spread):
        qs = services.lays_intersecting(
            Lay.objects.all(), TODAY - 5 * DAY, TODAY + 5 * DAY
        )
        assert list(qs) == [spread]

    def test_not_found_before_it_starts(self, spread):
        qs = services.lays_intersecting(Lay.objects.all(), TODAY - 5 * DAY, TODAY - DAY)
        assert list(qs) == []

    def test_not_found_after_it_ends(self, spread):
        qs = services.lays_intersecting(Lay.objects.all(), TODAY + 3 * DAY, TODAY + 9 * DAY)
        assert list(qs) == []

    def test_an_open_ended_window_filters_on_one_side_only(self, spread):
        assert list(services.lays_intersecting(Lay.objects.all(), TODAY + DAY, None)) == [spread]
        assert list(services.lays_intersecting(Lay.objects.all(), None, TODAY + DAY)) == [spread]
        assert list(services.lays_intersecting(Lay.objects.all(), None, None)) == [spread]


class TestAttendanceHours:
    def test_first_punch_in_last_punch_out(self, punch, leader):
        punch(leader.employee_code, TODAY, 8, 0)
        punch(leader.employee_code, TODAY, 12, 30)
        punch(leader.employee_code, TODAY, 17, 0)
        period = attendance.hours_for(leader.employee_code, TODAY, TODAY)
        assert period.total_hours == 9.0  # 8:00 → 17:00, the midday punch ignored
        assert period.measured_days == 1

    def test_a_single_punch_scores_zero_hours(self, punch, leader):
        """25% of the live employee-days look like this — in, never out."""
        punch(leader.employee_code, TODAY, 8)
        period = attendance.hours_for(leader.employee_code, TODAY, TODAY)
        assert period.days_present == 1
        assert period.measured_days == 0
        assert period.total_hours == 0.0

    def test_hours_add_up_across_the_days_of_the_period(self, punch, leader):
        punch(leader.employee_code, TODAY, 8)
        punch(leader.employee_code, TODAY, 16)
        punch(leader.employee_code, TODAY + DAY, 9)
        punch(leader.employee_code, TODAY + DAY, 15)
        period = attendance.hours_for(leader.employee_code, TODAY, TODAY + DAY)
        assert period.total_hours == 14.0
        assert period.measured_days == 2

    def test_it_joins_on_the_code_not_the_employee_fk(self, punch, leader):
        """17% of the live rows have a null FK; the code is always there."""
        log = punch(leader.employee_code, TODAY, 8)
        punch(leader.employee_code, TODAY, 17)
        assert log.employee is None
        assert attendance.hours_for(leader.employee_code, TODAY, TODAY).total_hours == 9.0

    def test_present_codes_lists_everyone_who_punched_in_the_range(self, punch):
        punch("101", TODAY, 8)
        punch("202", TODAY + DAY, 8)
        punch("303", TODAY + 9 * DAY, 8)
        assert attendance.present_codes(TODAY, TODAY + DAY) == {"101", "202"}

    def test_the_history_start_is_the_earliest_punch(self, punch):
        assert attendance.attendance_data_start() is None
        punch("101", TODAY, 8)
        punch("101", TODAY - 30 * DAY, 8)
        assert attendance.attendance_data_start() == TODAY - 30 * DAY


class TestProductivity:
    def test_pieces_divided_by_the_leaders_hours(self, make_lay, punch, leader, user):
        lay = make_lay(status=Lay.STATUS_CLOSED)
        punch(leader.employee_code, TODAY, 8)
        punch(leader.employee_code, TODAY, 18)  # 10 hours
        services.record_output(lay, user, actual_pieces=120)
        lay.refresh_from_db()

        stats = services.team_leader_productivity(lay)
        assert stats["total_hours"] == 10.0
        assert stats["pieces_per_hour"] == 12.0
        assert stats["is_reliable"] is True

    def test_zero_hour_days_leave_the_denominator_instead_of_zeroing_it(
        self, make_lay, punch, leader, user
    ):
        """The man worked; he just never punched out. Averaging in a zero
        would understate him, and dividing by zero would crash."""
        lay = make_lay(status=Lay.STATUS_CLOSED, end_date=TODAY + DAY)
        punch(leader.employee_code, TODAY, 8)
        punch(leader.employee_code, TODAY, 18)      # a real 10-hour day
        punch(leader.employee_code, TODAY + DAY, 8)  # in only — no hours
        services.record_output(lay, user, actual_pieces=120)
        lay.refresh_from_db()

        stats = services.team_leader_productivity(lay)
        assert stats["total_hours"] == 10.0        # not 10 spread over 2 days
        assert stats["pieces_per_hour"] == 12.0    # not 6.0
        assert stats["measured_days"] == 1
        assert stats["days_present"] == 2
        assert stats["total_days"] == 2

    def test_coverage_is_stated_and_flagged_when_thin(self, make_lay, punch, leader, user):
        lay = make_lay(status=Lay.STATUS_CLOSED, end_date=TODAY + 3 * DAY)
        punch(leader.employee_code, TODAY, 8)
        punch(leader.employee_code, TODAY, 18)
        services.record_output(lay, user, actual_pieces=120)
        lay.refresh_from_db()

        stats = services.team_leader_productivity(lay)
        assert stats["coverage_pct"] == 25.0
        assert stats["is_reliable"] is False  # below 50%
        assert stats["coverage_label"] == "مبني على 1 يوم من أصل 4"

    def test_no_hours_at_all_gives_no_number_rather_than_a_made_up_one(
        self, make_lay, punch, leader, user
    ):
        lay = make_lay(status=Lay.STATUS_CLOSED)
        punch(leader.employee_code, TODAY, 8)  # in only
        services.record_output(lay, user, actual_pieces=120)
        lay.refresh_from_db()

        stats = services.team_leader_productivity(lay)
        assert stats["pieces_per_hour"] is None
        assert "بصمة واحدة" in stats["unavailable_reason"]

    def test_no_punches_at_all_says_so(self, make_lay, punch, leader, user):
        lay = make_lay(status=Lay.STATUS_CLOSED)
        services.record_output(lay, user, actual_pieces=120)
        lay.refresh_from_db()
        stats = services.team_leader_productivity(lay)
        assert stats["pieces_per_hour"] is None
        assert "مفيش بصمة" in stats["unavailable_reason"]

    def test_an_uncounted_lay_has_no_productivity_yet(self, make_lay, punch, leader):
        punch(leader.employee_code, TODAY, 8)
        punch(leader.employee_code, TODAY, 18)
        stats = services.team_leader_productivity(make_lay())
        assert stats["pieces_per_hour"] is None
        assert stats["unavailable_reason"] == "الفرشة لسه مستنية ترقيم"
