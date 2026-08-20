"""
The contested-query series: the thing that decides whether DEC-309 worked.

Two failure modes this measurement could have had, and the tests that pin them:

- A 90-day window shares 89 days with last week's, so a real change reads as a
  rounding error for a month. Readings are taken over short trailing windows.
- One post-change point has nothing to compare against, so "it fell" is a story
  rather than a finding. summarise() refuses to judge until there are three
  pre-change readings, and compares against their spread rather than a single
  prior value.

The headline is a SHARE, not a count: total query volume swings with bare-root
season, which is exactly when the pre-change baseline was taken.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

import contested_queries as cq  # noqa: E402


def row(query, page, clicks=0, impressions=10, position=10.0):
    return {"keys": [query, page], "clicks": clicks,
            "impressions": impressions, "position": position}


class FakeService:
    """Stands in for the GSC client. cq.measure only calls query_gsc."""
    def __init__(self, rows):
        self.rows = rows


def fake_query_gsc(service, site, start, end, dims, row_limit=None):
    return service.rows


class MeasureTests(unittest.TestCase):
    def setUp(self):
        self._real = cq.query_gsc
        cq.query_gsc = fake_query_gsc

    def tearDown(self):
        cq.query_gsc = self._real

    def _measure(self, rows):
        return cq.measure(FakeService(rows), "2026-08-01", "2026-08-07")

    def test_a_query_needs_both_page_types_to_be_contested(self):
        m = self._measure([
            row("pecan tree", "/species/pecan.html"),
            row("pecan tree", "/compare/pecan-prices.html"),
            row("mango tree", "/species/mango.html"),          # species only
            row("fig prices", "/compare/fig-prices.html"),      # compare only
            row("lemon myrtle", "/variety/lemon-myrtle-x.html"),
        ])
        self.assertEqual(m["contested_queries"], 1)
        self.assertEqual(m["total_queries"], 4)

    def test_share_is_a_share_not_a_count(self):
        # Same contested count, twice the uncontested volume: the share halves.
        base = [row("pecan tree", "/species/pecan.html"),
                row("pecan tree", "/compare/pecan-prices.html")]
        thin = self._measure(base + [row("q1", "/species/a.html")])
        fat = self._measure(base + [row(f"q{i}", "/species/a.html") for i in range(3)])
        self.assertEqual(thin["contested_queries"], fat["contested_queries"])
        self.assertGreater(thin["contested_share"], fat["contested_share"])

    def test_the_better_page_is_impression_weighted(self):
        # Species is shown once at position 3 and 200 times at 40; compare sits
        # at 11 throughout. A naive best-position rule would call species the
        # winner on the strength of a single impression.
        m = self._measure([
            row("apple tree", "/species/apple.html", impressions=1, position=3.0),
            row("apple tree", "/species/apple.html", impressions=200, position=40.0),
            row("apple tree", "/compare/apple-prices.html", impressions=50, position=11.0),
        ])
        self.assertEqual(m["compare_better"], 1)
        self.assertEqual(m["species_better"], 0)

    def test_the_compare_index_is_not_a_compare_page(self):
        # /compare/index.html is a hub, not a species price page, and counting it
        # would make every query that surfaces the hub look contested.
        m = self._measure([
            row("fruit tree prices", "/species/apple.html"),
            row("fruit tree prices", "/compare/index.html"),
        ])
        self.assertEqual(m["contested_queries"], 0)

    def test_empty_window_does_not_divide_by_zero(self):
        m = self._measure([])
        self.assertEqual(m["contested_share"], 0.0)
        self.assertEqual(m["contested_ctr"], 0.0)


class AppendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.csv = Path(self.tmp.name) / "series.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def _rec(self, end, window=7, share=0.05):
        return {f: "" for f in cq.FIELDS} | {
            "captured_at": "2026-08-20T00:00:00Z", "window_days": window,
            "start": "2026-08-01", "end": end, "total_queries": 100,
            "contested_queries": 5, "contested_share": share,
            "contested_impressions": 50, "contested_clicks": 1,
            "contested_ctr": 0.02, "species_better": 2, "compare_better": 3,
        }

    def test_rereading_the_same_window_does_not_duplicate_it(self):
        self.assertEqual(cq.append(self.csv, [self._rec("2026-08-17")]), 1)
        self.assertEqual(cq.append(self.csv, [self._rec("2026-08-17")]), 0)
        self.assertEqual(len(cq.read_series(self.csv)), 1)

    def test_the_same_end_date_at_a_different_window_is_a_different_reading(self):
        cq.append(self.csv, [self._rec("2026-08-17", window=7)])
        self.assertEqual(cq.append(self.csv, [self._rec("2026-08-17", window=28)]), 1)

    def test_header_is_written_once(self):
        cq.append(self.csv, [self._rec("2026-08-10")])
        cq.append(self.csv, [self._rec("2026-08-17")])
        with self.csv.open() as fh:
            self.assertEqual(sum(1 for line in fh if line.startswith("captured_at")), 1)


class SummariseTests(unittest.TestCase):
    def _series(self, before_shares, after_shares):
        out = []
        for i, s in enumerate(before_shares):
            out.append({"window_days": "7", "end": f"2026-07-{i + 1:02d}",
                        "contested_share": str(s), "species_better": "1",
                        "compare_better": "1"})
        for i, s in enumerate(after_shares):
            out.append({"window_days": "7", "end": f"2026-09-{i + 1:02d}",
                        "contested_share": str(s), "species_better": "1",
                        "compare_better": "1"})
        return out

    def test_refuses_to_judge_without_enough_before_readings(self):
        self.assertIsNone(cq.summarise(self._series([0.05, 0.06], [0.01]), 7))

    def test_refuses_to_judge_with_no_after_reading(self):
        self.assertIsNone(cq.summarise(self._series([0.05, 0.06, 0.055], []), 7))

    def test_a_move_inside_normal_variation_is_not_called_a_result(self):
        s = cq.summarise(self._series([0.04, 0.06, 0.05, 0.055], [0.045]), 7)
        self.assertFalse(s["outside"])
        self.assertIn("inside normal week-to-week variation", cq.describe(s))

    def test_a_real_drop_is_flagged_with_its_direction(self):
        s = cq.summarise(self._series([0.050, 0.051, 0.049, 0.050], [0.010]), 7)
        self.assertTrue(s["outside"])
        self.assertEqual(s["direction"], "down")
        self.assertIn("OUTSIDE the band", cq.describe(s))

    def test_the_band_ignores_history_older_than_the_state_we_changed(self):
        """The series trends hard: 0.00% every week through May, ~2% by August.

        Averaging all of it describes 2026-05 rather than what we changed, and
        the 2026-08-20 backfill made that concrete: over 16 weeks the 7d band is
        -0.94% to 3.50%, a lower bound no drop can cross. The check would have
        reported "normal" forever.
        """
        old = [0.0] * 8                       # the dead months
        recent = [0.021, 0.019, 0.023, 0.018, 0.033, 0.032, 0.018, 0.016]
        s = cq.summarise(self._series(old + recent, [0.005]), 7)
        self.assertEqual(s["n_before"], cq.BAND_READINGS)
        self.assertGreater(s["band_low"], 0.0, "a band that starts at zero can never flag a drop")
        self.assertTrue(s["outside"], "a drop to a third of the recent level was not flagged")

    def test_the_band_never_reports_a_negative_share(self):
        s = cq.summarise(self._series([0.01, 0.03, 0.005, 0.04], [0.02]), 7)
        self.assertGreaterEqual(s["band_low"], 0.0)

    def test_a_flat_before_arm_cannot_manufacture_a_result(self):
        # Zero spread would make any difference "significant" on a naive test.
        s = cq.summarise(self._series([0.05, 0.05, 0.05], [0.05]), 7)
        self.assertFalse(s["outside"])


if __name__ == "__main__":
    unittest.main()
