"""Shorthand search parsing, and that the tokens really filter (SRS 7.1.1)."""
import datetime

import pytest

from cutting import services
from cutting.models import Lay
from cutting.search import parse_query
from cutting.tests.conftest import TODAY

pytestmark = pytest.mark.django_db
DAY = datetime.timedelta(days=1)


class TestParseQuery:
    def test_the_srs_example(self):
        assert parse_query("ميتراج>1.2") == ("", {"real_metrage_min": "1.2"})

    def test_less_than(self):
        assert parse_query("ميتراج<1.2") == ("", {"real_metrage_max": "1.2"})

    def test_colon_means_exactly(self):
        free, params = parse_query("راق:125")
        assert params == {"total_plies_min": "125", "total_plies_max": "125"}

    @pytest.mark.parametrize("text,expected", [
        ("عجز:نعم", {"has_shortage": "true"}),
        ("عجز:لا", {"has_shortage": "false"}),
        ("مقاس:32", {"size": "32"}),
        ("لون:أسود", {"shade_note": "أسود"}),
        ("بنك:2", {"bank_code": "2"}),
        ("حالة:مستنية-ترقيم", {"awaiting_count": "true"}),
        ("حالة:مقفولة", {"status": "closed"}),
    ])
    def test_the_documented_tokens(self, text, expected):
        assert parse_query(text) == ("", expected)

    def test_tokens_and_free_words_together(self):
        free, params = parse_query("عجز:نعم مقاس:32 كارل")
        assert free == "كارل"
        assert params == {"has_shortage": "true", "size": "32"}

    def test_arabic_indic_digits_in_a_token(self):
        assert parse_query("ميتراج>١.٢") == ("", {"real_metrage_min": "1.2"})

    def test_a_negative_threshold(self):
        assert parse_query("انحراف<-2") == ("", {"deviation_max": "-2"})

    def test_plain_words_stay_plain(self):
        assert parse_query("كارل رجالي") == ("كارل رجالي", {})

    def test_an_unknown_token_is_left_as_text_not_dropped(self):
        """It might be a lot number with a colon in it — still search for it."""
        free, params = parse_query("حاجة:مش-معروفة")
        assert params == {}
        assert "مش-معروفة" in free

    def test_empty(self):
        assert parse_query("") == ("", {})
        assert parse_query(None) == ("", {})


class TestSearchEndpoint:
    @pytest.fixture
    def data(self, make_lay, user):
        a = make_lay(sizes_raw="30 32", status=Lay.STATUS_CLOSED,
                     lines=[{"roll_length_m": "99.00", "plies": 20, "remnant_m": "0",
                             "article": "MEGAN", "lot_no": "L1", "shade_note": "أسود"}])
        b = make_lay(sizes_raw="34 36", start_date=TODAY + 5 * DAY,
                     lines=[{"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50",
                             "article": "BLACK MIMAS", "shade_note": "كحلي"}])
        services.record_output(a, user, actual_pieces=38)
        return {"a": a, "b": b}

    def ids(self, res):
        return {r["id"] for r in res.data["results"]}

    def test_a_shorthand_threshold_filters(self, supervisor, data):
        res = supervisor.get("/api/cutting/lays/search/?q=" + "ميتراج>1")
        assert res.status_code == 200
        assert self.ids(res) == {data["a"].pk}

    def test_the_same_threshold_the_other_way_excludes_it(self, supervisor, data):
        res = supervisor.get("/api/cutting/lays/search/?q=" + "ميتراج<1")
        assert self.ids(res) == set()

    def test_a_free_word_searches_the_roll_lines(self, supervisor, data):
        """The shade is the only line field with an input, so it is the only
        one searched."""
        res = supervisor.get("/api/cutting/lays/search/?q=" + "كحلي")
        assert self.ids(res) == {data["b"].pk}

    def test_the_dropped_tokens_are_treated_as_plain_words(self):
        """خامة: and لوط: are gone; whatever follows must not vanish."""
        free, params = parse_query("خامة:MEGAN")
        assert params == {}
        assert "MEGAN" in free

    def test_a_token_and_a_word_narrow_together(self, supervisor, data):
        res = supervisor.get("/api/cutting/lays/search/?q=" + "لون:كحلي")
        assert self.ids(res) == {data["b"].pk}

    def test_the_response_explains_what_it_understood(self, supervisor, data):
        res = supervisor.get("/api/cutting/lays/search/?q=" + "عجز:نعم كارل")
        assert res.data["parsed"]["free_text"] == "كارل"
        assert res.data["parsed"]["filters"][0]["label"] == "فيها عجز"

    def test_it_still_paginates(self, supervisor, data):
        res = supervisor.get("/api/cutting/lays/search/?q=")
        assert res.data["count"] == 2


class TestSummary:
    def test_the_cards_add_up_over_the_current_filters(self, make_lay, supervisor, user):
        a = make_lay(status=Lay.STATUS_CLOSED)
        make_lay(start_date=TODAY + 5 * DAY,
                 lines=[{"roll_length_m": "101.00", "plies": 20, "remnant_m": "0.50"}])
        services.record_output(a, user, actual_pieces=118)

        res = supervisor.get("/api/cutting/lays/summary/")
        assert res.status_code == 200
        assert res.data["lays"] == 2
        assert res.data["theoretical_pieces"] == 240
        assert res.data["actual_pieces"] == 118
        assert res.data["with_shortage"] == 1
        assert res.data["awaiting_count"] == 0

    def test_it_follows_the_filters(self, make_lay, supervisor):
        make_lay()
        make_lay(start_date=TODAY + 20 * DAY)
        res = supervisor.get(f"/api/cutting/lays/summary/?date_from={TODAY.isoformat()}"
                             f"&date_to={TODAY.isoformat()}")
        assert res.data["lays"] == 1


class TestSavedFilters:
    def test_save_and_list(self, supervisor):
        res = supervisor.post("/api/cutting/saved-filters/", {
            "name": "فرشات كارل فيها عجز", "query": "كارل عجز:نعم",
        }, format="json")
        assert res.status_code == 201
        assert supervisor.get("/api/cutting/saved-filters/").data["count"] == 1

    def test_one_persons_filter_is_not_anothers(self, api, make_user):
        api.force_authenticate(make_user("cutting_supervisor"))
        api.post("/api/cutting/saved-filters/", {"name": "بتاعي", "query": "x"},
                 format="json")
        api.force_authenticate(make_user("admin"))
        assert api.get("/api/cutting/saved-filters/").data["count"] == 0

    def test_a_shared_filter_is_visible_to_everyone(self, api, make_user):
        api.force_authenticate(make_user("cutting_supervisor"))
        api.post("/api/cutting/saved-filters/",
                 {"name": "للكل", "query": "x", "is_shared": True}, format="json")
        api.force_authenticate(make_user("production_manager"))
        assert api.get("/api/cutting/saved-filters/").data["count"] == 1

    def test_but_only_its_owner_may_delete_it(self, api, make_user):
        api.force_authenticate(make_user("cutting_supervisor"))
        created = api.post("/api/cutting/saved-filters/",
                           {"name": "للكل", "query": "x", "is_shared": True},
                           format="json").data
        api.force_authenticate(make_user("admin"))
        assert api.delete(f"/api/cutting/saved-filters/{created['id']}/").status_code == 403
