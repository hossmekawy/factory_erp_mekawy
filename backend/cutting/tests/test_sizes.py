"""Size-text parsing and the actual-pieces distribution (SRS 4.5, 4.9)."""
import pytest

from cutting import sizes


class TestParse:
    def test_the_srs_example(self):
        assert sizes.parse_sizes("30 32 32 34 34 36") == [
            ("30", 1), ("32", 2), ("34", 2), ("36", 1)
        ]

    def test_piece_count_is_tokens_not_distinct_sizes(self):
        """Six sizes written, four distinct — pieces per ply is six."""
        assert sizes.total_pieces("30 32 32 34 34 36") == 6
        assert sizes.total_pieces("30 32 33 34 36 36 38 38 38") == 9

    def test_notebook_writes_sizes_in_brackets(self):
        assert sizes.parse_sizes("(32)(34)(34)") == [("32", 1), ("34", 2)]

    def test_arabic_indic_digits(self):
        assert sizes.parse_sizes("٣٠ ٣٢ ٣٢") == [("30", 1), ("32", 2)]

    @pytest.mark.parametrize(
        "raw", ["30,32,32", "30، 32، 32", "30/32/32", "30-32-32", "  30   32  32 "]
    )
    def test_separators(self, raw):
        assert sizes.parse_sizes(raw) == [("30", 1), ("32", 2)]

    def test_order_follows_the_notebook_not_numeric_order(self):
        assert [s for s, _ in sizes.parse_sizes("36 30 32")] == ["36", "30", "32"]

    def test_letter_sizes(self):
        assert sizes.parse_sizes("s m m l") == [("S", 1), ("M", 2), ("L", 1)]

    @pytest.mark.parametrize("raw", ["", "   ", None, "()"])
    def test_empty_text_is_rejected(self, raw):
        with pytest.raises(sizes.SizeParseError):
            sizes.parse_sizes(raw)

    def test_round_trip(self):
        raw = "30 32 32 34 34 36"
        assert sizes.format_sizes(sizes.parse_sizes(raw)) == raw


class TestDistribute:
    def test_the_corrected_srs_table(self):
        """SRS 4.9 worked example: 490 pieces over `30 32 33 34 36 36 38 38 38`.

        The v1.8 table added up to 488. These are the v1.9 figures.
        """
        breakdown = sizes.parse_sizes("30 32 33 34 36 36 38 38 38")
        assert sizes.distribute(490, breakdown) == {
            "38": 163, "36": 109, "30": 55, "32": 55, "33": 54, "34": 54
        }

    def test_total_always_matches_exactly(self):
        """Anything else is a bug, in the SRS's own words."""
        breakdown = sizes.parse_sizes("30 32 33 34 36 36 38 38 38")
        for total in range(0, 1000):
            assert sum(sizes.distribute(total, breakdown).values()) == total

    def test_exact_division_leaves_no_remainder_to_hand_out(self):
        breakdown = sizes.parse_sizes("30 32 32 34 34 36")  # 6 per ply
        assert sizes.distribute(600, breakdown) == {
            "30": 100, "32": 200, "34": 200, "36": 100
        }

    def test_ties_go_to_the_smaller_size_first(self):
        """Four equal sizes, one piece left over: it lands on 30, not 36."""
        breakdown = sizes.parse_sizes("30 32 34 36")
        result = sizes.distribute(9, breakdown)
        assert result == {"30": 3, "32": 2, "34": 2, "36": 2}

    def test_letter_sizes_tie_break_alphabetically(self):
        result = sizes.distribute(5, [("L", 1), ("M", 1), ("S", 1)])
        assert sum(result.values()) == 5
        assert result["L"] == 2 and result["M"] == 2 and result["S"] == 1

    def test_single_size_takes_everything(self):
        assert sizes.distribute(490, [("32", 6)]) == {"32": 490}

    def test_zero_pieces_gives_every_size_zero(self):
        breakdown = sizes.parse_sizes("30 32 34")
        assert sizes.distribute(0, breakdown) == {"30": 0, "32": 0, "34": 0}

    def test_a_size_may_end_up_with_zero_when_the_total_is_tiny(self):
        result = sizes.distribute(1, [("30", 1), ("32", 3)])
        assert result == {"30": 0, "32": 1}

    @pytest.mark.parametrize(
        "total,breakdown",
        [(-1, [("30", 1)]), (10, []), (10, [("30", 0)]), (10, [("30", -2)])],
    )
    def test_nonsense_input_is_rejected(self, total, breakdown):
        with pytest.raises(ValueError):
            sizes.distribute(total, breakdown)
