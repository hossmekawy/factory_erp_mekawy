"""The formulas in SRS 5.2 and 5.3, pinned to the backend's numbers."""
from decimal import Decimal

import pytest

from cutting import services
from cutting.models import Lay, LayLine

pytestmark = pytest.mark.django_db


class TestExpectedMetrage:
    def test_lay_length_divided_by_pieces_per_ply(self, make_lay):
        """SRS 5.2: 9 m over 9 trousers is 1 m a piece."""
        lay = make_lay(lay_length_m="9.00", sizes_raw="30 32 33 34 36 36 38 38 38")
        assert lay.expected_metrage == Decimal("1.0000")

    def test_it_does_not_divide_by_the_number_of_distinct_sizes(self, make_lay):
        """4.95 m over 6 pieces — the size set has 4 distinct sizes, 6 pieces."""
        lay = make_lay()
        assert lay.pieces_per_ply == 6
        assert lay.expected_metrage == Decimal("0.8250")


class TestTotalPlies:
    def test_plain_sum_without_splices(self, make_lay):
        lay = make_lay(lines=[
            {"roll_length_m": "50.00", "plies": 10, "remnant_m": "0.50"},
            {"roll_length_m": "40.00", "plies": 8, "remnant_m": "0.40"},
        ])
        assert lay.total_plies == 18

    def test_a_splice_subtracts_the_ply_it_shares(self, make_lay):
        """SRS 4.8: the spliced ply was written on both notebook rows."""
        lay = make_lay(lines=[
            {"roll_length_m": "50.00", "plies": 10, "remnant_m": "0",
             "roll_end_action": LayLine.ACTION_SPLICE},
            {"roll_length_m": "40.00", "plies": 8, "remnant_m": "0.40"},
        ])
        assert lay.total_plies == 17  # 18 − 1 splice
        assert lay.has_splice is True

    def test_two_splices_subtract_two(self, make_lay):
        lay = make_lay(lines=[
            {"roll_length_m": "50.00", "plies": 10, "remnant_m": "0",
             "roll_end_action": LayLine.ACTION_SPLICE},
            {"roll_length_m": "30.00", "plies": 6, "remnant_m": "0",
             "roll_end_action": LayLine.ACTION_SPLICE},
            {"roll_length_m": "40.00", "plies": 8, "remnant_m": "0.40"},
        ])
        assert lay.total_plies == 22  # 24 − 2

    def test_stored_and_new_roll_do_not_subtract(self, make_lay):
        lay = make_lay(lines=[
            {"roll_length_m": "50.00", "plies": 10, "remnant_m": "0.50",
             "roll_end_action": LayLine.ACTION_STORED},
            {"roll_length_m": "40.00", "plies": 8, "remnant_m": "0.40",
             "roll_end_action": LayLine.ACTION_NEW_ROLL},
        ])
        assert lay.total_plies == 18
        assert lay.has_splice is False

    def test_theoretical_pieces_follow_the_corrected_ply_count(self, make_lay):
        lay = make_lay(lines=[
            {"roll_length_m": "50.00", "plies": 10, "remnant_m": "0",
             "roll_end_action": LayLine.ACTION_SPLICE},
            {"roll_length_m": "40.00", "plies": 8, "remnant_m": "0.40"},
        ])
        assert lay.theoretical_pieces == 17 * 6


class TestRealMetrage:
    def test_it_divides_by_the_counted_pieces_not_the_theoretical_ones(
        self, make_lay, user
    ):
        """SRS 5.2: 500 m ÷ 490 counted = 1.02 m a piece.

        The theoretical count here is 600, so dividing by that would give
        0.8333 — a number that would quietly hide every piece that was lost.
        """
        lay = make_lay(
            lay_length_m="5.00", status=Lay.STATUS_CLOSED,
            lines=[{"roll_length_m": "500.00", "plies": 100, "remnant_m": "0"}],
        )
        assert lay.theoretical_pieces == 600
        services.record_output(lay, user, actual_pieces=490)
        lay.refresh_from_db()
        assert lay.real_metrage == Decimal("1.0204")  # 500 / 490
        assert lay.real_metrage != lay.total_roll_length_m / lay.theoretical_pieces

    def test_it_stays_none_until_the_count_is_recorded(self, make_lay):
        lay = make_lay()
        assert lay.real_metrage is None
        assert lay.deviation_pct is None

    def test_deviation_is_the_gap_from_expected_as_a_percentage(self, make_lay, user):
        lay = make_lay(
            lay_length_m="1.00", sizes_raw="32", status=Lay.STATUS_CLOSED,
            lines=[{"roll_length_m": "102.00", "plies": 100, "remnant_m": "0"}],
        )
        services.record_output(lay, user, actual_pieces=100)
        lay.refresh_from_db()
        assert lay.expected_metrage == Decimal("1.0000")
        assert lay.real_metrage == Decimal("1.0200")
        assert lay.deviation_pct == Decimal("2.00")

    def test_a_negative_deviation_means_less_fabric_than_planned(self, make_lay, user):
        lay = make_lay(
            lay_length_m="1.00", sizes_raw="32", status=Lay.STATUS_CLOSED,
            lines=[{"roll_length_m": "98.00", "plies": 100, "remnant_m": "0"}],
        )
        services.record_output(lay, user, actual_pieces=100)
        lay.refresh_from_db()
        assert lay.deviation_pct == Decimal("-2.00")


class TestShortage:
    def test_roll_lengths_minus_consumed_and_remnants(self, make_lay):
        """SRS 5.3. 100 m on the table, 20 plies × 4.95 consumed, 0.50 left
        over: 100 − (99 + 0.50) = 0.50 m unaccounted for."""
        lay = make_lay(lines=[
            {"roll_length_m": "100.00", "plies": 20, "remnant_m": "0.50"},
        ])
        assert lay.total_roll_length_m == Decimal("100.00")
        assert lay.consumed_m == Decimal("99.00")
        assert lay.total_remnant_m == Decimal("0.50")
        assert lay.fabric_shortage_m == Decimal("0.50")

    def test_a_lay_that_adds_up_has_no_shortage(self, make_lay):
        lay = make_lay()  # 99.50 = 20 × 4.95 + 0.50
        assert lay.fabric_shortage_m == Decimal("0.00")
        assert lay.has_shortage is False

    def test_the_flag_only_trips_past_the_tolerance(self, make_lay, settings_row):
        """Default tolerance is 0.5% of the fabric on the table."""
        within = make_lay(lines=[  # 0.40 m short of 99.90 → 0.40%
            {"roll_length_m": "99.90", "plies": 20, "remnant_m": "0.50"},
        ])
        assert within.fabric_shortage_m == Decimal("0.40")
        assert within.has_shortage is False

        beyond = make_lay(lines=[  # 1.50 m short of 101.00 → 1.49%
            {"roll_length_m": "101.00", "plies": 20, "remnant_m": "0.50"},
        ])
        assert beyond.fabric_shortage_m == Decimal("1.50")
        assert beyond.has_shortage is True

    def test_surplus_fabric_is_not_a_shortage(self, make_lay):
        lay = make_lay(lines=[
            {"roll_length_m": "95.00", "plies": 20, "remnant_m": "0.50"},
        ])
        assert lay.fabric_shortage_m == Decimal("-4.50")
        assert lay.has_shortage is False

    def test_the_splice_correction_flows_into_the_shortage(self, make_lay):
        """One fewer ply means less fabric consumed, so more looks missing."""
        lay = make_lay(lines=[
            {"roll_length_m": "50.00", "plies": 10, "remnant_m": "0",
             "roll_end_action": LayLine.ACTION_SPLICE},
            {"roll_length_m": "49.50", "plies": 10, "remnant_m": "0"},
        ])
        assert lay.total_plies == 19
        assert lay.consumed_m == Decimal("94.05")  # 19 × 4.95, not 20 × 4.95
        assert lay.fabric_shortage_m == Decimal("5.45")


class TestPiecesLoss:
    def test_theoretical_minus_counted(self, make_lay, user):
        lay = make_lay(status=Lay.STATUS_CLOSED,
                       lines=[{"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50"}])
        assert lay.theoretical_pieces == 120
        services.record_output(lay, user, actual_pieces=118)
        lay.refresh_from_db()
        loss = services.pieces_loss(lay)
        assert loss["pieces_loss"] == 2
        assert loss["pieces_loss_pct"] == Decimal("1.67")
        assert loss["exceeds_tolerance"] is False  # default tolerance is 2%

    def test_it_trips_past_the_pieces_tolerance(self, make_lay, user):
        lay = make_lay(status=Lay.STATUS_CLOSED,
                       lines=[{"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50"}])
        services.record_output(lay, user, actual_pieces=110)
        lay.refresh_from_db()
        assert services.pieces_loss(lay)["exceeds_tolerance"] is True

    def test_it_is_unknown_before_the_count(self, make_lay):
        assert services.pieces_loss(make_lay())["pieces_loss"] is None


class TestQuickMode:
    def test_one_aggregate_line_produces_the_same_totals(self, make_lay):
        """SRS 5.1: in a hurry the supervisor enters metres and plies only."""
        lay = make_lay(
            entry_mode=Lay.MODE_QUICK,
            lines=[{"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50",
                    "is_aggregate": True}],
        )
        assert lay.total_plies == 20
        assert lay.theoretical_pieces == 120
        assert lay.fabric_shortage_m == Decimal("0.00")


class TestRemnantClassification:
    def test_under_one_metre_is_waste(self, make_lay):
        lay = make_lay(lines=[{"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50"}])
        assert lay.lines.first().remnant_disposition == LayLine.DISPOSITION_WASTE

    def test_one_metre_and_over_is_usable(self, make_lay):
        lay = make_lay(
            lay_length_m="4.95",
            lines=[{"roll_length_m": "100.00", "plies": 20, "remnant_m": "1.00"}],
        )
        assert lay.lines.first().remnant_disposition == LayLine.DISPOSITION_USABLE

    def test_the_remnant_log_mirrors_the_lines(self, make_lay):
        lay = make_lay(lines=[
            {"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50",
             "article": "MEGAN", "lot_no": "L1"},
            {"roll_length_m": "50.00", "plies": 10, "remnant_m": "0"},
        ])
        logs = services.sync_remnant_logs(lay)
        assert len(logs) == 1  # the zero-remnant line logs nothing
        assert logs[0].article == "MEGAN"
        assert logs[0].disposition == LayLine.DISPOSITION_WASTE


class TestStoredNotProperty:
    def test_the_derived_columns_are_filterable(self, make_lay, user):
        """The whole reason these are columns: SRS 7.1.2 range filters."""
        lay = make_lay(
            lay_length_m="1.00", sizes_raw="32", status=Lay.STATUS_CLOSED,
            lines=[{"roll_length_m": "102.00", "plies": 100, "remnant_m": "0"}],
        )
        services.record_output(lay, user, actual_pieces=100)
        assert Lay.objects.filter(deviation_pct__gte=Decimal("1.5")).count() == 1
        assert Lay.objects.filter(deviation_pct__gte=Decimal("5")).count() == 0
        assert Lay.objects.filter(real_metrage__range=(1, 2)).count() == 1
        # 2 m unaccounted for out of 102 is 1.96%, past the 0.5% tolerance.
        assert Lay.objects.filter(has_shortage=True).count() == 1

    def test_recalculate_writes_what_it_returns(self, make_lay):
        lay = make_lay()
        values = services.recalculate(lay)
        lay.refresh_from_db()
        for field, value in values.items():
            assert getattr(lay, field) == value
