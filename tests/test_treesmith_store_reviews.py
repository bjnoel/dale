"""Store ratings and reviews in the TreeSmith digest (2026-09-21).

Benedict asked for the review count on each store and the text of any new
review. What is pinned:

1. Both stores' response shapes parse (Apple's `entry` is a dict for one
   review and a list for several; Play wraps JSON in a `)]}'` envelope).
2. A review is "new" once. The second run over the same feed reports none.
3. Play hiding its rating count renders as "not shown", never as 0.
4. Photos added reach the headline as a row distinct from plants added.

These never touch the network.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "tools", "autonomous"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import store_reviews as sr  # noqa: E402
import treesmith_analytics as ta  # noqa: E402
from test_treesmith_new_events import base_metrics  # noqa: E402


def _ios_entry(rid, title, body, stars=5):
    return {"id": {"label": rid}, "title": {"label": title},
            "content": {"label": body}, "im:rating": {"label": str(stars)},
            "im:version": {"label": "1.0.11"},
            "updated": {"label": "2026-09-13T01:49:22-07:00"},
            "author": {"name": {"label": "Larrykan"}}}


PLAY_RAW = (")]}'\n\n" + json.dumps([
    ["wrb.fr", "UsvDTd", json.dumps([[[
        "1a0525e9", ["K Ed", []], 5, None,
        "Excellent APP. Can even set reminder for when to fertilise next!",
        [1787212998, 217000000], 0, None, None, None, "1.0.10"]], None]),
     None, None, None, "generic"],
    ["di", 28]]))


class TestParsers(unittest.TestCase):
    def test_ios_single_entry_is_a_dict_not_a_list(self):
        feed = {"feed": {"entry": _ios_entry("1", "Great", "Body")}}
        out = sr.parse_ios_feed(feed)
        self.assertEqual([r["id"] for r in out], ["ios:1"])
        self.assertEqual(out[0]["date"], "2026-09-13")
        self.assertEqual(out[0]["stars"], 5)

    def test_ios_no_entries(self):
        self.assertEqual(sr.parse_ios_feed({"feed": {}}), [])

    def test_play_envelope(self):
        out = sr.parse_play_reviews(PLAY_RAW)
        self.assertEqual(len(out), 1)
        r = out[0]
        self.assertEqual(r["id"], "android:1a0525e9")
        self.assertEqual(r["author"], "K Ed")
        self.assertEqual(r["date"], "2026-08-20")
        self.assertEqual(r["version"], "1.0.10")
        self.assertIn("fertilise", r["text"])

    def test_play_page_without_rating_markers_is_none_not_zero(self):
        self.assertEqual(sr.parse_play_page("<html>no ratings</html>"),
                         (None, None))
        self.assertEqual(
            sr.parse_play_page('x "ratingValue":"4.5", "ratingCount":"12"}'),
            (12, 4.5))


class TestNewOnlyOnce(unittest.TestCase):
    def _fetchers(self):
        return {"ios": [lambda: {
            "store": "ios", "country": "AU", "rating_count": 1,
            "average": 5, "reviews": sr.parse_ios_feed(
                {"feed": {"entry": _ios_entry("14544249562", "Fantastic",
                                              "Easy to use")}})}]}

    def test_second_run_reports_nothing_new(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.json")
            first = sr.check(fetchers=self._fetchers(), path=path)
            self.assertEqual(len(first["new"]), 1)
            self.assertTrue(first["first_run"])
            second = sr.check(fetchers=self._fetchers(), path=path)
            self.assertEqual(second["new"], [])
            self.assertFalse(second["first_run"])
            self.assertEqual(second["stores"][0]["written"], 1)

    def test_a_failed_store_is_reported_and_its_reviews_stay_unseen(self):
        def boom():
            raise sr.Unavailable("Play returned 429")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.json")
            res = sr.check(fetchers={"android": [boom]}, path=path)
            self.assertEqual(res["stores"], [])
            self.assertIn("429", res["unreadable"][0]["error"])
            self.assertFalse(os.path.exists(path))


class TestDigestRender(unittest.TestCase):
    def _reviews(self, new):
        return {"ok": True, "data": {
            "stores": [
                {"store": "ios", "country": "AU", "rating_count": 1,
                 "average": 5, "written": 1},
                {"store": "android", "country": "global",
                 "rating_count": None, "average": None, "written": 1}],
            "new": new, "unreadable": [], "first_run": bool(new)}}

    def test_new_review_text_reaches_the_mail(self):
        m = base_metrics()
        m["store_reviews"] = self._reviews([{
            "store": "android", "country": "global", "id": "android:1",
            "author": "K Ed", "stars": 5, "title": "",
            "text": "Excellent APP. <b>Can even set reminder</b>",
            "version": "1.0.10", "date": "2026-08-20"}])
        text, html = ta.render(m)
        self.assertIn("Store ratings and reviews", text)
        self.assertIn("Play ***** 2026-08-20 by K Ed, v1.0.10", text)
        self.assertIn("Excellent APP.", text)
        self.assertIn("&lt;b&gt;", html)  # review text is escaped, not markup
        # Headline row present and honest about Play's hidden count.
        self.assertIn("Store reviews", text[:text.index("Store ratings and")])
        self.assertIn("Play not shown (1 written)", text)
        self.assertNotIn("Play 0", text)

    def test_quiet_week_says_so(self):
        m = base_metrics()
        m["store_reviews"] = self._reviews([])
        text, _ = ta.render(m)
        self.assertIn("none this week", text)
        self.assertIn("0 new this week", text)

    def test_failed_metric_drops_the_headline_row(self):
        m = base_metrics()
        m["store_reviews"] = {"ok": False, "error": "iTunes 503"}
        text, _ = ta.render(m)
        self.assertNotIn("Store reviews ", text[:text.index("Store ratings")])
        self.assertIn("ERROR iTunes 503", text)

    def test_photos_added_is_its_own_headline_row(self):
        m = base_metrics()
        m["feature_usage"] = {"ok": True, "data": {
            "by_event": {
                "photo_added": {"all_time": 566, "n_7d": 100, "people_7d": 9},
                "activity_logged": {"all_time": 3, "n_7d": 0, "people_7d": 0}},
            "grafts": [], "activities": [], "bulk": [], "photos": []}}
        text, _ = ta.render(m)
        self.assertIn("Photos added (7d / all time)", text)
        self.assertIn("100 / 566", text)
        self.assertIn("9 people this week", text)


if __name__ == "__main__":
    unittest.main()
