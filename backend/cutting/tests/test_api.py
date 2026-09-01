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
        ("admin", 200), ("cutting_supervisor", 200),
        ("production_manager", 403), ("cutting", 403),
    ])
    def test_only_the_supervisor_and_admin_may_write(
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

    @pytest.mark.parametrize("role,expected", [
        ("admin", 201), ("cutting_supervisor", 403), ("production_manager", 403),
    ])
    def test_the_catalogues_are_admin_only(self, as_role, role, expected):
        res = as_role(role).post("/api/cutting/banks/",
                                 {"code": f"B{role[:3]}", "name": "بنك"}, format="json")
        assert res.status_code == expected

    def test_the_supervisor_can_still_read_the_catalogues(self, as_role, bank):
        assert as_role("cutting_supervisor").get("/api/cutting/banks/").status_code == 200

    def test_the_supervisor_may_add_a_model_from_the_new_lay_screen(self, as_role):
        """SRS 7.2 quick-add: he is holding the model in his hand right now."""
        res = as_role("cutting_supervisor").post(
            "/api/cutting/models/", {"code": "9001", "name": "موديل جديد"}, format="json"
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
            "lay_width_cm": "167", "lay_length_m": "4.95", "sizes_raw": "()",
        }, format="json")
        assert res.status_code == 400
        assert issue_codes(res) == ["sizes_unreadable"]
        assert "مقاسات" in res.data["issues"][0]["message"]

    def test_an_end_date_before_the_start_is_refused_by_the_model_rule(
        self, supervisor, bank, garment_model, leader
    ):
        res = supervisor.post("/api/cutting/lays/", {
            "start_date": TODAY.isoformat(),
            "end_date": (TODAY - DAY).isoformat(),
            "bank": bank.pk, "garment_model": garment_model.pk,
            "team_leader": leader.pk, "lay_width_cm": "167",
            "lay_length_m": "4.95", "sizes_raw": "32",
        }, format="json")
        assert res.status_code == 400
        assert "date_order" in issue_codes(res)


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
        res = supervisor.get("/api/cutting/lays/?article=MEGAN,BLACK MIMAS")
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
        res = supervisor.get("/api/cutting/lays/?search=MEGAN")
        assert self.ids(res) == {spread["a"].pk}

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


class TestFitCatalogue:
    """القَصّات as a catalogue rather than free text (user request, SRS 4.4)."""

    def test_admin_creates_a_fit(self, as_role):
        res = as_role("admin").post("/api/cutting/fits/", {"name": "بوت كت"}, format="json")
        assert res.status_code == 201

    def test_the_supervisor_may_add_and_correct_but_not_delete(self, as_role, fit):
        client = as_role("cutting_supervisor")
        assert client.post("/api/cutting/fits/", {"name": "واسع"},
                           format="json").status_code == 201
        assert client.patch(f"/api/cutting/fits/{fit.pk}/", {"name": "سليم جدًا"},
                            format="json").status_code == 200
        assert client.delete(f"/api/cutting/fits/{fit.pk}/").status_code == 403

    def test_a_read_only_role_cannot_touch_it(self, as_role, fit):
        client = as_role("production_manager")
        assert client.get("/api/cutting/fits/").status_code == 200
        assert client.post("/api/cutting/fits/", {"name": "x"},
                           format="json").status_code == 403

    def test_the_name_is_unique(self, as_role, fit):
        res = as_role("admin").post("/api/cutting/fits/", {"name": fit.name}, format="json")
        assert res.status_code == 400

    def test_renaming_a_fit_renames_it_on_every_model(self, as_role, fit, garment_model):
        """The whole point of the catalogue."""
        as_role("admin").patch(f"/api/cutting/fits/{fit.pk}/", {"name": "سليم ٢"},
                               format="json")
        res = as_role("admin").get(f"/api/cutting/models/{garment_model.pk}/")
        assert res.data["fit_name"] == "سليم ٢"

    def test_a_fit_in_use_is_refused_in_arabic(self, as_role, fit, garment_model):
        """PROTECT on the FK — deleting it would orphan the models."""
        res = as_role("admin").delete(f"/api/cutting/fits/{fit.pk}/")
        assert res.status_code == 400
        assert res.data["issues"][0]["code"] == "in_use"

    def test_it_counts_how_many_models_use_it(self, as_role, fit, garment_model):
        res = as_role("admin").get("/api/cutting/fits/")
        assert res.data["results"][0]["model_count"] == 1

    def test_lays_can_be_filtered_by_fit_name(self, supervisor, make_lay):
        make_lay()
        assert supervisor.get("/api/cutting/lays/?fit=سليم").data["count"] == 1
        assert supervisor.get("/api/cutting/lays/?fit=واسع").data["count"] == 0

    def test_the_shorthand_token_still_works(self, supervisor, make_lay):
        make_lay()
        res = supervisor.get("/api/cutting/lays/search/?q=" + "قصة:سليم")
        assert res.data["count"] == 1


class TestModelCatalogue:
    def test_a_duplicate_code_is_refused(self, as_role, garment_model):
        res = as_role("admin").post(
            "/api/cutting/models/", {"code": garment_model.code, "name": "تاني"},
            format="json",
        )
        assert res.status_code == 400

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

    def test_an_unused_model_can_be_deleted(self, as_role):
        created = as_role("admin").post(
            "/api/cutting/models/", {"code": "9999", "name": "مؤقت"}, format="json"
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
