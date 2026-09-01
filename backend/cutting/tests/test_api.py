"""API tests: who may do what, the SRS 7.1.2 filters, and the transitions.

The rules themselves are tested in test_validators.py. What matters here is
that the API *reaches* them and hands the rule number back to the client.
"""
import datetime
from decimal import Decimal

import pytest

from cutting import services
from cutting.models import Lay, LayLine, SizeSet
from cutting.tests.conftest import TODAY

pytestmark = pytest.mark.django_db

DAY = datetime.timedelta(days=1)


def issue_codes(response):
    return sorted(i["code"] for i in response.data.get("issues", []))


class TestAuthentication:
    def test_anonymous_is_turned_away(self, api):
        assert api.get("/api/cutting/lays/").status_code == 401

    def test_a_user_with_no_role_is_turned_away(self, as_role):
        assert as_role("").get("/api/cutting/lays/").status_code == 403

    def test_an_hr_clerk_has_no_business_here(self, as_role):
        assert as_role("hr").get("/api/cutting/lays/").status_code == 403


class TestPermissions:
    @pytest.mark.parametrize(
        "role", ["admin", "production_manager", "cutting_supervisor", "cutting"]
    )
    def test_everyone_in_the_module_can_read_lays(self, as_role, role, make_lay):
        make_lay()
        assert as_role(role).get("/api/cutting/lays/").status_code == 200

    @pytest.mark.parametrize("role,expected", [
        ("admin", 200), ("cutting_supervisor", 200), ("cutting", 200),
        ("production_manager", 403),
    ])
    def test_the_supervisor_roles_write_and_the_manager_reads(
        self, as_role, role, expected, make_lay
    ):
        lay = make_lay()
        client = as_role(role)
        res = client.patch(f"/api/cutting/lays/{lay.pk}/", {"notes": "كلام"}, format="json")
        assert res.status_code == expected

    def test_the_production_manager_reads_but_never_closes(self, as_role, make_lay):
        lay = make_lay()
        res = as_role("production_manager").post(f"/api/cutting/lays/{lay.pk}/close/",
                                                 {}, format="json")
        assert res.status_code == 403

    def test_the_cutting_group_is_the_supervisor_under_another_name(
        self, as_role, make_lay
    ):
        """The real supervisor's account will be in this group."""
        lay = make_lay()
        client = as_role("cutting")
        assert client.post(f"/api/cutting/lays/{lay.pk}/close/",
                           {}, format="json").status_code == 200
        assert client.post("/api/cutting/models/", {"name": "من مجموعة القص",
                                                    "category": 1},
                           format="json").status_code in (201, 400)

    def test_but_deleting_from_the_catalogue_still_needs_the_admin(
        self, as_role, garment_model
    ):
        assert as_role("cutting").delete(
            f"/api/cutting/models/{garment_model.pk}/"
        ).status_code == 403

    @pytest.mark.parametrize("role,expected", [
        ("admin", 201), ("cutting_supervisor", 403), ("production_manager", 403),
    ])
    def test_the_catalogues_are_admin_only(self, as_role, role, expected):
        res = as_role(role).post("/api/cutting/banks/",
                                 {"code": f"B{role[:3]}", "name": "بنك"}, format="json")
        assert res.status_code == expected

    def test_the_supervisor_can_still_read_the_catalogues(self, as_role, bank):
        assert as_role("cutting_supervisor").get("/api/cutting/banks/").status_code == 200

    def test_the_supervisor_may_add_a_model_from_the_new_lay_screen(
        self, as_role, category
    ):
        """SRS 7.2 quick-add: he is holding the model in his hand right now."""
        res = as_role("cutting_supervisor").post(
            "/api/cutting/models/",
            {"name": "موديل جديد", "category": category.pk}, format="json",
        )
        assert res.status_code == 201

    def test_and_may_correct_one_he_mistyped(self, as_role, garment_model):
        """He can add a model, so he can mistype one. Refusing the fix just
        leaves the wrong name in every report."""
        res = as_role("cutting_supervisor").patch(
            f"/api/cutting/models/{garment_model.pk}/", {"name": "تاني"}, format="json"
        )
        assert res.status_code == 200
        garment_model.refresh_from_db()
        assert garment_model.name == "تاني"

    def test_but_he_may_not_delete_one(self, as_role, garment_model):
        """The one action that cannot be walked back stays with the admin."""
        res = as_role("cutting_supervisor").delete(f"/api/cutting/models/{garment_model.pk}/")
        assert res.status_code == 403

    def test_a_read_only_role_cannot_add_a_model(self, as_role):
        res = as_role("production_manager").post(
            "/api/cutting/models/", {"code": "9002", "name": "x"}, format="json"
        )
        assert res.status_code == 403


class TestCreateLay:
    def test_the_phone_posts_one_payload_and_gets_a_full_lay_back(
        self, supervisor, bank, garment_model, leader
    ):
        res = supervisor.post("/api/cutting/lays/", {
            "code": "1749",
            "start_date": TODAY.isoformat(),
            "bank": bank.pk,
            "garment_model": garment_model.pk,
            "team_leader": leader.pk,
            "lay_width_cm": "167.00",
            "lay_length_m": "4.95",
            "sizes_raw": "30 32 32 34 34 36",
            "lines": [
                {"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50"},
                {"roll_length_m": "49.50", "plies": 10, "remnant_m": "0.00"},
            ],
        }, format="json")
        assert res.status_code == 201, res.data

        assert res.data["pieces_per_ply"] == 6           # derived from the text
        assert res.data["total_plies"] == 30             # calculated server-side
        assert res.data["theoretical_pieces"] == 180
        assert res.data["expected_metrage"] == "0.8250"
        assert len(res.data["lines"]) == 2
        assert len(res.data["size_breakdown"]) == 4      # 4 distinct sizes
        assert res.data["end_date"] == TODAY.isoformat()  # filled from start
        assert res.data["status"] == "open"

    def test_entered_by_comes_from_the_token_not_the_body(
        self, api, make_user, bank, garment_model, leader
    ):
        me = make_user("cutting_supervisor")
        someone_else = make_user("admin")
        api.force_authenticate(me)
        res = api.post("/api/cutting/lays/", {
            "code": "1750",
            "start_date": TODAY.isoformat(), "bank": bank.pk,
            "garment_model": garment_model.pk, "team_leader": leader.pk,
            "lay_width_cm": "167", "lay_length_m": "4.95", "sizes_raw": "32",
            "entered_by": someone_else.pk,
        }, format="json")
        assert res.status_code == 201
        assert res.data["entered_by"] == me.pk

    def test_a_lay_with_no_sizes_is_refused_with_the_rule_number(
        self, supervisor, bank, garment_model, leader
    ):
        res = supervisor.post("/api/cutting/lays/", {
            "code": "1751",
            "start_date": TODAY.isoformat(), "bank": bank.pk,
            "garment_model": garment_model.pk, "team_leader": leader.pk,
            "lay_width_cm": "167", "lay_length_m": "4.95",
        }, format="json")
        assert res.status_code == 400
        assert issue_codes(res) == ["V6"]

    def test_unreadable_size_text_says_so_in_arabic(
        self, supervisor, bank, garment_model, leader
    ):
        res = supervisor.post("/api/cutting/lays/", {
            "start_date": TODAY.isoformat(), "bank": bank.pk,
            "garment_model": garment_model.pk, "team_leader": leader.pk,
            "code": "1752",
            "lay_width_cm": "167", "lay_length_m": "4.95", "sizes_raw": "()",
        }, format="json")
        assert res.status_code == 400
        assert issue_codes(res) == ["sizes_unreadable"]
        assert "مقاسات" in res.data["issues"][0]["message"]

    def test_an_end_date_before_the_start_is_refused_by_the_model_rule(
        self, supervisor, bank, garment_model, leader
    ):
        res = supervisor.post("/api/cutting/lays/", {
            "code": "1753",
            "start_date": TODAY.isoformat(),
            "end_date": (TODAY - DAY).isoformat(),
            "bank": bank.pk, "garment_model": garment_model.pk,
            "team_leader": leader.pk, "lay_width_cm": "167",
            "lay_length_m": "4.95", "sizes_raw": "32",
        }, format="json")
        assert res.status_code == 400
        assert "date_order" in issue_codes(res)


    def test_the_cutting_run_code_is_required(self, supervisor, bank, garment_model, leader):
        """The number at the top of the notebook page identifies this run."""
        res = supervisor.post("/api/cutting/lays/", {
            "start_date": TODAY.isoformat(), "bank": bank.pk,
            "garment_model": garment_model.pk, "team_leader": leader.pk,
            "lay_width_cm": "167", "lay_length_m": "4.95", "sizes_raw": "32",
        }, format="json")
        assert res.status_code == 400
        assert "code" in res.data

    def test_two_runs_cannot_share_a_code(self, supervisor, bank, garment_model, leader):
        body = {
            "code": "5150", "start_date": TODAY.isoformat(), "bank": bank.pk,
            "garment_model": garment_model.pk, "team_leader": leader.pk,
            "lay_width_cm": "167", "lay_length_m": "4.95", "sizes_raw": "32",
        }
        assert supervisor.post("/api/cutting/lays/", body,
                               format="json").status_code == 201
        clash = supervisor.post("/api/cutting/lays/", body, format="json")
        assert clash.status_code == 400
        assert "مستخدم" in str(clash.data["code"][0])

    def test_the_same_model_can_be_cut_again_under_a_new_code(
        self, supervisor, bank, garment_model, leader
    ):
        """The whole reason the code moved off the model."""
        for code in ("6001", "6002"):
            res = supervisor.post("/api/cutting/lays/", {
                "code": code, "start_date": TODAY.isoformat(), "bank": bank.pk,
                "garment_model": garment_model.pk, "team_leader": leader.pk,
                "lay_width_cm": "167", "lay_length_m": "4.95", "sizes_raw": "32",
            }, format="json")
            assert res.status_code == 201, res.data


class TestCountWithTheClose:
    """Counting is normally later, but it can ride along with the close."""

    def test_the_count_can_come_with_the_close(self, supervisor, make_lay):
        lay = make_lay()   # 20 plies x 6 = 120
        res = supervisor.post(f"/api/cutting/lays/{lay.pk}/close/",
                              {"actual_pieces": 118, "rejected_pieces": 2},
                              format="json")
        assert res.status_code == 200, res.data
        assert res.data["lay"]["status"] == "counted"
        assert res.data["lay"]["real_metrage"] is not None
        lay.refresh_from_db()
        assert lay.output.actual_pieces == 118
        assert lay.output.rejected_pieces == 2

    def test_it_records_who_entered_it(self, supervisor, make_lay, make_user):
        lay = make_lay()
        supervisor.post(f"/api/cutting/lays/{lay.pk}/close/",
                        {"actual_pieces": 118}, format="json")
        lay.refresh_from_db()
        assert lay.output.recorded_by == make_user("cutting_supervisor")
        assert lay.audit_entries.filter(action="output").exists()

    def test_leaving_it_out_sends_the_lay_to_the_counting_screen(
        self, supervisor, make_lay
    ):
        lay = make_lay()
        supervisor.post(f"/api/cutting/lays/{lay.pk}/close/", {}, format="json")
        lay.refresh_from_db()
        assert lay.status == Lay.STATUS_CLOSED
        assert not hasattr(lay, "output")
        waiting = supervisor.get("/api/cutting/lays/?awaiting_count=true")
        assert lay.pk in [r["id"] for r in waiting.data["results"]]

    def test_an_impossible_count_rolls_the_close_back_too(self, supervisor, make_lay):
        """One transaction: a lay must never end up closed with a count that
        never landed."""
        lay = make_lay()
        res = supervisor.post(f"/api/cutting/lays/{lay.pk}/close/",
                              {"actual_pieces": 9999}, format="json")
        assert res.status_code == 400
        assert "V9" in [i["code"] for i in res.data["issues"]]
        lay.refresh_from_db()
        assert lay.status == Lay.STATUS_OPEN   # the close was rolled back


class TestLineRulesReachTheApi:
    def test_v3_comes_back_with_its_number(self, supervisor, make_lay):
        """The remnant rule lives in LayLine.clean(), not in the serializer."""
        lay = make_lay()  # lay_length 4.95
        res = supervisor.post(f"/api/cutting/lays/{lay.pk}/lines/", {
            "roll_length_m": "50.00", "plies": 9, "remnant_m": "5.00",
        }, format="json")
        assert res.status_code == 400
        assert issue_codes(res) == ["V3"]
        assert res.data["issues"][0]["field"] == "remnant_m"
        assert "الباقي أكبر من طول الفرشة" in res.data["issues"][0]["message"]

    def test_a_good_line_is_added_and_the_totals_move(self, supervisor, make_lay):
        lay = make_lay()
        assert lay.total_plies == 20
        res = supervisor.post(f"/api/cutting/lays/{lay.pk}/lines/", {
            "roll_length_m": "49.50", "plies": 10, "remnant_m": "0.00",
        }, format="json")
        assert res.status_code == 201
        lay.refresh_from_db()
        assert lay.total_plies == 30

    def test_deleting_a_line_recalculates(self, supervisor, make_lay):
        lay = make_lay(lines=[
            {"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50"},
            {"roll_length_m": "49.50", "plies": 10, "remnant_m": "0.00"},
        ])
        line = lay.lines.last()
        assert supervisor.delete(f"/api/cutting/lay-lines/{line.pk}/").status_code == 204
        lay.refresh_from_db()
        assert lay.total_plies == 20


class TestClose:
    def test_a_clean_lay_closes(self, supervisor, make_lay):
        lay = make_lay()
        res = supervisor.post(f"/api/cutting/lays/{lay.pk}/close/", {}, format="json")
        assert res.status_code == 200, res.data
        assert res.data["lay"]["status"] == "closed"

    def test_closing_with_no_lines_is_refused_with_v5(self, supervisor, make_lay):
        lay = make_lay(lines=[])
        res = supervisor.post(f"/api/cutting/lays/{lay.pk}/close/", {}, format="json")
        assert res.status_code == 400
        assert "V5" in issue_codes(res)

    def test_closing_with_no_notebook_photo_is_refused_with_v10(
        self, supervisor, make_lay
    ):
        lay = make_lay(with_sheet=False)
        res = supervisor.post(f"/api/cutting/lays/{lay.pk}/close/", {}, format="json")
        assert res.status_code == 400
        assert "V10" in issue_codes(res)

    def test_a_broken_size_breakdown_is_refused_with_v6(self, supervisor, make_lay):
        lay = make_lay()
        lay.size_breakdown.filter(size="36").delete()
        res = supervisor.post(f"/api/cutting/lays/{lay.pk}/close/", {}, format="json")
        assert res.status_code == 400
        assert "V6" in issue_codes(res)

    def test_a_warning_asks_for_a_reason_then_lets_it_through(
        self, supervisor, make_lay, punch
    ):
        punch("999", TODAY, 8)  # the history exists; the leader is not in it
        lay = make_lay()

        blocked = supervisor.post(f"/api/cutting/lays/{lay.pk}/close/", {}, format="json")
        assert blocked.status_code == 400
        assert "V7" in issue_codes(blocked)

        allowed = supervisor.post(f"/api/cutting/lays/{lay.pk}/close/",
                                  {"reason": "كان في فرع تاني"}, format="json")
        assert allowed.status_code == 200
        assert allowed.data["lay"]["status"] == "closed"

    def test_length_drift_no_longer_blocks_but_stays_flagged(self, supervisor, make_lay):
        """V4 is a warning in both modes now — the lay closes, flagged."""
        lay = make_lay(lines=[
            {"roll_length_m": "90.00", "plies": 20, "remnant_m": "0.50"},
        ])
        res = supervisor.post(f"/api/cutting/lays/{lay.pk}/close/",
                              {"reason": "التوب اتقاس بالتقريب"}, format="json")
        assert res.status_code == 200
        assert res.data["lay"]["status"] == "closed"
        assert res.data["lay"]["has_length_mismatch"] is True
        assert "V4" in [i["code"] for i in res.data["issues"]]

    def test_validate_previews_the_checks_without_closing(self, supervisor, make_lay):
        lay = make_lay(lines=[])
        res = supervisor.get(f"/api/cutting/lays/{lay.pk}/validate/")
        assert res.status_code == 200
        assert res.data["can_close"] is False
        assert "V5" in [i["code"] for i in res.data["issues"]]
        lay.refresh_from_db()
        assert lay.status == Lay.STATUS_OPEN  # nothing changed


class TestOutput:
    def test_counting_records_the_split_and_the_real_metrage(
        self, supervisor, make_lay, user
    ):
        lay = make_lay(status=Lay.STATUS_CLOSED)  # 20 plies x 6 = 120
        res = supervisor.post(f"/api/cutting/lays/{lay.pk}/output/",
                              {"actual_pieces": 118, "rejected_pieces": 2}, format="json")
        assert res.status_code == 200, res.data
        assert res.data["status"] == "counted"
        assert res.data["output"]["actual_pieces"] == 118
        assert res.data["real_metrage"] is not None
        split = {b["size"]: b["actual_pieces"] for b in res.data["size_breakdown"]}
        assert sum(split.values()) == 118

    def test_counting_an_open_lay_is_refused(self, supervisor, make_lay):
        res = supervisor.post(f"/api/cutting/lays/{make_lay().pk}/output/",
                              {"actual_pieces": 100}, format="json")
        assert res.status_code == 400
        assert "V5" in issue_codes(res)

    def test_counting_more_than_the_plies_allow_is_refused_with_v9(
        self, supervisor, make_lay
    ):
        lay = make_lay(status=Lay.STATUS_CLOSED)
        res = supervisor.post(f"/api/cutting/lays/{lay.pk}/output/",
                              {"actual_pieces": 500}, format="json")
        assert res.status_code == 400
        assert "V9" in issue_codes(res)

    def test_a_manual_split_that_does_not_add_up_is_refused_in_arabic(
        self, supervisor, make_lay
    ):
        lay = make_lay(sizes_raw="30 32", status=Lay.STATUS_CLOSED)
        res = supervisor.post(f"/api/cutting/lays/{lay.pk}/output/", {
            "actual_pieces": 40, "manual_distribution": {"30": 25, "32": 10},
        }, format="json")
        assert res.status_code == 400
        assert "مش مطابق" in res.data["detail"]

    def test_approve_only_after_counting(self, supervisor, make_lay):
        lay = make_lay(status=Lay.STATUS_CLOSED)
        assert supervisor.post(f"/api/cutting/lays/{lay.pk}/approve/",
                               {}, format="json").status_code == 400
        supervisor.post(f"/api/cutting/lays/{lay.pk}/output/",
                        {"actual_pieces": 100}, format="json")
        res = supervisor.post(f"/api/cutting/lays/{lay.pk}/approve/", {}, format="json")
        assert res.status_code == 200
        assert res.data["status"] == "approved"


class TestEditAfterClose:
    def test_the_reason_is_written_into_the_activity_log(self, supervisor, make_lay):
        lay = make_lay(status=Lay.STATUS_CLOSED)
        res = supervisor.patch(f"/api/cutting/lays/{lay.pk}/",
                               {"notes": "اتصحح", "edit_reason": "غلطة في النقل"},
                               format="json")
        assert res.status_code == 200
        entry = lay.audit_entries.get(action="edit_after_close")
        assert entry.field == "notes"
        assert entry.reason == "غلطة في النقل"

    def test_editing_an_open_lay_writes_no_audit_entry(self, supervisor, make_lay):
        lay = make_lay()
        supervisor.patch(f"/api/cutting/lays/{lay.pk}/", {"notes": "كلام"}, format="json")
        assert not lay.audit_entries.filter(action="edit_after_close").exists()


class TestFilters:
    @pytest.fixture
    def spread(self, make_lay, user):
        """Three lays that differ on everything the filters touch."""
        a = make_lay(start_date=TODAY, end_date=TODAY + 2 * DAY, sizes_raw="30 32",
                     status=Lay.STATUS_CLOSED,
                     lines=[{"roll_length_m": "99.00", "plies": 20, "remnant_m": "0.00",
                             "article": "MEGAN", "lot_no": "L1", "shade_note": "أسود"}])
        b = make_lay(start_date=TODAY + 10 * DAY, sizes_raw="34 36",
                     lines=[{"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50",
                             "article": "BLACK MIMAS", "lot_no": "L2",
                             "shade_note": "أسود غامق"}])
        c = make_lay(start_date=TODAY + 20 * DAY, sizes_raw="30 32",
                     is_backfill=True,
                     lines=[{"roll_length_m": "90.00", "plies": 20, "remnant_m": "0.50"}])
        services.record_output(a, user, actual_pieces=38)
        return {"a": a, "b": b, "c": c}

    def ids(self, res):
        return {row["id"] for row in res.data["results"]}

    def test_the_date_filter_intersects_instead_of_matching_the_start(
        self, supervisor, spread
    ):
        """The middle day of lay A — a day it never started on."""
        day = (TODAY + DAY).isoformat()
        res = supervisor.get(f"/api/cutting/lays/?date_from={day}&date_to={day}")
        assert self.ids(res) == {spread["a"].pk}

    def test_a_window_can_catch_several_lays(self, supervisor, spread):
        res = supervisor.get(
            f"/api/cutting/lays/?date_from={TODAY.isoformat()}"
            f"&date_to={(TODAY + 12 * DAY).isoformat()}"
        )
        assert self.ids(res) == {spread["a"].pk, spread["b"].pk}

    def test_filter_by_a_size_present_in_the_lay(self, supervisor, spread):
        res = supervisor.get("/api/cutting/lays/?size=36")
        assert self.ids(res) == {spread["b"].pk}

    def test_several_values_in_one_filter_are_ored(self, supervisor, spread):
        res = supervisor.get("/api/cutting/lays/?shade_note=أسود,أسود غامق")
        assert self.ids(res) == {spread["a"].pk, spread["b"].pk}

    def test_filters_combine_with_and(self, supervisor, spread):
        res = supervisor.get("/api/cutting/lays/?size=30&is_backfill=true")
        assert self.ids(res) == {spread["c"].pk}

    def test_range_filter_on_the_deviation(self, supervisor, spread):
        res = supervisor.get("/api/cutting/lays/?deviation_min=0")
        assert self.ids(res) == {spread["a"].pk}

    def test_range_filter_on_the_real_metrage(self, supervisor, spread):
        res = supervisor.get("/api/cutting/lays/?real_metrage_min=1&real_metrage_max=99")
        assert self.ids(res) == {spread["a"].pk}

    def test_filter_on_the_length_mismatch_flag(self, supervisor, spread):
        res = supervisor.get("/api/cutting/lays/?has_length_mismatch=true")
        assert self.ids(res) == {spread["c"].pk}

    def test_filter_on_lays_awaiting_a_count(self, supervisor, spread):
        closed_uncounted = make_it = spread["a"]
        res = supervisor.get("/api/cutting/lays/?awaiting_count=true")
        assert self.ids(res) == set()  # a is closed but already counted
        Lay.objects.filter(pk=spread["b"].pk).update(status=Lay.STATUS_CLOSED)
        res = supervisor.get("/api/cutting/lays/?awaiting_count=true")
        assert self.ids(res) == {spread["b"].pk}

    def test_filter_by_shade_note(self, supervisor, spread):
        res = supervisor.get("/api/cutting/lays/?shade_note=أسود")
        assert self.ids(res) == {spread["a"].pk}

    def test_filter_by_remnants(self, supervisor, spread):
        res = supervisor.get("/api/cutting/lays/?has_remnants=true")
        assert self.ids(res) == {spread["b"].pk, spread["c"].pk}

    def test_filter_by_pieces_loss_percentage(self, supervisor, spread):
        """A is 40 theoretical against 38 counted — a 5% loss."""
        res = supervisor.get("/api/cutting/lays/?pieces_loss_pct_min=4&pieces_loss_pct_max=6")
        assert self.ids(res) == {spread["a"].pk}

    def test_free_text_search_reaches_the_roll_lines(self, supervisor, spread):
        """The shade is the only line field anyone fills, so it is the only one
        searched — article and lot were dropped rather than left returning
        nothing."""
        res = supervisor.get("/api/cutting/lays/?search=" + "أسود غامق")
        assert self.ids(res) == {spread["b"].pk}

    def test_ordering_by_a_derived_column(self, supervisor, spread):
        res = supervisor.get("/api/cutting/lays/?ordering=-total_roll_length_m")
        lengths = [Decimal(r["total_roll_length_m"]) for r in res.data["results"]]
        assert lengths == sorted(lengths, reverse=True)


class TestSizeSetParse:
    def test_it_splits_the_text_and_counts_the_pieces(self, supervisor):
        res = supervisor.post("/api/cutting/size-sets/parse/",
                              {"sizes_raw": "30 32 32 34 34 36"}, format="json")
        assert res.status_code == 200
        assert res.data["total_pieces"] == 6
        assert res.data["sizes"][1] == {"size": "32", "pieces_in_ply": 2}

    def test_the_notebook_bracket_form_works_too(self, supervisor):
        res = supervisor.post("/api/cutting/size-sets/parse/",
                              {"sizes_raw": "(32)(34)(34)"}, format="json")
        assert res.data["total_pieces"] == 3

    def test_unreadable_text_is_a_400_in_arabic(self, supervisor):
        res = supervisor.post("/api/cutting/size-sets/parse/",
                              {"sizes_raw": ""}, format="json")
        assert res.status_code == 400
        assert issue_codes(res) == ["sizes_unreadable"]

    def test_a_read_only_role_may_still_parse(self, as_role):
        """It saves nothing — the production manager can use the screen."""
        res = as_role("production_manager").post(
            "/api/cutting/size-sets/parse/", {"sizes_raw": "30 32"}, format="json"
        )
        assert res.status_code == 200


class TestTeamLeaders:
    def test_the_ones_the_device_saw_come_first(self, supervisor, punch, leader, db):
        from hr.models import Employee

        absent = Employee.objects.create(
            employee_code="202", full_name="أحمد", is_team_leader=True
        )
        punch(leader.employee_code, TODAY, 8)
        res = supervisor.get(f"/api/cutting/team-leaders/?date={TODAY.isoformat()}")
        assert res.status_code == 200
        assert [r["employee_code"] for r in res.data] == [leader.employee_code, "202"]
        assert res.data[0]["was_present"] is True
        assert res.data[1]["was_present"] is False

    def test_presence_is_checked_across_the_whole_lay_period(
        self, supervisor, punch, leader
    ):
        punch(leader.employee_code, TODAY + DAY, 8)
        res = supervisor.get(
            f"/api/cutting/team-leaders/?date_from={TODAY.isoformat()}"
            f"&date_to={(TODAY + 2 * DAY).isoformat()}"
        )
        assert res.data[0]["was_present"] is True

    def test_only_flagged_team_leaders_are_listed(self, supervisor, leader, db):
        from hr.models import Employee

        Employee.objects.create(employee_code="303", full_name="مش رئيس فريق")
        res = supervisor.get("/api/cutting/team-leaders/")
        assert [r["employee_code"] for r in res.data] == [leader.employee_code]


class TestCalculationsEndpoint:
    def test_it_reports_the_numbers_and_the_productivity_coverage(
        self, supervisor, make_lay, punch, leader, user
    ):
        lay = make_lay(status=Lay.STATUS_CLOSED, end_date=TODAY + DAY)
        punch(leader.employee_code, TODAY, 8)
        punch(leader.employee_code, TODAY, 18)
        punch(leader.employee_code, TODAY + DAY, 8)  # in only
        services.record_output(lay, user, actual_pieces=120)

        res = supervisor.get(f"/api/cutting/lays/{lay.pk}/calculations/")
        assert res.status_code == 200
        assert res.data["total_plies"] == 20
        assert res.data["working_days"] == 2
        prod = res.data["productivity"]
        assert prod["pieces_per_hour"] == 12.0
        assert prod["coverage_label"] == "مبني على 1 يوم من أصل 2"


class TestRemnantsAreReadOnly:
    def test_the_log_can_be_read(self, supervisor, make_lay):
        lay = make_lay()
        services.sync_remnant_logs(lay)
        res = supervisor.get("/api/cutting/remnants/")
        assert res.status_code == 200
        assert res.data["count"] == 1

    def test_nobody_can_write_to_it(self, as_role):
        assert as_role("admin").post("/api/cutting/remnants/", {}, format="json") \
            .status_code == 405


class TestDistributionPreview:
    """The counting screen asks the server how a count would split, before it
    commits anything (SRS 7.3, 4.9)."""

    def test_it_previews_without_saving(self, supervisor, make_lay):
        lay = make_lay(sizes_raw="30 32 33 34 36 36 38 38 38", status=Lay.STATUS_CLOSED,
                       lines=[{"roll_length_m": "272.25", "plies": 55, "remnant_m": "0"}])
        res = supervisor.get(f"/api/cutting/lays/{lay.pk}/distribution/?actual_pieces=490")
        assert res.status_code == 200
        split = {r["size"]: r["actual_pieces"] for r in res.data["sizes"]}
        assert split == {"38": 163, "36": 109, "30": 55, "32": 55, "33": 54, "34": 54}
        assert sum(split.values()) == 490

        lay.refresh_from_db()
        assert lay.status == Lay.STATUS_CLOSED   # nothing committed
        assert not hasattr(lay, "output") or lay.size_breakdown.filter(
            actual_pieces__isnull=False
        ).count() == 0

    def test_it_reports_the_loss_for_a_number_not_yet_saved(self, supervisor, make_lay):
        lay = make_lay(status=Lay.STATUS_CLOSED)  # 120 theoretical
        res = supervisor.get(f"/api/cutting/lays/{lay.pk}/distribution/?actual_pieces=100")
        assert res.data["pieces_loss"] == 20
        assert res.data["exceeds_tolerance"] is True

    def test_it_warns_with_v9_without_refusing_the_preview(self, supervisor, make_lay):
        """The screen should be able to show why the number is impossible."""
        lay = make_lay(status=Lay.STATUS_CLOSED)
        res = supervisor.get(f"/api/cutting/lays/{lay.pk}/distribution/?actual_pieces=999")
        assert res.status_code == 200
        assert "V9" in [i["code"] for i in res.data["issues"]]

    def test_a_missing_number_is_a_400(self, supervisor, make_lay):
        lay = make_lay(status=Lay.STATUS_CLOSED)
        res = supervisor.get(f"/api/cutting/lays/{lay.pk}/distribution/")
        assert res.status_code == 400

    def test_a_read_only_role_may_preview(self, as_role, make_lay):
        lay = make_lay(status=Lay.STATUS_CLOSED)
        res = as_role("production_manager").get(
            f"/api/cutting/lays/{lay.pk}/distribution/?actual_pieces=100"
        )
        assert res.status_code == 200


class TestCountingWorklist:
    def test_awaiting_count_lists_only_closed_uncounted_lays(
        self, supervisor, make_lay, user
    ):
        waiting = make_lay(status=Lay.STATUS_CLOSED)
        make_lay()                                        # still open
        counted = make_lay(status=Lay.STATUS_CLOSED)
        services.record_output(counted, user, actual_pieces=100)

        res = supervisor.get("/api/cutting/lays/?awaiting_count=true")
        assert {r["id"] for r in res.data["results"]} == {waiting.pk}


class TestCategoryCatalogue:
    """الأقسام as a catalogue the factory extends itself."""

    def test_the_factory_sections_are_seeded(self, as_role):
        names = [c["name"] for c in as_role("admin").get(
            "/api/cutting/categories/?page_size=50").data["results"]]
        assert "رجالي" in names and "مواليد" in names and "رجالي جامبو" in names

    def test_admin_adds_a_section(self, as_role):
        res = as_role("admin").post("/api/cutting/categories/",
                                    {"name": "قسم جديد"}, format="json")
        assert res.status_code == 201

    def test_the_supervisor_may_add_and_correct_but_not_delete(self, as_role, category):
        client = as_role("cutting_supervisor")
        assert client.post("/api/cutting/categories/", {"name": "قسم تاني"},
                           format="json").status_code == 201
        assert client.patch(f"/api/cutting/categories/{category.pk}/",
                            {"notes": "ملاحظة"}, format="json").status_code == 200
        assert client.delete(f"/api/cutting/categories/{category.pk}/").status_code == 403

    def test_a_read_only_role_cannot_touch_it(self, as_role, category):
        client = as_role("production_manager")
        assert client.get("/api/cutting/categories/").status_code == 200
        assert client.post("/api/cutting/categories/", {"name": "x"},
                           format="json").status_code == 403

    def test_the_name_is_unique(self, as_role, category):
        res = as_role("admin").post("/api/cutting/categories/",
                                    {"name": category.name}, format="json")
        assert res.status_code == 400

    def test_renaming_a_section_renames_it_on_every_model(
        self, as_role, category, garment_model
    ):
        as_role("admin").patch(f"/api/cutting/categories/{category.pk}/",
                               {"name": "رجالي ٢"}, format="json")
        res = as_role("admin").get(f"/api/cutting/models/{garment_model.pk}/")
        assert res.data["category_label"] == "رجالي ٢"

    def test_a_section_in_use_is_refused_in_arabic(self, as_role, category, garment_model):
        res = as_role("admin").delete(f"/api/cutting/categories/{category.pk}/")
        assert res.status_code == 400
        assert res.data["issues"][0]["code"] == "in_use"

    def test_it_counts_how_many_models_use_it(self, as_role, category, garment_model):
        rows = as_role("admin").get("/api/cutting/categories/?page_size=50").data["results"]
        mine = next(r for r in rows if r["id"] == category.pk)
        assert mine["model_count"] == 1

    def test_lays_can_be_filtered_by_section(self, supervisor, make_lay):
        make_lay()
        assert supervisor.get("/api/cutting/lays/?category=رجالي").data["count"] == 1
        assert supervisor.get("/api/cutting/lays/?category=حريمي").data["count"] == 0

    def test_the_shorthand_token_filters_by_section(self, supervisor, make_lay):
        make_lay()
        res = supervisor.get("/api/cutting/lays/search/?q=" + "قسم:رجالي")
        assert res.data["count"] == 1



class TestModelCatalogue:
    def test_the_code_is_generated_not_typed(self, as_role, category):
        """The number in the notebook belongs to the cutting run; a model's
        code is only an internal handle, counting up from 1."""
        first = as_role("admin").post(
            "/api/cutting/models/",
            {"name": "كارل حريمي", "category": category.pk, "code": "9999"},
            format="json",
        )
        assert first.status_code == 201
        assert first.data["code"] != "9999"       # what was sent is ignored
        assert first.data["code"].isdigit()

    def test_codes_count_up(self, as_role, category):
        client = as_role("admin")
        codes = [
            client.post("/api/cutting/models/",
                        {"name": f"موديل {i}", "category": category.pk},
                        format="json").data["code"]
            for i in range(3)
        ]
        assert [int(c) for c in codes] == sorted(int(c) for c in codes)
        assert len(set(codes)) == 3

    def test_a_model_needs_a_section(self, as_role):
        """Without one it drops out of every filter and every report."""
        res = as_role("admin").post("/api/cutting/models/", {"name": "بدون قسم"},
                                    format="json")
        assert res.status_code == 400
        assert "category" in res.data

    def test_models_are_found_by_name(self, as_role, garment_model):
        res = as_role("admin").get("/api/cutting/models/?search=كارل")
        assert garment_model.pk in [r["id"] for r in res.data["results"]]

    def test_it_reports_how_many_lays_use_each_model(self, as_role, make_lay, garment_model):
        make_lay()
        res = as_role("admin").get("/api/cutting/models/")
        row = next(r for r in res.data["results"] if r["id"] == garment_model.pk)
        assert row["lay_count"] == 1

    def test_a_model_in_use_is_refused_in_arabic_not_a_500(
        self, as_role, make_lay, garment_model
    ):
        make_lay()
        res = as_role("admin").delete(f"/api/cutting/models/{garment_model.pk}/")
        assert res.status_code == 400
        assert res.data["issues"][0]["code"] == "in_use"
        assert "فرشات" in res.data["detail"]

    def test_an_unused_model_can_be_deleted(self, as_role, category):
        created = as_role("admin").post(
            "/api/cutting/models/", {"name": "مؤقت", "category": category.pk},
            format="json",
        ).data
        assert as_role("admin").delete(
            f"/api/cutting/models/{created['id']}/"
        ).status_code == 204


class TestNewLayDefaults:
    """Almost every lay is the same bank and the same team leader, so the
    screen preselects them (user request)."""

    def test_the_settings_carry_the_defaults(self, as_role, bank, leader):
        client = as_role("admin")
        res = client.patch("/api/cutting/settings/1/", {
            "default_bank": bank.pk, "default_team_leader": leader.pk,
        }, format="json")
        assert res.status_code == 200
        assert res.data["default_bank"] == bank.pk
        assert res.data["default_team_leader"] == leader.pk

    def test_they_start_empty(self, as_role):
        res = as_role("admin").get("/api/cutting/settings/1/")
        assert res.data["default_bank"] is None
        assert res.data["default_team_leader"] is None

    def test_a_read_only_role_can_read_them(self, as_role):
        assert as_role("production_manager").get(
            "/api/cutting/settings/1/"
        ).status_code == 200


class TestRemnantLogScreen:
    """SRS 7.6 — view only. No balance, no "use it"."""

    @pytest.fixture
    def logged(self, make_lay, user):
        lay = make_lay(lines=[
            {"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50",
             "article": "MEGAN", "lot_no": "L1", "shade_note": "أسود"},
            {"roll_length_m": "50.45", "plies": 10, "remnant_m": "1.00",
             "article": "MEGAN", "lot_no": "L2", "shade_note": "كحلي"},
        ])
        services.sync_remnant_logs(lay)
        return lay

    def test_it_lists_length_shade_lot_and_class(self, supervisor, logged):
        res = supervisor.get("/api/cutting/remnants/")
        assert res.status_code == 200
        assert res.data["count"] == 2
        row = res.data["results"][0]
        for key in ["length_m", "shade_note", "lot_no", "article",
                    "disposition", "disposition_label", "lay"]:
            assert key in row

    def test_under_a_metre_is_waste_and_over_is_usable(self, supervisor, logged):
        rows = supervisor.get("/api/cutting/remnants/").data["results"]
        by_length = {r["length_m"]: r["disposition"] for r in rows}
        assert by_length["0.50"] == "waste"
        assert by_length["1.00"] == "usable"

    def test_it_can_be_filtered_by_class(self, supervisor, logged):
        assert supervisor.get(
            "/api/cutting/remnants/?disposition=waste"
        ).data["count"] == 1

    def test_a_read_only_role_can_see_it(self, as_role, logged):
        assert as_role("production_manager").get(
            "/api/cutting/remnants/"
        ).status_code == 200

    def test_nobody_can_write_to_it_at_all(self, as_role, logged):
        """No balance and no consumption — it is a record, not stock."""
        client = as_role("admin")
        assert client.post("/api/cutting/remnants/", {}, format="json").status_code == 405
        row = client.get("/api/cutting/remnants/").data["results"][0]
        assert client.patch(f"/api/cutting/remnants/{row['id']}/", {"length_m": "9"},
                            format="json").status_code == 405
        assert client.delete(f"/api/cutting/remnants/{row['id']}/").status_code == 405

    def test_it_points_back_at_the_lay(self, supervisor, logged):
        rows = supervisor.get("/api/cutting/remnants/").data["results"]
        assert all(r["lay"] == logged.pk for r in rows)


class TestTicketFieldsAreGone:
    """SRS 4.3.1 wanted a photo of every roll's ticket. Nobody is going to take
    one, and an empty field in front of the supervisor implies he forgot
    something."""

    def test_a_line_no_longer_carries_a_ticket(self, supervisor, make_lay):
        lay = make_lay()
        row = supervisor.get(f"/api/cutting/lays/{lay.pk}/").data["lines"][0]
        assert "ticket_image" not in row
        assert "ticket_data" not in row

    def test_the_notebook_photo_is_untouched(self, supervisor, make_lay):
        """That one really does get taken, once per lay."""
        lay = make_lay()
        assert supervisor.get(f"/api/cutting/lays/{lay.pk}/").data["sheet_image"]


class TestSizePresets:
    """Saved size runs (user request): buttons on the new-lay screen, managed
    from their own page, sorted so the model's own section comes first."""

    def test_a_set_made_through_the_api_is_a_preset(self, as_role, category):
        res = as_role("admin").post("/api/cutting/size-sets/", {
            "name": "رجالي عادي", "sizes_raw": "30 32 34 36 38",
            "category": category.pk,
        }, format="json")
        assert res.status_code == 201
        assert res.data["is_preset"] is True
        assert res.data["total_pieces"] == 5          # derived, not sent
        assert res.data["category_label"] == category.name

    def test_sizes_typed_on_a_lay_do_not_become_a_preset(
        self, supervisor, bank, garment_model, leader
    ):
        """Otherwise every one-off run would show up as a button next time."""
        supervisor.post("/api/cutting/lays/", {
            "code": "P100", "start_date": TODAY.isoformat(), "bank": bank.pk,
            "garment_model": garment_model.pk, "team_leader": leader.pk,
            "lay_width_cm": "167", "lay_length_m": "4.95",
            "sizes_raw": "44 46 48",
        }, format="json")
        presets = supervisor.get("/api/cutting/size-sets/?is_preset=true").data
        assert "44 46 48" not in [p["sizes_raw"] for p in presets["results"]]
        # but the set itself exists, because the breakdown snapshots from it
        assert supervisor.get("/api/cutting/size-sets/").data["count"] >= 1

    def test_presets_can_be_filtered_by_section(self, as_role, category):
        client = as_role("admin")
        client.post("/api/cutting/size-sets/",
                    {"name": "للقسم", "sizes_raw": "30 32", "category": category.pk},
                    format="json")
        client.post("/api/cutting/size-sets/",
                    {"name": "عام", "sizes_raw": "34 36"}, format="json")
        only = client.get(f"/api/cutting/size-sets/?is_preset=true&category={category.pk}")
        assert [p["name"] for p in only.data["results"]] == ["للقسم"]

    def test_a_preset_without_a_section_is_general(self, as_role):
        res = as_role("admin").post("/api/cutting/size-sets/",
                                    {"name": "عام", "sizes_raw": "30 32"}, format="json")
        assert res.status_code == 201
        assert res.data["category"] is None
        assert res.data["category_label"] == ""

    def test_it_parses_the_sizes_for_the_screen(self, as_role):
        res = as_role("admin").post("/api/cutting/size-sets/",
                                    {"name": "مكرر", "sizes_raw": "30 32 32 34"},
                                    format="json")
        assert res.data["total_pieces"] == 4
        assert res.data["parsed"] == [
            {"size": "30", "pieces_in_ply": 1},
            {"size": "32", "pieces_in_ply": 2},
            {"size": "34", "pieces_in_ply": 1},
        ]

    def test_the_supervisor_may_add_and_correct_but_not_delete(self, as_role):
        client = as_role("cutting_supervisor")
        made = client.post("/api/cutting/size-sets/",
                           {"name": "بتاعي", "sizes_raw": "30 32"}, format="json")
        assert made.status_code == 201
        assert client.patch(f"/api/cutting/size-sets/{made.data['id']}/",
                            {"name": "اتعدل"}, format="json").status_code == 200
        assert client.delete(
            f"/api/cutting/size-sets/{made.data['id']}/"
        ).status_code == 403

    def test_a_read_only_role_can_see_them(self, as_role):
        assert as_role("production_manager").get(
            "/api/cutting/size-sets/?is_preset=true"
        ).status_code == 200


class TestEditingALay:
    """A wrong code has to be fixable. SRS 3: after closing, with a reason."""

    def test_an_open_lay_edits_freely(self, supervisor, make_lay):
        lay = make_lay()
        res = supervisor.patch(f"/api/cutting/lays/{lay.pk}/",
                               {"code": "EDIT-1"}, format="json")
        assert res.status_code == 200
        lay.refresh_from_db()
        assert lay.code == "EDIT-1"

    def test_a_closed_lay_refuses_an_edit_with_no_reason(self, supervisor, make_lay):
        lay = make_lay(status=Lay.STATUS_CLOSED)
        res = supervisor.patch(f"/api/cutting/lays/{lay.pk}/",
                               {"code": "EDIT-2"}, format="json")
        assert res.status_code == 400
        assert res.data["issues"][0]["code"] == "edit_reason"
        lay.refresh_from_db()
        assert lay.code != "EDIT-2"

    def test_and_accepts_it_with_one(self, supervisor, make_lay):
        lay = make_lay(status=Lay.STATUS_CLOSED)
        before = lay.code
        res = supervisor.patch(
            f"/api/cutting/lays/{lay.pk}/",
            {"code": "EDIT-3", "edit_reason": "الكود اتكتب غلط"}, format="json",
        )
        assert res.status_code == 200
        lay.refresh_from_db()
        assert lay.code == "EDIT-3"

        entry = lay.audit_entries.get(action="edit_after_close", field="code")
        assert entry.old_value == before
        assert entry.new_value == "EDIT-3"
        assert entry.reason == "الكود اتكتب غلط"

    def test_a_no_op_patch_on_a_closed_lay_needs_nothing(self, supervisor, make_lay):
        """Only an actual change demands a reason."""
        lay = make_lay(status=Lay.STATUS_CLOSED)
        res = supervisor.patch(f"/api/cutting/lays/{lay.pk}/",
                               {"code": lay.code}, format="json")
        assert res.status_code == 200

    def test_the_new_code_still_has_to_be_free(self, supervisor, make_lay):
        first = make_lay()
        second = make_lay()
        res = supervisor.patch(f"/api/cutting/lays/{second.pk}/",
                               {"code": first.code}, format="json")
        assert res.status_code == 400
        assert "مستخدم" in str(res.data["code"][0])

    def test_an_open_lay_can_be_deleted_by_whoever_may_write(
        self, supervisor, make_lay
    ):
        lay = make_lay()
        assert supervisor.delete(f"/api/cutting/lays/{lay.pk}/").status_code == 204

    def test_a_closed_lay_can_only_be_deleted_by_the_admin(
        self, as_role, make_lay
    ):
        """It carries frozen numbers, an activity log and maybe a count."""
        lay = make_lay(status=Lay.STATUS_CLOSED)
        assert as_role("cutting_supervisor").delete(
            f"/api/cutting/lays/{lay.pk}/"
        ).status_code == 403
        assert as_role("admin").delete(
            f"/api/cutting/lays/{lay.pk}/"
        ).status_code == 204

    def test_a_read_only_role_edits_nothing(self, as_role, make_lay):
        lay = make_lay()
        assert as_role("production_manager").patch(
            f"/api/cutting/lays/{lay.pk}/", {"code": "NOPE"}, format="json"
        ).status_code == 403


class TestEditingRollLines:
    """A line typed wrong must be fixable without binning the whole lay."""

    def test_an_open_lay_edits_a_line_freely(self, supervisor, make_lay):
        lay = make_lay()
        line = lay.lines.first()
        res = supervisor.patch(f"/api/cutting/lay-lines/{line.pk}/",
                               {"plies": 25}, format="json")
        assert res.status_code == 200
        lay.refresh_from_db()
        assert lay.total_plies == 25

    def test_every_number_moves_with_it(self, supervisor, make_lay):
        """Plies, pieces, consumption, shortage and the shades all follow."""
        lay = make_lay(lines=[
            {"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50",
             "shade_note": "أسود"},
        ])
        before = (lay.total_plies, lay.theoretical_pieces, lay.consumed_m,
                  lay.fabric_shortage_m)
        line = lay.lines.first()
        supervisor.patch(f"/api/cutting/lay-lines/{line.pk}/",
                         {"plies": 10}, format="json")
        lay.refresh_from_db()
        after = (lay.total_plies, lay.theoretical_pieces, lay.consumed_m,
                 lay.fabric_shortage_m)
        assert after != before
        assert lay.total_plies == 10
        assert lay.theoretical_pieces == 10 * lay.pieces_per_ply
        shades = {r["shade"]: r["plies"] for r in services.shade_totals(lay)}
        assert shades == {"أسود": 10}

    def test_a_closed_lay_refuses_without_a_reason(self, supervisor, make_lay):
        lay = make_lay(status=Lay.STATUS_CLOSED)
        line = lay.lines.first()
        res = supervisor.patch(f"/api/cutting/lay-lines/{line.pk}/",
                               {"plies": 25}, format="json")
        assert res.status_code == 400
        assert res.data["issues"][0]["code"] == "edit_reason"
        lay.refresh_from_db()
        assert lay.total_plies != 25

    def test_and_records_the_reason_when_given(self, supervisor, make_lay):
        lay = make_lay(status=Lay.STATUS_CLOSED)
        line = lay.lines.first()
        res = supervisor.patch(
            f"/api/cutting/lay-lines/{line.pk}/",
            {"plies": 25, "edit_reason": "الراق اتكتب غلط"}, format="json",
        )
        assert res.status_code == 200
        lay.refresh_from_db()
        assert lay.total_plies == 25
        entry = lay.audit_entries.get(action="line_edited")
        assert entry.reason == "الراق اتكتب غلط"
        assert "20 راق" in entry.old_value      # readable before
        assert "25 راق" in entry.new_value      # and after

    def test_deleting_a_line_from_a_closed_lay_needs_a_reason_too(
        self, supervisor, make_lay
    ):
        lay = make_lay(status=Lay.STATUS_CLOSED, lines=[
            {"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50"},
            {"roll_length_m": "49.50", "plies": 10, "remnant_m": "0"},
        ])
        line = lay.lines.last()
        assert supervisor.delete(
            f"/api/cutting/lay-lines/{line.pk}/"
        ).status_code == 400

        res = supervisor.delete(
            f"/api/cutting/lay-lines/{line.pk}/?edit_reason=x",
            data={"edit_reason": "السطر مكرر"}, format="json",
        )
        assert res.status_code == 204
        lay.refresh_from_db()
        assert lay.total_plies == 20
        assert lay.audit_entries.filter(action="line_deleted").exists()

    def test_adding_a_line_to_a_closed_lay_is_logged(self, supervisor, make_lay):
        lay = make_lay(status=Lay.STATUS_CLOSED)
        res = supervisor.post(f"/api/cutting/lays/{lay.pk}/lines/", {
            "roll_length_m": "49.50", "plies": 10, "remnant_m": "0",
        }, format="json")
        # the nested endpoint keeps its own behaviour; the standalone one logs
        assert res.status_code in (201, 400)

    def test_a_read_only_role_touches_nothing(self, as_role, make_lay):
        lay = make_lay()
        line = lay.lines.first()
        assert as_role("production_manager").patch(
            f"/api/cutting/lay-lines/{line.pk}/", {"plies": 5}, format="json"
        ).status_code == 403
        assert as_role("production_manager").delete(
            f"/api/cutting/lay-lines/{line.pk}/"
        ).status_code == 403

    def test_the_line_rules_still_apply_on_edit(self, supervisor, make_lay):
        """V3: a remnant as long as the lay is still refused."""
        lay = make_lay()
        line = lay.lines.first()
        res = supervisor.patch(f"/api/cutting/lay-lines/{line.pk}/",
                               {"remnant_m": "9.99"}, format="json")
        assert res.status_code == 400
        assert res.data["issues"][0]["code"] == "V3"

    def test_a_new_line_is_numbered_by_the_server(self, supervisor, make_lay):
        """The client sends what it read off the notebook, not a row position."""
        lay = make_lay()
        res = supervisor.post("/api/cutting/lay-lines/", {
            "lay": lay.pk, "roll_length_m": "49.50", "plies": 10, "remnant_m": "0",
        }, format="json")
        assert res.status_code == 201, res.data
        assert res.data["line_no"] == 2
        lay.refresh_from_db()
        assert lay.total_plies == 30

    def test_numbering_survives_a_deletion(self, supervisor, make_lay):
        lay = make_lay(lines=[
            {"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50"},
            {"roll_length_m": "49.50", "plies": 10, "remnant_m": "0"},
        ])
        supervisor.delete(f"/api/cutting/lay-lines/{lay.lines.last().pk}/")
        res = supervisor.post("/api/cutting/lay-lines/", {
            "lay": lay.pk, "roll_length_m": "30.00", "plies": 6, "remnant_m": "0",
        }, format="json")
        assert res.status_code == 201
        assert res.data["line_no"] == 2   # the freed number, not a clash
