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
        self.assertEqual(s["seasonal"], 0)

    def test_seasonal_state_ships_but_is_flagged(self):
        # Daleys ships to WA only in windows. Still shippable (not counted
        # as lost), but the report must not say "Yes" as if any day will do.
        clicks = {"WA": {"d/x": 298}, "NSW": {"d/x": 203}}
        s = bpr.region_summary(clicks, 501, ["NSW", "WA"], set(), ["WA"])
        self.assertEqual(s["unshippable"], 0)
        self.assertEqual(s["seasonal"], 298)
        self.assertEqual([(r["state"], r["seasonal"]) for r in s["rows"]],
                         [("WA", True), ("NSW", False)])


class Recipient(unittest.TestCase):
    def test_defaults_follow_platform_and_partnership(self):
        self.assertEqual(bpr.recipient("ross-creek", "shopify")["offer"], "goaffpro")
        # Daleys' snapshot source is "feed": a custom site, so no GoAffPro.
        self.assertEqual(bpr.recipient("daleys", "feed")["offer"], "ask")
        # Already in AFFILIATES: nothing to ask for.
        self.assertEqual(bpr.recipient("primal-fruits", "ecwid")["offer"], "partner")

    def test_only_shopify_is_named_as_the_place_to_check(self):
        self.assertEqual(bpr.recipient("ross-creek", "shopify")["check_in"],
                         "your Shopify sessions")
        self.assertEqual(bpr.recipient("daleys", "feed")["check_in"], "your analytics")

    def test_goaffpro_is_refused_off_shopify(self):
        with self.assertRaises(ValueError):
            bpr.recipient("daleys", "feed", "goaffpro")
        self.assertEqual(bpr.recipient("ross-creek", "shopify", "ask")["offer"], "ask")


class ClassifyVariety(unittest.TestCase):
    def test_kinds(self):
        yes, no = {"available": True}, {"available": False}
        self.assertEqual(bpr.classify_variety([yes], [no, no]), "only_you")
        self.assertEqual(bpr.classify_variety([no], [no]), "nobody")
        self.assertEqual(bpr.classify_variety([no], []), "nobody")
        self.assertEqual(bpr.classify_variety([yes], [yes]), "you_and_others")
        self.assertEqual(bpr.classify_variety([no], [yes]), "others_only")


class WatchGrowth(unittest.TestCase):
    STAMPS = (["2026-06-03T01:00"] * 17 + ["2026-07-09T01:00"] * 30
              + ["2026-08-20T01:00"] * 45 + ["2026-09-04T00:32"] * 98
              + ["2026-10-14T09:27"] * 47)

    def test_bars_stop_at_the_report_month(self):
        from datetime import date
        g = bpr.watch_growth(self.STAMPS, "2026-09", today=date(2026, 10, 15))
        self.assertEqual([(r["label"], r["n"]) for r in g["rows"]],
                         [("June", 17), ("July", 30), ("August", 45), ("September", 98)])
        self.assertEqual(g["max"], 98)
        # October is a count with its day span, never a bar: 47 next to 98
        # would draw as a drop when it is on pace to match.
        self.assertEqual(g["after"], {"label": "October", "n": 47, "days": 15})

    def test_partial_month_line_dropped_once_it_is_over(self):
        from datetime import date
        g = bpr.watch_growth(self.STAMPS, "2026-09", today=date(2026, 11, 2))
        self.assertEqual(g["after"]["days"], 0)

    def test_december_rolls_into_january(self):
        g = bpr.watch_growth(["2027-01-05T00:00"], "2026-12")
        self.assertEqual((g["after"]["label"], g["after"]["n"]), ("January", 1))


class TemplateRenders(unittest.TestCase):
    def _render(self, recipient, regions=None):
        row = {"title": "Fig & Olive <b>", "url": "https://x", "price": 49.9,
               "clicks": 3, "now": False, "days_out": 30, "home": 1, "away": 2}
        w = {"title": "Blueberry - OB1", "waiting": 6, "mine_prices": [49.9], "mine_in_prices": [49.9],
             "mine_restricted": False, "other_names": ["Ladybird Nursery"]}
        return render(
            "partner_report.html.j2",
            recipient=recipient,
            name="Ross Creek Tropicals", contact="Tom", domain="rosscreektropicals.com.au",
            month_label="September 2026", month_name="September", generated="12 October 2026",
            this={"clicks": 460, "people": 321, "label": "September"},
            prev={"clicks": 215, "people": 168, "label": "August"},
            monthly=[{"label": "August", "clicks": 215, "people": 168},
                     {"label": "September", "clicks": 460, "people": 321}],
            max_monthly=321, share=0.118, rank=2, n_nurseries=27, tagged_share=1.0,
            regions=regions or {"rows": [{"state": "WA", "clicks": 10, "ships": False, "seasonal": False}],
                     "elsewhere": 0, "unshippable": 10, "seasonal": 0,
                     "restricted_home": 1, "restricted_away": 2},
            no_ship=["WA", "TAS", "NT"],
            cls={"product": 431, "sold_out": 41, "restricted": 3},
            lost_products=1, baseline=0.65, n_days=30,
            top_clicked=[row], lost=[row], restricted=[row],
            n_watchers=208, n_watching_yours=93, n_varieties_yours=74,
            top_watched={"title": "Blueberry - OB1", "n": 6, "yours": True},
            only_you=[w], nobody=[w], n_state_known=13, n_dropped=1,
            growth={"rows": [{"label": "August", "n": 45}, {"label": "September", "n": 98}],
                    "max": 98, "after": {"label": "October", "n": 47, "days": 15}})

    def test_renders_and_escapes(self):
        html = self._render(bpr.recipient("ross-creek", "shopify"))
        self.assertIn("Fig &amp; Olive &lt;b&gt;", html)
        # Headline and month-on-month are PEOPLE, which is what Shopify shows as
        # sessions. Ross Creek read 316 against a headline of 460 clicks and
        # took it as our data being wrong (2026-10-17).
        self.assertIn('<div class="v">321</div>', html)
        self.assertIn("460 clicks to rosscreektropicals.com.au", html)
        self.assertIn("+91%", html)
        self.assertIn("should show close to 321.", html)
        self.assertNotIn("close to the same 460", html)
        self.assertIn('content="noindex, nofollow"', html)
        self.assertNotIn("outbound-links", html,
                         "the report's own links must not count as referral clicks")
        self.assertNotIn("—", html, "no em dashes in copy")
        # Only states that actually sent clicks are named as unshippable.
        self.assertIn("came from WA</strong>", html)
        self.assertIn("WA, TAS or NT", html)
        # The fill is a span: without display:block its width is ignored and
        # every bar draws as an empty track (shipped that way 2026-10-12).
        self.assertIn(".bar .fill{display:block;", html)
        self.assertNotIn("Sources:", html)
        self.assertIn("width:45.9%", html, "alert bars scale to the busiest month")
        self.assertIn("October so far: 47 in the first 15 days.", html)
        self.assertIn("filtering your Shopify sessions on it", html)
        self.assertIn("Install GoAffPro on Shopify", html)
        # Withdrawn 2026-10-18: browsers pass the treestock referrer, so an
        # untagged click was never invisible to a nursery's analytics.
        self.assertNotIn("only about half our links carried the tag", html)

    def test_custom_site_states_no_terms(self):
        # Daleys: custom site, asked in the email what it thinks is fair. The
        # report must not name Shopify or GoAffPro, or set the terms first.
        wa = {"rows": [{"state": "WA", "clicks": 298, "ships": True, "seasonal": True},
                       {"state": "NSW", "clicks": 162, "ships": True, "seasonal": False}],
              "elsewhere": 0, "unshippable": 0, "seasonal": 298,
              "restricted_home": 0, "restricted_away": 0}
        html = self._render(bpr.recipient("daleys", "feed"), wa)
        self.assertNotIn("Shopify", html)
        self.assertNotIn("GoAffPro", html)
        self.assertNotIn("referral arrangement", html)
        self.assertIn("filtering your analytics on it", html)
        self.assertIn("From our data", html)
        self.assertIn("In windows", html)
        self.assertIn("298 clicks (65%) came from WA</strong>, where you ship in windows", html)
        self.assertIn("never take commission into account", html)
        self.assertNotIn("—", html)

    def test_partner_is_not_asked_for_anything(self):
        html = self._render(bpr.recipient("primal-fruits", "ecwid"))
        self.assertIn("You're a referral partner", html)
        self.assertNotIn("Install GoAffPro", html)


if __name__ == "__main__":
    unittest.main()
