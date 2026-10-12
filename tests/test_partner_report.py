"""
Tests for tools/scrapers/build_partner_report.py -- the monthly nursery report.

The joins are what the report sells, so they are what is pinned: a click is
judged against stock ON ITS DAY (the 2026-08-31 sample used one snapshot and
counted a mid-month restock as a lost sale), Queensland-only lines are set
aside rather than called lost, and watchers in a state the nursery cannot ship
to are not quoted as demand.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

import build_partner_report as bpr  # noqa: E402
from stocklib.templates import render  # noqa: E402

RC = "rosscreektropicals.com.au/products/"


class NormUrl(unittest.TestCase):
    def test_click_and_availability_keys_meet(self):
        click = "https://www.rosscreektropicals.com.au/products/blueberry-ob1?utm_source=treestock&utm_medium=referral"
        key = "https://www.rosscreektropicals.com.au/products/blueberry-ob1|sku:OB1 90mm"
        self.assertEqual(bpr.norm_url(click), RC + "blueberry-ob1")
        self.assertEqual(bpr.norm_url(key), RC + "blueberry-ob1")


class AvailabilityByUrl(unittest.TestCase):
    def test_any_variant_available_means_available(self):
        avail = {"products": {
            "https://www.rosscreektropicals.com.au/products/fig|sku:a": {
                "title": "Fig", "days": {"2026-09-01": {"a": False}}},
            "https://www.rosscreektropicals.com.au/products/fig|sku:b": {
                "title": "Fig", "days": {"2026-09-01": {"a": True}}},
        }}
        self.assertTrue(bpr.availability_by_url(avail)[RC + "fig"]["days"]["2026-09-01"])


class ClassifyClicks(unittest.TestCase):
    AVAIL = {
        RC + "mango": {"title": "Mango Coconut Cream 2l",
                       "days": {"2026-09-01": False, "2026-09-02": True}},
        RC + "dekupon": {"title": "Mandarin- Shiranui Dekupon 2.4l (Qld only)",
                         "days": {"2026-09-01": True}},
    }

    def test_click_is_judged_on_its_own_day(self):
        # Sold out on the 1st, restocked on the 2nd. A single end-of-month
        # snapshot would call both clicks lost or both fine.
        res = bpr.classify_clicks(
            {"2026-09-01": {RC + "mango": 3}, "2026-09-02": {RC + "mango": 2}},
            self.AVAIL, {})
        self.assertEqual(res["sold_out"], 3)
        self.assertEqual(res["in_stock"], 2)
        self.assertEqual(res["lost_by_url"][RC + "mango"], 3)

    def test_queensland_only_lines_are_not_lost_sales(self):
        res = bpr.classify_clicks({"2026-09-01": {RC + "dekupon": 4}}, self.AVAIL, {})
        self.assertEqual(res["restricted"], 4)
        self.assertEqual(res["sold_out"], 0)

    def test_bare_root_potted_is_judged_on_stock(self):
        # Ross Creek ships "Bare Root Potted" nationally; the August sample
        # wrongly set these aside as restricted.
        avail = {RC + "cherry": {"title": "Cherry Royal Crimson (Bare Root Potted)",
                                 "days": {"2026-09-01": False}}}
        res = bpr.classify_clicks({"2026-09-01": {RC + "cherry": 1}}, avail, {})
        self.assertEqual((res["restricted"], res["sold_out"]), (0, 1))

    def test_homepage_and_missing_history(self):
        res = bpr.classify_clicks(
            {"2026-09-03": {"rosscreektropicals.com.au": 5, RC + "mango": 1}},
            self.AVAIL, {})
        self.assertEqual(res["other"], 5)
        self.assertEqual(res["unknown"], 1, "no record that day is unknown, never guessed")


class SoldOutBaseline(unittest.TestCase):
    def test_mean_daily_share(self):
        avail = {"a": {"days": {"d1": False, "d2": False}},
                 "b": {"days": {"d1": True, "d2": False}}}
        self.assertAlmostEqual(bpr.catalogue_sold_out_share(avail, ["d1", "d2"]), 0.75)


class ServableWatchers(unittest.TestCase):
    def test_known_unshippable_state_is_dropped_unknown_is_kept(self):
        got = bpr.servable_watchers(
            [("wa@x", "WA"), ("nsw@x", "NSW"), ("all@x", "ALL"), ("anon@x", None)],
            ["NSW", "VIC", "QLD", "SA", "ACT"])
        self.assertEqual(got, ["nsw@x", "all@x", "anon@x"])


class RegionSummary(unittest.TestCase):
    def test_unshippable_and_restricted_split(self):
        clicks = {"NSW": {RC + "mango": 5}, "WA": {RC + "mango": 3},
                  "QLD": {RC + "dekupon": 2}, "VIC": {RC + "dekupon": 4}}
        s = bpr.region_summary(clicks, 20, ["NSW", "VIC", "QLD", "SA", "ACT"],
                               {RC + "dekupon"})
        self.assertEqual(s["unshippable"], 3)
        self.assertEqual(s["elsewhere"], 6)
        self.assertEqual((s["restricted_home"], s["restricted_away"]), (2, 4))
        self.assertEqual(s["rows"][0]["state"], "NSW")


class ClassifyVariety(unittest.TestCase):
    def test_kinds(self):
        yes, no = {"available": True}, {"available": False}
        self.assertEqual(bpr.classify_variety([yes], [no, no]), "only_you")
        self.assertEqual(bpr.classify_variety([no], [no]), "nobody")
        self.assertEqual(bpr.classify_variety([no], []), "nobody")
        self.assertEqual(bpr.classify_variety([yes], [yes]), "you_and_others")
        self.assertEqual(bpr.classify_variety([no], [yes]), "others_only")


class TemplateRenders(unittest.TestCase):
    def test_renders_and_escapes(self):
        row = {"title": "Fig & Olive <b>", "url": "https://x", "price": 49.9,
               "clicks": 3, "now": False, "days_out": 30, "home": 1, "away": 2}
        w = {"title": "Blueberry - OB1", "waiting": 6, "mine_prices": [49.9], "mine_in_prices": [49.9],
             "mine_restricted": False, "other_names": ["Ladybird Nursery"]}
        html = render(
            "partner_report.html.j2",
            name="Ross Creek Tropicals", contact="Tom", domain="rosscreektropicals.com.au",
            month_label="September 2026", month_name="September", generated="12 October 2026",
            this={"clicks": 460, "label": "September"}, prev={"clicks": 215, "label": "August"},
            monthly=[{"label": "August", "clicks": 215}, {"label": "September", "clicks": 460}],
            max_monthly=460, share=0.118, rank=2, n_nurseries=27, tagged_share=1.0,
            regions={"rows": [{"state": "WA", "clicks": 10, "ships": False}],
                     "elsewhere": 0, "unshippable": 10, "restricted_home": 1, "restricted_away": 2},
            no_ship=["WA", "TAS", "NT"],
            cls={"product": 431, "sold_out": 41, "restricted": 3},
            lost_products=1, baseline=0.65, n_days=30,
            top_clicked=[row], lost=[row], restricted=[row],
            n_watchers=208, n_watching_yours=93, n_varieties_yours=74,
            top_watched={"title": "Blueberry - OB1", "n": 6, "yours": True},
            only_you=[w], nobody=[w], n_state_known=13, n_dropped=1)
        self.assertIn("Fig &amp; Olive &lt;b&gt;", html)
        self.assertIn("+114%", html)
        self.assertIn('content="noindex, nofollow"', html)
        self.assertNotIn("outbound-links", html,
                         "the report's own links must not count as referral clicks")
        self.assertNotIn("—", html, "no em dashes in copy")


if __name__ == "__main__":
    unittest.main()
