"""V2 → V10 from SRS 5.5, checked on the backend.

V1 is gone: it needed a width on every roll and told the spreader nothing he
was not already holding in his hands.

Each test breaks exactly one rule on an otherwise closable lay, so a failure
names the rule that regressed.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from cutting import services, validators
from cutting.models import Lay, LayLine, LaySizeBreakdown
from cutting.tests.conftest import TODAY

pytestmark = pytest.mark.django_db


def codes(issues, level=None):
    return sorted(i.code for i in issues if level is None or i.level == level)


class TestV2Positives:
    def test_zero_plies_is_rejected_by_the_database(self, make_lay):
        lay = make_lay()
        with pytest.raises(Exception):  # CheckConstraint line_plies_positive
            LayLine.objects.create(
                lay=lay, line_no=99, roll_length_m=Decimal("10"), plies=0
            )

    def test_zero_length_is_rejected_by_clean(self, make_lay):
        lay = make_lay()
        line = LayLine(lay=lay, line_no=99, roll_length_m=Decimal("0"), plies=5)
        with pytest.raises(ValidationError) as exc:
            line.clean()
        assert "roll_length_m" in exc.value.message_dict


class TestV3Remnant:
    def test_a_remnant_as_long_as_the_lay_is_rejected(self, make_lay):
        """Another whole ply would have fitted — the row is wrong."""
        lay = make_lay()  # lay_length 4.95
        line = LayLine(
            lay=lay, line_no=99, roll_length_m=Decimal("50"), plies=9,
            remnant_m=Decimal("5.00"),
        )
        with pytest.raises(ValidationError) as exc:
            line.clean()
        assert "الباقي أكبر من طول الفرشة" in str(exc.value)

    def test_a_shorter_remnant_passes(self, make_lay):
        lay = make_lay()
        line = LayLine(
            lay=lay, line_no=99, roll_length_m=Decimal("50"), plies=9,
            remnant_m=Decimal("4.94"),
        )
        line.clean()  # must not raise


class TestV4RollArithmetic:
    """Never a block. A supervisor who cannot close edits the number instead of
    re-measuring the roll, so blocking would buy tidy rows and cost true ones."""

    def test_a_roll_that_does_not_add_up_warns_in_detailed_mode(self, make_lay):
        """20 × 4.95 + 0.50 = 99.50, but the notebook says 90."""
        lay = make_lay(lines=[
            {"roll_length_m": "90.00", "plies": 20, "remnant_m": "0.50"},
        ])
        issues = validators.check_v4_roll_arithmetic(
            lay, list(lay.lines.all()), Decimal("0.5")
        )
        assert codes(issues) == ["V4"]
        assert issues[0].level == validators.WARNING

    def test_it_warns_in_quick_mode_too(self, make_lay):
        lay = make_lay(
            entry_mode=Lay.MODE_QUICK,
            lines=[{"roll_length_m": "90.00", "plies": 20, "remnant_m": "0.50"}],
        )
        issues = validators.check_v4_roll_arithmetic(
            lay, list(lay.lines.all()), Decimal("0.5")
        )
        assert issues[0].level == validators.WARNING

    def test_the_lay_is_flagged_so_the_reports_can_find_it(self, make_lay):
        lay = make_lay(lines=[
            {"roll_length_m": "90.00", "plies": 20, "remnant_m": "0.50"},
        ])
        assert lay.has_length_mismatch is True
        assert Lay.objects.filter(has_length_mismatch=True).count() == 1

    def test_a_lay_that_adds_up_is_not_flagged(self, make_lay):
        assert make_lay().has_length_mismatch is False

    def test_the_drift_does_not_stop_the_close(self, make_lay, user):
        """The whole point of the change: it closes, and it stays flagged."""
        lay = make_lay(lines=[
            {"roll_length_m": "90.00", "plies": 20, "remnant_m": "0.50"},
        ])
        services.close_lay(lay, user, override_reason="التوب اتقاس بالتقريب")
        lay.refresh_from_db()
        assert lay.status == Lay.STATUS_CLOSED
        assert lay.has_length_mismatch is True

    def test_drift_inside_the_tolerance_passes(self, make_lay):
        lay = make_lay(lines=[
            {"roll_length_m": "99.70", "plies": 20, "remnant_m": "0.50"},  # +0.2%
        ])
        assert validators.check_v4_roll_arithmetic(
            lay, list(lay.lines.all()), Decimal("0.5")
        ) == []

    def test_a_spliced_row_is_exempt(self, make_lay):
        """The roll ran out mid-ply; its arithmetic is shared with the next row."""
        lay = make_lay(lines=[
            {"roll_length_m": "30.00", "plies": 20, "remnant_m": "0",
             "roll_end_action": LayLine.ACTION_SPLICE},
            {"roll_length_m": "69.50", "plies": 20, "remnant_m": "0.50"},
        ])
        issues = validators.check_v4_roll_arithmetic(
            lay, list(lay.lines.all()), Decimal("0.5")
        )
        assert [i.line_no for i in issues] == [2]  # only the unspliced row

    def test_the_aggregate_row_is_exempt(self, make_lay):
        lay = make_lay(lines=[
            {"roll_length_m": "90.00", "plies": 20, "remnant_m": "0.50",
             "is_aggregate": True},
        ])
        assert validators.check_v4_roll_arithmetic(
            lay, list(lay.lines.all()), Decimal("0.5")
        ) == []


class TestV5AtLeastOneLine:
    def test_an_empty_lay_cannot_close(self, make_lay, user):
        lay = make_lay(lines=[])
        with pytest.raises(services.LayValidationError) as exc:
            services.close_lay(lay, user)
        assert "V5" in codes(exc.value.issues)


class TestV6BreakdownTotal:
    def test_sizes_must_add_up_to_the_pieces_in_a_ply(self, make_lay):
        lay = make_lay()  # 6 pieces per ply
        lay.size_breakdown.filter(size="36").delete()  # now 5
        issues = validators.check_v6_breakdown_total(lay, list(lay.size_breakdown.all()))
        assert codes(issues) == ["V6"]
        assert issues[0].level == validators.ERROR

    def test_a_matching_breakdown_passes(self, make_lay):
        lay = make_lay()
        assert validators.check_v6_breakdown_total(
            lay, list(lay.size_breakdown.all())
        ) == []

    def test_the_size_set_fills_pieces_per_ply_automatically(self, make_lay):
        lay = make_lay(sizes_raw="30 32 32 34 34 36 36 38 38")
        assert lay.pieces_per_ply == 9
        assert sum(b.pieces_in_ply for b in lay.size_breakdown.all()) == 9

    def test_a_single_size_lay_gets_one_row(self, make_lay):
        lay = make_lay(sizes_raw="32")
        assert list(lay.size_breakdown.values_list("size", "pieces_in_ply")) == [("32", 1)]


class TestV7TeamLeaderPresence:
    def test_a_leader_with_no_punch_in_the_period_warns(self, make_lay, punch, leader):
        punch("999", TODAY, 8)  # somebody else was there, so the history exists
        lay = make_lay()
        issues = validators.check_v7_team_leader_present(lay)
        assert codes(issues) == ["V7"]
        assert issues[0].level == validators.WARNING

    def test_one_punch_on_any_day_of_the_period_is_enough(self, make_lay, punch, leader):
        """SRS 5.6: presence is checked across the whole lay, not one day."""
        punch(leader.employee_code, TODAY + __import__("datetime").timedelta(days=1), 8)
        lay = make_lay(end_date=TODAY + __import__("datetime").timedelta(days=2))
        assert validators.check_v7_team_leader_present(lay) == []

    def test_a_lay_older_than_the_punch_history_is_skipped_silently(
        self, make_lay, punch, leader
    ):
        """SRS 6: that history does not exist, so there is nothing to warn about."""
        import datetime

        punch("999", TODAY, 8)
        old = make_lay(
            start_date=TODAY - datetime.timedelta(days=60),
            end_date=TODAY - datetime.timedelta(days=60),
        )
        assert validators.check_v7_team_leader_present(old) == []

    def test_a_backfilled_lay_is_skipped(self, make_lay, punch):
        punch("999", TODAY, 8)
        lay = make_lay(is_backfill=True)
        assert validators.check_v7_team_leader_present(lay) == []

    def test_no_punches_at_all_means_nothing_to_check(self, make_lay):
        assert validators.check_v7_team_leader_present(make_lay()) == []


class TestV8ShadeMix:
    def test_more_than_one_shade_is_reported_not_blocked(self, make_lay):
        lay = make_lay(lines=[
            {"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50",
             "shade_note": "أسود"},
            {"roll_length_m": "49.50", "plies": 10, "remnant_m": "0",
             "shade_note": "أسود غامق"},
        ])
        issues = validators.check_v8_shade_mix(list(lay.lines.all()))
        assert codes(issues) == ["V8"]
        assert issues[0].level == validators.INFO  # allowed and normal

    def test_one_shade_says_nothing(self, make_lay):
        lay = make_lay(lines=[
            {"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50",
             "shade_note": "أسود"},
        ])
        assert validators.check_v8_shade_mix(list(lay.lines.all())) == []


class TestV9ActualNotAboveTheoretical:
    def test_counting_more_than_the_plies_allow_is_rejected(self, make_lay, user):
        lay = make_lay(status=Lay.STATUS_CLOSED)  # 20 plies × 6 = 120
        with pytest.raises(services.LayValidationError) as exc:
            services.record_output(lay, user, actual_pieces=121)
        assert "V9" in codes(exc.value.issues)

    def test_counting_exactly_the_theoretical_total_is_fine(self, make_lay, user):
        lay = make_lay(status=Lay.STATUS_CLOSED)
        services.record_output(lay, user, actual_pieces=120)
        lay.refresh_from_db()
        assert lay.status == Lay.STATUS_COUNTED


class TestSheetImageRequired:
    def test_no_notebook_photo_means_no_closing(self, make_lay, user):
        """SRS 4.6 — the photo is the original record."""
        lay = make_lay(with_sheet=False)
        with pytest.raises(services.LayValidationError) as exc:
            services.close_lay(lay, user)
        assert "V10" in codes(exc.value.issues)


class TestClosing:
    def test_a_clean_lay_closes_and_freezes_its_numbers(self, make_lay, user):
        lay = make_lay()
        result = services.close_lay(lay, user)
        lay.refresh_from_db()
        assert lay.status == Lay.STATUS_CLOSED
        assert lay.closed_by == user and lay.closed_at is not None
        assert result["values"]["total_plies"] == 20
        assert lay.audit_entries.filter(action="close").exists()

    def test_a_warning_blocks_the_close_until_a_reason_is_given(
        self, make_lay, punch, user
    ):
        punch("999", TODAY, 8)  # history exists, the leader is not in it → V7
        lay = make_lay()
        with pytest.raises(services.LayValidationError):
            services.close_lay(lay, user)

        services.close_lay(lay, user, override_reason="الراجل كان في فرع تاني")
        lay.refresh_from_db()
        assert lay.status == Lay.STATUS_CLOSED
        assert lay.audit_entries.get(action="close").reason


class TestDistributionOnCounting:
    def test_the_count_is_spread_across_the_sizes_automatically(self, make_lay, user):
        # 55 plies x 9 = 495 theoretical, so 490 counted is a plausible count.
        lay = make_lay(sizes_raw="30 32 33 34 36 36 38 38 38", status=Lay.STATUS_CLOSED,
                       lines=[{"roll_length_m": "272.25", "plies": 55, "remnant_m": "0"}])
        services.record_output(lay, user, actual_pieces=490)
        got = dict(lay.size_breakdown.values_list("size", "actual_pieces"))
        assert got == {"38": 163, "36": 109, "30": 55, "32": 55, "33": 54, "34": 54}
        assert sum(got.values()) == 490

    def test_a_manual_override_is_flagged_and_must_still_add_up(self, make_lay, user):
        lay = make_lay(sizes_raw="30 32", status=Lay.STATUS_CLOSED)
        services.record_output(lay, user, actual_pieces=40, manual={"30": 25, "32": 15})
        rows = {b.size: b for b in lay.size_breakdown.all()}
        assert rows["30"].actual_pieces == 25
        assert all(b.is_manually_adjusted for b in rows.values())

    def test_a_manual_override_that_does_not_add_up_is_rejected(self, make_lay, user):
        lay = make_lay(sizes_raw="30 32", status=Lay.STATUS_CLOSED)
        with pytest.raises(ValueError):
            services.record_output(lay, user, actual_pieces=40, manual={"30": 25, "32": 10})

    def test_a_manual_override_missing_a_size_is_rejected(self, make_lay, user):
        lay = make_lay(sizes_raw="30 32", status=Lay.STATUS_CLOSED)
        with pytest.raises(ValueError):
            services.record_output(lay, user, actual_pieces=40, manual={"30": 40})
