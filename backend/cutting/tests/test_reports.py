"""Cutting reports (SRS section 9) and their exports."""
import datetime
from decimal import Decimal

import pytest

from cutting import reports, services
from cutting.models import Lay
from cutting.tests.conftest import TODAY

pytestmark = pytest.mark.django_db
DAY = datetime.timedelta(days=1)


@pytest.fixture
def spread(make_lay, user, punch, leader):
    """One clean counted lay, one with a shortage, one backfilled."""
    clean = make_lay(status=Lay.STATUS_CLOSED)
    short = make_lay(status=Lay.STATUS_CLOSED, start_date=TODAY + DAY,
                     lines=[{"roll_length_m": "101.00", "plies": 20, "remnant_m": "0.50",
                             "article": "MEGAN", "lot_no": "L9"}])
    old = make_lay(is_backfill=True, status=Lay.STATUS_CLOSED,
                   start_date=TODAY - 40 * DAY, end_date=TODAY - 40 * DAY)
    services.record_output(clean, user, actual_pieces=118)
    services.record_output(short, user, actual_pieces=100)
    services.record_output(old, user, actual_pieces=100)
    services.recalculate(short)
    return {"clean": clean, "short": short, "old": old}


class TestMetrage:
    def test_it_groups_by_model(self, spread):
        report = reports.metrage_by_model()
        assert report["title"] == "الميتراج لكل موديل"
        assert len(report["rows"]) == 1  # all three share one model
        row = report["rows"][0]
        assert row["name"] == "كارل رجالي"
        assert row["category"] == "رجالي"
        assert row["lays"] == 2  # the backfilled one is excluded

    def test_backfilled_lays_are_excluded_unless_asked_for(self, spread):
        assert reports.metrage_by_model()["rows"][0]["lays"] == 2
        assert reports.metrage_by_model(include_backfill=True)["rows"][0]["lays"] == 3

    def test_it_honours_the_period_by_intersection(self, spread):
        only_first = reports.metrage_by_model(start=TODAY, end=TODAY)
        assert only_first["rows"][0]["lays"] == 1


class TestShortage:
    def test_only_lays_over_tolerance_appear(self, spread):
        report = reports.shortage_report()
        codes = [r["code"] for r in report["rows"]]
        assert codes == [spread["short"].code]

    def test_it_carries_the_article_and_lot(self, spread):
        row = reports.shortage_report()["rows"][0]
        assert row["articles"] == "MEGAN"
        assert row["lots"] == "L9"

    def test_it_totals_by_lot_so_a_bad_lot_shows_up(self, spread):
        report = reports.shortage_report()
        assert report["by_lot"][0]["lot"] == "L9"
        assert report["by_lot"][0]["lays"] == 1
        assert report["total_shortage"] > 0


class TestProductivity:
    def test_pieces_per_hour_from_the_device(self, spread, punch, leader):
        punch(leader.employee_code, TODAY, 8)
        punch(leader.employee_code, TODAY, 18)
        report = reports.productivity_report(start=TODAY, end=TODAY)
        row = report["rows"][0]
        assert row["hours"] == 10.0
        assert row["pieces_per_hour"] == 11.8  # 118 / 10
        assert row["reliable"] is True

    def test_a_single_punch_day_leaves_the_denominator(self, spread, punch, leader):
        punch(leader.employee_code, TODAY, 8)  # in only
        report = reports.productivity_report(start=TODAY, end=TODAY)
        row = report["rows"][0]
        assert row["hours"] == 0.0
        assert row["pieces_per_hour"] is None
        assert row["reliable"] is False

    def test_the_coverage_is_always_stated(self, spread, punch, leader):
        punch(leader.employee_code, TODAY, 8)
        punch(leader.employee_code, TODAY, 18)
        row = reports.productivity_report(start=TODAY, end=TODAY)["rows"][0]
        assert "من" in row["coverage"] and "يوم" in row["coverage"]

    def test_uncounted_lays_are_left_out(self, make_lay, punch, leader):
        make_lay()  # open, never counted
        assert reports.productivity_report()["rows"] == []


class TestRemnants:
    def test_it_splits_waste_from_usable(self, make_lay, user):
        lay = make_lay(lines=[
            {"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50",
             "article": "MEGAN"},
            {"roll_length_m": "50.45", "plies": 10, "remnant_m": "1.00",
             "article": "MEGAN"},
        ])
        services.sync_remnant_logs(lay)
        report = reports.remnant_report()
        assert report["total_waste_m"] == Decimal("0.50")
        assert report["total_usable_m"] == Decimal("1.00")


class TestDailyBank:
    def test_it_groups_by_close_date_and_bank(self, spread):
        report = reports.daily_bank_report()
        assert len(report["rows"]) == 2  # two days, one bank
        assert all(r["bank"] for r in report["rows"])

    def test_a_two_day_lay_counts_on_the_day_it_closed_only(self, make_lay):
        make_lay(start_date=TODAY, end_date=TODAY + DAY)
        rows = reports.daily_bank_report()["rows"]
        assert len(rows) == 1
        assert rows[0]["date"] == (TODAY + DAY).isoformat()


class TestEntryQuality:
    def test_it_counts_the_things_that_show_sloppy_recording(self, make_lay, spread):
        make_lay(entry_mode=Lay.MODE_QUICK)
        make_lay(with_sheet=False)
        report = reports.entry_quality_report()
        by_metric = {r["metric"]: r["count"] for r in report["rows"]}
        assert by_metric["إدخال سريع"] == 1
        assert by_metric["من غير صورة دفتر"] == 1
        assert by_metric["فيها عجز"] == 1
        assert by_metric["إجمالي الفرشات"] == 4

    def test_percentages_are_of_the_total(self, make_lay):
        make_lay()
        make_lay(entry_mode=Lay.MODE_QUICK)
        rows = {r["metric"]: r["pct"] for r in reports.entry_quality_report()["rows"]}
        assert rows["إدخال سريع"] == 50.0


class TestExports:
    @pytest.mark.parametrize("name", sorted(reports.REPORTS))
    def test_every_report_renders_to_excel(self, name, spread):
        report = reports.REPORTS[name]()
        buf = reports.report_xlsx(report)
        head = buf.read(4)
        assert head[:2] == b"PK"  # xlsx is a zip

    @pytest.mark.parametrize("name", sorted(reports.REPORTS))
    def test_every_report_renders_to_pdf(self, name, spread):
        report = reports.REPORTS[name]()
        buf = reports.report_pdf(report)
        assert buf.read(5) == b"%PDF-"

    def test_an_empty_report_still_renders(self):
        report = reports.metrage_by_model()
        assert report["rows"] == []
        assert reports.report_xlsx(report).read(2) == b"PK"
        assert reports.report_pdf(report).read(5) == b"%PDF-"


class TestReportApi:
    def test_json_by_default(self, supervisor, spread):
        res = supervisor.get("/api/cutting/reports/metrage/")
        assert res.status_code == 200
        assert res.data["title"] == "الميتراج لكل موديل"

    def test_the_param_is_export_not_format(self, supervisor, spread):
        """DRF owns `format`; using it would 404 before the view ran."""
        assert supervisor.get(
            "/api/cutting/reports/metrage/?format=xlsx"
        ).status_code == 404

    def test_excel_and_pdf(self, supervisor, spread):
        xlsx = supervisor.get("/api/cutting/reports/shortage/?export=xlsx")
        assert xlsx.status_code == 200
        assert "spreadsheet" in xlsx["Content-Type"]
        pdf = supervisor.get("/api/cutting/reports/shortage/?export=pdf")
        assert pdf["Content-Type"] == "application/pdf"

    def test_an_unknown_report_is_a_404_that_lists_the_real_ones(self, supervisor):
        res = supervisor.get("/api/cutting/reports/nope/")
        assert res.status_code == 404
        assert "metrage" in res.data["available"]

    def test_a_read_only_role_may_read_reports(self, as_role, spread):
        assert as_role("production_manager").get(
            "/api/cutting/reports/metrage/"
        ).status_code == 200

    def test_the_lay_export_follows_the_applied_filters(self, supervisor, spread):
        everything = supervisor.get("/api/cutting/lays/export/?export=xlsx")
        assert everything.status_code == 200
        filtered = supervisor.get(
            "/api/cutting/lays/export/?export=xlsx&has_shortage=true"
        )
        assert filtered.status_code == 200
        assert len(filtered.content) < len(everything.content)

    def test_the_export_is_downloadable(self, supervisor, spread):
        res = supervisor.get("/api/cutting/lays/export/?export=pdf")
        assert "attachment" in res["Content-Disposition"]
        assert res["Content-Disposition"].endswith('.pdf"')
