"""Pagination completeness for every external API reader (DAL-261).

The same defect has now produced four wrong numbers in four days: a fetcher
issues one request, the API returns a full first page, and the code treats
that page as the complete result set. `gsc_analysis.py` (DEC-243), the
Plausible breakdowns (DEC-248), `resend_engagement.py` (DEC-250) and a
PostHog row fetch (DEC-252) all failed this way. A saturated first page and
a complete small result set are indistinguishable at the call site, so the
only reliable guard is a test that hands each fetcher a saturated first page
and asserts it goes back for the rest.

Each test drives the real fetcher against a fake transport that would return
a truncated answer if the fetcher stopped after one request.
"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path

AUTONOMOUS = Path(__file__).resolve().parents[1] / "tools" / "autonomous"


def load(name, filename):
    """Import a tools/autonomous script by path (some have hyphens in names).

    Registered under a namespaced key. `daily_digest` and `nursery_crm` are
    also real module names elsewhere in the tree, and binding the autonomous
    file to the bare name shadows tools/scrapers/daily_digest.py for every
    test that runs afterwards.
    """
    key = f"_dale_autonomous_{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, AUTONOMOUS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


class FakeGscService:
    """Mimics the GSC searchanalytics resource, honouring startRow/rowLimit."""

    def __init__(self, total_rows):
        self.rows = [{"keys": [f"q{i}"], "clicks": 1, "impressions": 10,
                      "position": 5.0} for i in range(total_rows)]
        self.requests = []

    def searchanalytics(self):
        return self

    def query(self, siteUrl, body):  # noqa: N803 (matches the Google client)
        self.requests.append(body)
        start = body["startRow"]
        end = start + body["rowLimit"]
        page = self.rows[start:end]
        return types.SimpleNamespace(execute=lambda: {"rows": page})


class TestGscPagination(unittest.TestCase):
    """traffic_report.gsc_query used rowLimit=200 with startRow fixed at 0.

    Its callers compute a set difference between two periods, so truncation
    did not shorten the answer, it inverted it: a query present in both
    periods but outside the truncated slice of the earlier one was reported
    as brand new. Measured against live GSC on 2026-07-30, 9 of the 10 "new
    queries" in the daily email were queries we already ranked for.
    """

    def setUp(self):
        self.tr = load("traffic_report", "traffic_report.py")

    def test_reads_every_row_past_the_first_page(self):
        svc = FakeGscService(total_rows=1703)
        rows = self.tr.gsc_query(svc, "sc-domain:example", "2026-07-01",
                                 "2026-07-07", ["query"], page_size=200)
        self.assertEqual(len(rows), 1703)
        self.assertGreater(len(svc.requests), 1)

    def test_advances_start_row_rather_than_refetching_page_one(self):
        svc = FakeGscService(total_rows=450)
        self.tr.gsc_query(svc, "sc-domain:example", "2026-07-01", "2026-07-07",
                          ["query"], page_size=200)
        self.assertEqual([r["startRow"] for r in svc.requests], [0, 200, 400])

    def test_exact_multiple_of_page_size_is_not_cut_short(self):
        # The nastiest case: the last full page looks identical to a saturated
        # one, so a fetcher must issue one more request to learn it is done.
        svc = FakeGscService(total_rows=400)
        rows = self.tr.gsc_query(svc, "sc-domain:example", "2026-07-01",
                                 "2026-07-07", ["query"], page_size=200)
        self.assertEqual(len(rows), 400)
        self.assertEqual(len(svc.requests), 3)

    def test_short_first_page_issues_exactly_one_request(self):
        svc = FakeGscService(total_rows=12)
        rows = self.tr.gsc_query(svc, "sc-domain:example", "2026-07-01",
                                 "2026-07-07", ["query"], page_size=200)
        self.assertEqual(len(rows), 12)
        self.assertEqual(len(svc.requests), 1)

    def test_callers_do_not_reintroduce_a_row_cap(self):
        source = (AUTONOMOUS / "traffic_report.py").read_text()
        self.assertNotIn("row_limit=200", source)


class TestResendReportPagination(unittest.TestCase):
    """resend_report.py kept a second, unpaginated copy of fetch_emails.

    DEC-250 fixed this exact bug in resend_engagement.py and missed the
    sibling. One page is ~17 days of sends at current volume, so the default
    7-day window happened to fit and the report looked correct, while the
    documented `--days 14` and any growth in send volume would have reported
    a partial window under a heading asserting the full one.
    """

    def setUp(self):
        self.mod = load("resend_report", "resend_report.py")

    def test_delegates_to_the_paginated_fetcher(self):
        engagement = sys.modules.get("resend_engagement") or load(
            "resend_engagement", "resend_engagement.py")
        calls = []

        def fake(api_key, limit=100, max_pages=200):
            calls.append(limit)
            return [{"id": "a"}, {"id": "b"}]

        original = self.mod._engagement_fetch_emails
        self.mod._engagement_fetch_emails = fake
        try:
            result = self.mod.fetch_emails("key")
        finally:
            self.mod._engagement_fetch_emails = original
        self.assertEqual(len(result), 2)
        self.assertEqual(calls, [100])
        self.assertTrue(hasattr(engagement, "fetch_emails"))

    def test_does_not_keep_its_own_unpaginated_request(self):
        source = (AUTONOMOUS / "resend_report.py").read_text()
        self.assertNotIn("https://api.resend.com/emails?limit=", source)


class TestNurseryCrmCapIsAnnounced(unittest.TestCase):
    """outbound_clicks paginates, but ran off the end of range(1, 41) silently.

    Reaching the last page with a full page of results means there is more
    data we did not read. Returning that total unannounced is the same shape
    of failure as not paginating at all.
    """

    def test_cap_exhaustion_warns_on_stderr(self):
        import io
        import contextlib

        crm = load("nursery_crm", "nursery_crm.py")
        fake_stats = types.ModuleType("plausible_stats")
        fake_stats.load_plausible_config = lambda: ("token", "host")
        fake_stats.api_get = lambda *a, **k: {
            "results": [{"url": f"https://n{i}.com/p", "events": 1, "visitors": 1}
                        for i in range(1000)]
        }
        saved = sys.modules.get("plausible_stats")
        sys.modules["plausible_stats"] = fake_stats
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                crm.outbound_clicks()
        finally:
            sys.modules.pop("plausible_stats", None)
            if saved is not None:
                sys.modules["plausible_stats"] = saved
        self.assertIn("PARTIAL", err.getvalue())

    def test_complete_result_does_not_warn(self):
        import io
        import contextlib

        crm = load("nursery_crm", "nursery_crm.py")
        fake_stats = types.ModuleType("plausible_stats")
        fake_stats.load_plausible_config = lambda: ("token", "host")
        fake_stats.api_get = lambda *a, **k: {
            "results": [{"url": "https://n.com/p", "events": 3, "visitors": 2}]
        }
        saved = sys.modules.get("plausible_stats")
        sys.modules["plausible_stats"] = fake_stats
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                agg = crm.outbound_clicks()
        finally:
            sys.modules.pop("plausible_stats", None)
            if saved is not None:
                sys.modules["plausible_stats"] = saved
        self.assertNotIn("PARTIAL", err.getvalue())
        self.assertEqual(agg["n.com"]["clicks"], 3)


class TestEngagementStampPagination(unittest.TestCase):
    """The strike gate reads this. An unseen signal reads as absence.

    update_engagement_stamp took a single `first: 50` page of issues touched
    since the cutoff. With more than 50 touched issues, Benedict's activity
    could sit on page two, and DEC-226 turns "no sign of Benedict" into a
    strike, so the failure runs in the damaging direction.
    """

    def test_follows_the_cursor_and_finds_a_human_on_page_two(self):
        digest = load("daily_digest", "daily-digest.py")
        pages = [
            {"issues": {
                "nodes": [{"history": {"nodes": [
                    {"createdAt": "2026-07-29T00:00:00Z", "actor": {"name": "Dale"}}]},
                    "comments": {"nodes": []}}],
                "pageInfo": {"hasNextPage": True, "endCursor": "c1"}}},
            {"issues": {
                "nodes": [{"history": {"nodes": [
                    {"createdAt": "2026-07-30T00:00:00Z",
                     "actor": {"name": "Benedict Noel"}}]},
                    "comments": {"nodes": []}}],
                "pageInfo": {"hasNextPage": False, "endCursor": None}}},
        ]
        seen = []

        def fake_graphql(query, variables=None):
            seen.append((variables or {}).get("after"))
            return pages[len(seen) - 1]

        import tempfile
        original = digest.graphql
        digest.graphql = fake_graphql
        try:
            with tempfile.TemporaryDirectory() as tmp:
                result = digest.update_engagement_stamp(
                    "team", "2026-07-01T00:00:00Z", tmp)
                self.assertTrue(result, "human activity on page 2 must be seen")
                self.assertTrue((Path(tmp) / "benedict-engagement.json").exists())
        finally:
            digest.graphql = original
        self.assertEqual(seen, [None, "c1"])


if __name__ == "__main__":
    unittest.main()


class TestResendDeliveryClassification(unittest.TestCase):
    """`last_event` is the furthest state reached, not a set of flags.

    Counting only the literal "delivered" excluded every email that was
    opened or clicked, so the reported delivery rate FELL as engagement rose.
    On 2026-07-30 it read 52.5% against a true 100% delivered, 0 bounced.
    """

    def setUp(self):
        self.mod = load("resend_report", "resend_report.py")

    def _emails(self):
        return [{"from": "alerts@mail.treestock.com.au", "last_event": ev,
                 "to": [f"{i}@example.com"], "subject": "Nursery Stock Update",
                 "created_at": "2026-07-29T00:00:00.000Z"}
                for i, ev in enumerate(
                    ["delivered", "delivered", "opened", "clicked", "bounced"])]

    def test_opened_and_clicked_count_as_delivered(self):
        report = self.mod.build_report(self._emails(), days=3650)
        stats = report["programs"]["treestock_digest"]
        self.assertEqual(stats["sent"], 5)
        self.assertEqual(stats["delivered"], 4)  # not 2
        self.assertEqual(stats["bounced"], 1)
        self.assertEqual(stats["delivery_rate_pct"], 80.0)

    def test_open_rate_includes_clicks(self):
        stats = self.mod.build_report(self._emails(), days=3650)["programs"]["treestock_digest"]
        self.assertEqual(stats["opened"], 2)   # opened + clicked
        self.assertEqual(stats["clicked"], 1)

    def test_perfect_engagement_does_not_read_as_a_delivery_failure(self):
        # The inverted-metric case: every email was opened or clicked.
        emails = [{"from": "alerts@mail.treestock.com.au", "last_event": ev,
                   "to": [f"{i}@example.com"], "subject": "Nursery Stock Update",
                   "created_at": "2026-07-29T00:00:00.000Z"}
                  for i, ev in enumerate(["opened", "clicked", "opened"])]
        stats = self.mod.build_report(emails, days=3650)["programs"]["treestock_digest"]
        self.assertEqual(stats["delivery_rate_pct"], 100.0)
