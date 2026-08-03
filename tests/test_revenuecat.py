"""Guards for the RevenueCat revenue reader (DAL-265, DEC-260).

Three classes of defect this business has already shipped once each, now
asserted against on the one code path that reports money:

1. Truncation. A saturated first page and a complete result set look
   identical at the call site (DEC-255). `paginate` must go back for more.
2. Rounding an unknown towards revenue. `coalesce(environment,'production')`
   would have reported 12 sales we never made (DEC-253). Anything that is
   not literally "production" must be excluded.
3. Reporting a number the operator would not recognise (DEC-259). Gross is
   not revenue; proceeds is what reaches the bank, and the two differ by
   about a third.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

AUTONOMOUS = Path(__file__).resolve().parents[1] / "tools" / "autonomous"


def load(name, filename):
    key = f"_dale_autonomous_{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, AUTONOMOUS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


rc = load("revenuecat", "revenuecat.py")
ta = load("treesmith_analytics", "treesmith_analytics.py")


def purchase(env="production", gross=24.99, proceeds=17.49, at=1784000000000,
             country="AU", store="app_store"):
    return {
        "environment": env, "purchased_at": at, "country": country,
        "store": store,
        "revenue_in_usd": {"gross": gross, "proceeds": proceeds,
                           "commission": 3.75, "tax": 2.5, "currency": "USD"},
    }


class FakeApi:
    """Serves paged list responses and records every URL requested."""

    def __init__(self, pages_by_path):
        self.pages = pages_by_path
        self.requests = []

    def __call__(self, url, api_key):
        self.requests.append(url)
        for path, pages in self.pages.items():
            if path in url:
                # Which page? Count how many of this path we have served.
                seen = sum(1 for r in self.requests[:-1] if path in r)
                items, more = pages[min(seen, len(pages) - 1)]
                return {"items": items,
                        "next_page": f"https://x/{path}?page={seen + 2}"
                                     if more else None}
        return {"items": [], "next_page": None}


class PaginationTests(unittest.TestCase):
    def test_paginate_follows_next_page_to_exhaustion(self):
        # A full first page that would look complete to a single-shot reader.
        page1 = ([{"id": f"c{i}"} for i in range(100)], True)
        page2 = ([{"id": "c100"}], False)
        api = FakeApi({"/customers": [page1, page2]})
        items = rc.paginate("/customers?limit=100", "k", "proj", _opener=api)
        self.assertEqual(len(items), 101, "stopped after the first page")
        self.assertEqual(len(api.requests), 2)

    def test_paginate_handles_exact_multiple_of_page_size(self):
        # The nastiest case: the last full page is indistinguishable from a
        # truncated one, so the fetcher must ask again and get an empty page.
        page1 = ([{"id": f"c{i}"} for i in range(100)], True)
        page2 = ([], False)
        api = FakeApi({"/customers": [page1, page2]})
        items = rc.paginate("/customers?limit=100", "k", "proj", _opener=api)
        self.assertEqual(len(items), 100)
        self.assertEqual(len(api.requests), 2)

    def test_fetch_purchases_asks_every_customer(self):
        customers = [{"id": f"$RCAnonymousID:{i}"} for i in range(5)]
        api = FakeApi({"/purchases": [([purchase()], False)]})
        got = rc.fetch_purchases("proj", "k", customers, _opener=api,
                                 max_workers=1)
        self.assertEqual(len(got), 5)


class EnvironmentTests(unittest.TestCase):
    def test_sandbox_is_never_counted_as_revenue(self):
        s = rc.summarise([
            purchase(env="production", proceeds=17.49),
            purchase(env="sandbox", proceeds=45.35),
        ])
        self.assertEqual(s["production_n"], 1)
        self.assertEqual(s["production_proceeds_usd"], 17.49)
        self.assertIn("sandbox", s["by_env"])

    def test_unknown_environment_is_excluded_not_assumed_production(self):
        s = rc.summarise([purchase(env=None, proceeds=99.0)])
        self.assertEqual(s["production_n"], 0)
        self.assertEqual(s["production_proceeds_usd"], 0.0)
        self.assertIn("unknown", s["by_env"],
                      "an excluded purchase must stay visible, not vanish")

    def test_excluded_purchases_are_still_reported(self):
        s = rc.summarise([purchase(env="sandbox")])
        self.assertEqual(s["by_env"]["sandbox"]["n"], 1)


class ProceedsTests(unittest.TestCase):
    def test_proceeds_and_gross_are_reported_separately(self):
        s = rc.summarise([purchase(gross=27.74, proceeds=17.66)])
        self.assertEqual(s["production_gross_usd"], 27.74)
        self.assertEqual(s["production_proceeds_usd"], 17.66)
        self.assertLess(s["production_proceeds_usd"], s["production_gross_usd"])

    def test_monthly_breakdown_uses_proceeds(self):
        s = rc.summarise([
            purchase(at=1782000000000, proceeds=17.40),
            purchase(at=1784000000000, proceeds=17.66),
            purchase(at=1784100000000, proceeds=17.49),
        ])
        self.assertEqual(sum(m["n"] for m in s["by_month"].values()), 3)
        self.assertAlmostEqual(
            sum(m["proceeds"] for m in s["by_month"].values()), 52.55, places=2)


def digest_metrics(rc_data, posthog_production_n):
    """Minimal metrics dict: only the blocks render() needs to be exercised."""
    blank = {"ok": False, "error": "not under test"}
    return {
        "installs": blank, "active": blank, "identity": blank,
        "plants": blank, "activation": blank, "onboarding": blank,
        "funnel": blank, "paywall": blank, "retention": blank,
        "top_screens": blank, "backup": blank, "reconciliation": blank,
        "revenuecat": {"ok": True, "data": rc_data},
        "purchases": {"ok": True, "data": {"buckets": [], "production": [
            {"env": "production", "currency": "USD",
             "n_all": posthog_production_n, "revenue_all": 24.99,
             "n_7d": 0, "revenue_7d": 0.0},
        ]}},
    }


LIVE = {
    "production_n": 3, "production_proceeds_usd": 52.55,
    "production_gross_usd": 77.58, "countries": ["AU", "PK", "US"],
    "by_month": {"2026-06": {"n": 1, "proceeds": 17.40},
                 "2026-07": {"n": 2, "proceeds": 35.15}},
    "by_env": {"production": {"n": 3, "proceeds": 52.55, "gross": 77.58},
               "sandbox": {"n": 5, "proceeds": 136.56, "gross": 198.20}},
    "overview": {"revenue": 52}, "customers": 416,
}


class RenderTests(unittest.TestCase):
    """Per DEC-251: assert the rendered text, because the rendered text is the
    only surface a human ever reads."""

    def test_revenue_line_shows_proceeds_not_gross(self):
        text, _ = ta.render(digest_metrics(LIVE, 3))
        self.assertIn("Revenue ALL TIME (proceeds) US$52.55", text)
        self.assertNotIn("Revenue ALL TIME (proceeds) US$77.58", text)

    def test_gross_is_still_shown_but_labelled(self):
        text, _ = ta.render(digest_metrics(LIVE, 3))
        self.assertIn("gross before store cut", text)
        self.assertIn("US$77.58", text)

    def test_sandbox_is_labelled_as_not_revenue(self):
        text, _ = ta.render(digest_metrics(LIVE, 3))
        self.assertIn("Excluded: sandbox", text)
        self.assertIn("not counted as revenue", text)

    def test_warns_when_posthog_has_fewer_sales_than_revenuecat(self):
        text, html = ta.render(digest_metrics(LIVE, 2))
        self.assertIn("RevenueCat has 3 paid purchases", text)
        self.assertIn("telemetry is missing 1", text)
        self.assertIn("telemetry is missing 1", html)

    def test_no_warning_when_the_two_sources_agree(self):
        text, _ = ta.render(digest_metrics(LIVE, 3))
        self.assertNotIn("The receipt wins", text)

    def test_a_revenuecat_failure_does_not_sink_the_digest(self):
        metrics = digest_metrics(LIVE, 3)
        metrics["revenuecat"] = {"ok": False, "error": "HTTP 401"}
        text, _ = ta.render(metrics)
        self.assertIn("RevenueCat: ERROR HTTP 401", text)


if __name__ == "__main__":
    unittest.main()
