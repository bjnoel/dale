"""Tests for GSC row pagination (DAL-235).

Google Search Console caps a single searchanalytics response and reports no
total row count, so an unpaginated request truncates silently. It does not
error, it just returns the top N rows by impressions, and every derived
statistic (page-type CTR, clicks per page, "high opportunity" query lists)
is then computed on a biased subset.

This bit us for real: with row_limit=500 on the page dimension, the page-type
breakdown reported variety pages as 223 pages / 4,017 impressions / 8.0% CTR,
which read as our best-converting page type by 4x. Paginated, it is 1,669
pages / 13,576 impressions / 2.4% CTR, which is merely average. Same failure
class as the Plausible breakdown bug in DEC-241.
"""

import os
import sys
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools", "scrapers"))

import gsc_analysis  # noqa: E402


PAGE = 1000  # stand-in for GSC_MAX_ROWS_PER_PAGE, patched in during tests


def fake_service(total_rows):
    """A GSC double that honours rowLimit exactly, as the real API does."""
    rows = [
        {"keys": [f"q{i}"], "clicks": 1, "impressions": 10, "ctr": 0.1, "position": 5.0}
        for i in range(total_rows)
    ]
    calls = []

    def query(siteUrl, body):
        calls.append(dict(body))
        start = body["startRow"]
        execute = mock.Mock()
        execute.execute.return_value = {"rows": rows[start:start + body["rowLimit"]]}
        return execute

    svc = mock.Mock()
    svc.searchanalytics.return_value.query.side_effect = query
    return svc, calls, rows


class TestQueryPagination(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(gsc_analysis, "GSC_MAX_ROWS_PER_PAGE", PAGE)
        patcher.start()
        self.addCleanup(patcher.stop)

    def call(self, svc, **kw):
        return gsc_analysis.query_gsc(
            svc, "sc-domain:treestock.com.au", "2026-06-30", "2026-07-27", ["page"], **kw
        )

    def test_single_short_page_stops_after_one_request(self):
        svc, calls, _ = fake_service(120)
        got = self.call(svc)
        self.assertEqual(120, len(got))
        self.assertEqual(1, len(calls))

    def test_returns_every_row_across_pages(self):
        svc, calls, rows = fake_service(2600)
        got = self.call(svc)
        self.assertEqual(2600, len(got))
        self.assertEqual([r["keys"] for r in rows], [r["keys"] for r in got])
        self.assertEqual(3, len(calls))

    def test_start_row_advances(self):
        svc, calls, _ = fake_service(2600)
        self.call(svc)
        self.assertEqual([0, 1000, 2000], [c["startRow"] for c in calls])

    def test_exact_multiple_of_page_size_does_not_lose_rows(self):
        """The off-by-one that drops the last page or loops forever."""
        svc, calls, _ = fake_service(2000)
        got = self.call(svc)
        self.assertEqual(2000, len(got))
        self.assertEqual(3, len(calls))  # third comes back empty and stops

    def test_no_rows_at_all(self):
        svc, _, _ = fake_service(0)
        self.assertEqual([], self.call(svc))

    def test_row_limit_caps_the_total(self):
        svc, calls, _ = fake_service(5000)
        got = self.call(svc, row_limit=1500)
        self.assertEqual(1500, len(got))
        self.assertTrue(all(c["rowLimit"] <= 1000 for c in calls))

    def test_row_limit_never_requests_a_negative_page(self):
        svc, calls, _ = fake_service(5000)
        gsc_analysis.query_gsc(
            svc, "s", "a", "b", ["page"], row_limit=1000
        )
        self.assertTrue(all(c["rowLimit"] > 0 for c in calls))

    def test_default_is_unlimited(self):
        """Regression guard: a default row_limit is how the truncation got in."""
        import inspect
        sig = inspect.signature(gsc_analysis.query_gsc)
        self.assertIsNone(sig.parameters["row_limit"].default)

    def test_http_error_returns_rows_gathered_so_far(self):
        rows = [{"keys": [f"q{i}"], "clicks": 0, "impressions": 1, "ctr": 0.0,
                 "position": 9.0} for i in range(1500)]
        state = {"n": 0}

        def query(siteUrl, body):
            execute = mock.Mock()
            if state["n"] == 0:
                state["n"] += 1
                execute.execute.return_value = {"rows": rows[:1000]}
            else:
                execute.execute.side_effect = gsc_analysis.HttpError(
                    mock.Mock(status=500), b"boom"
                )
            return execute

        svc = mock.Mock()
        svc.searchanalytics.return_value.query.side_effect = query
        # Force a small page size so the first call looks "full" and it pages on.
        with mock.patch.object(gsc_analysis, "GSC_MAX_ROWS_PER_PAGE", 1000):
            got = gsc_analysis.query_gsc(svc, "s", "a", "b", ["page"])
        self.assertEqual(1000, len(got))


class TestCallSitesDoNotTruncate(unittest.TestCase):
    """The bug was never in the helper alone, it was the row_limit= arguments."""

    def test_no_call_site_passes_a_row_limit(self):
        path = os.path.join(REPO, "tools", "scrapers", "gsc_analysis.py")
        with open(path) as fh:
            src = fh.read()
        offenders = [
            line.strip()
            for line in src.splitlines()
            if "query_gsc(service" in line
            and "row_limit" in line
            and not line.strip().startswith("def ")
        ]
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
