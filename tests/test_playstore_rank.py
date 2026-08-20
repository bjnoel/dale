"""Guards for the Google Play keyword rank reader (DAL-279 baseline).

The Apple reader's guards (tests/test_appstore_rank.py) all apply here, plus
one failure mode that is specific to Play and does not exist on Apple:

    Apple returns up to 200 results and usually fewer, so "absent from n=191"
    proves absence. Play serves ~30 before lazy-loading, so "absent from n=30"
    proves nothing at all -- our app may sit at rank 31.

If those two cases ever render the same way, a rename that pushed us from #25
to #31 would read as unchanged-and-absent instead of as a loss, and DAL-257
would score the name-field theory on a measurement that cannot see the move.
"""

import contextlib
import csv
import importlib.util
import io
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "tools" / "autonomous" / "playstore_rank.py"
)
spec = importlib.util.spec_from_file_location("playstore_rank", MODULE_PATH)
pr = importlib.util.module_from_spec(spec)
sys.modules["playstore_rank"] = pr
spec.loader.exec_module(pr)


def page(packages):
    """Minimal HTML carrying detail links in order, with Play's repeated slots."""
    return "".join(
        f'<a href="/store/apps/details?id={p}"></a>'
        f'<a href="/store/apps/details?id={p}">dup slot</a>'
        for p in packages
    )


class TestPackagesInOrder(unittest.TestCase):
    def test_dedupes_but_keeps_first_appearance_order(self):
        html = page(["com.a", "com.b", pr.OUR_PACKAGE])
        self.assertEqual(
            pr.packages_in_order(html), ["com.a", "com.b", pr.OUR_PACKAGE]
        )

    def test_ignores_non_result_markup(self):
        self.assertEqual(pr.packages_in_order("<html><body>no apps</body></html>"), [])


class TestRankOf(unittest.TestCase):
    def test_rank_is_one_based(self):
        self.assertEqual(pr.rank_of(["com.a", pr.OUR_PACKAGE, "com.c"]), 2)

    def test_absent_is_none_not_zero(self):
        # None and 0 must not be interchangeable: 0 would format as a rank.
        self.assertIsNone(pr.rank_of(["com.a", "com.b"]))

    def test_empty_result_set_is_absent(self):
        self.assertIsNone(pr.rank_of([]))


class TestSaturation(unittest.TestCase):
    """The distinction Apple's reader never had to make."""

    def test_full_window_is_truncated(self):
        self.assertTrue(pr.saturated(pr.WINDOW))

    def test_over_full_window_is_truncated(self):
        self.assertTrue(pr.saturated(pr.WINDOW + 5))

    def test_short_result_set_is_exhausted(self):
        self.assertFalse(pr.saturated(12))

    def test_empty_result_set_is_exhausted(self):
        # Play genuinely had nothing. That is a finding, not a truncation.
        self.assertFalse(pr.saturated(0))


class TestCellRendering(unittest.TestCase):
    def test_proven_and_unproven_absence_render_differently(self):
        unproven = pr.cell(
            {"term": "plant tracker", "result_count": pr.WINDOW, "truncated": True, "rank": None}
        )
        proven = pr.cell(
            {"term": "orchard tracker", "result_count": 12, "truncated": False, "rank": None}
        )
        self.assertNotEqual(unproven, proven)
        self.assertIn("+", unproven)
        self.assertNotIn("+", proven)

    def test_denominator_always_reaches_the_reader(self):
        # DEC-255: a bare "absent" could be truncation. The count must show.
        for row, expected in [
            ({"result_count": 30, "truncated": True, "rank": 25}, "#25/30"),
            ({"result_count": 12, "truncated": False, "rank": None}, "none/12"),
            ({"result_count": 30, "truncated": True, "rank": None}, "none/30+"),
        ]:
            self.assertEqual(pr.cell(row), expected)

    def test_error_never_renders_as_not_ranked(self):
        # DEC-249: an absence of measurement and a measured zero must differ.
        rendered = pr.cell({"term": "x", "error": "HTTPError: 429"})
        self.assertEqual(rendered, "ERR")
        self.assertNotIn("none", rendered)


class TestMeasure(unittest.TestCase):
    def test_error_is_recorded_not_swallowed(self):
        def boom(term, country):
            raise TimeoutError("upstream said no")

        rows = pr.measure("AU", terms=[("brand", "treesmith")], pause=0, fetcher=boom)
        self.assertEqual(len(rows), 1)
        self.assertIn("error", rows[0])
        self.assertNotIn("rank", rows[0])

    def test_measures_and_flags_truncation(self):
        def fake(term, country):
            return page([f"com.f{i}" for i in range(29)] + [pr.OUR_PACKAGE])

        rows = pr.measure("AU", terms=[("brand", "treesmith")], pause=0, fetcher=fake)
        self.assertEqual(rows[0]["rank"], 30)
        self.assertEqual(rows[0]["result_count"], 30)
        self.assertTrue(rows[0]["truncated"])


class TestSharedTermSet(unittest.TestCase):
    """A forked term list would silently stop the two stores being comparable.

    Checked by scanning the source rather than comparing module identity: both
    readers get loaded by importlib under a fixed name, so whichever test file
    runs second replaces the other's entry in sys.modules and an identity check
    would fail on test ordering rather than on a real fork.
    """

    def test_playstore_reader_never_defines_its_own_term_set(self):
        src = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIsNone(
            re.search(r"^TERMS\s*[:=]", src, re.MULTILINE),
            "playstore_rank.py defines TERMS itself; import it from appstore_rank",
        )
        self.assertIsNotNone(
            re.search(r"^from appstore_rank import .*\bTERMS\b", src, re.MULTILINE),
            "playstore_rank.py must import TERMS from appstore_rank",
        )

    def test_apple_reader_owns_the_term_set(self):
        apple_src = (MODULE_PATH.parent / "appstore_rank.py").read_text(encoding="utf-8")
        self.assertIsNotNone(
            re.search(r"^TERMS\s*[:=]", apple_src, re.MULTILINE),
            "appstore_rank.py is the single definition site for TERMS",
        )

    def test_every_imported_group_is_measurable(self):
        self.assertTrue(pr.TERMS, "term set loaded empty")
        for group, terms in pr.TERMS.items():
            self.assertIsInstance(terms, list, f"{group} is not a list")
            self.assertTrue(terms, f"{group} is empty")
        # all_terms() flattens what measure() will iterate; it must cover them all.
        flat = pr.all_terms()
        self.assertEqual(len(flat), sum(len(v) for v in pr.TERMS.values()))


class TestRender(unittest.TestCase):
    def test_storefront_with_nothing_useful_still_appears(self):
        rows = {
            "AU": [{"group": "brand", "term": "treesmith", "result_count": 30, "truncated": True, "rank": 1}],
            "US": [{"group": "brand", "term": "treesmith", "error": "HTTPError: 503"}],
        }
        out = pr.render(rows)
        self.assertIn("US", out)
        self.assertIn("ERR", out)
        self.assertIn("!! ERRORS", out)


class TestSeriesFlag(unittest.TestCase):
    """--csv is purely additive, and it must carry Play's window semantics.

    measure() is replaced rather than its `fetcher` argument: main() calls
    measure() with the default seam, which was bound at definition time, so
    patching pr.fetch would leave the test talking to the real Play search page.
    """

    def _run(self, argv, rows):
        original, pr.measure = pr.measure, lambda country, terms=None: [
            dict(r, country=country) for r in rows
        ]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                pr.main(argv)
        finally:
            pr.measure = original
        return out.getvalue()

    def _row(self, packages):
        rows = [{
            "group": "brand", "term": "treesmith",
            "result_count": len(packages),
            "truncated": pr.saturated(len(packages)),
            "rank": pr.rank_of(packages),
            "top3": packages[:3],
        }]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "series.csv")
            self._run(["--country", "AU", "--csv", path,
                       "--captured-at", "2026-08-20T02:00:00Z"], rows)
            with open(path, newline="", encoding="utf-8") as fh:
                return list(csv.DictReader(fh))[0]

    def test_a_ranked_row_lands_as_ranked(self):
        row = self._row([pr.OUR_PACKAGE] + [f"pkg.{i}" for i in range(5)])
        self.assertEqual(row["store"], "play")
        self.assertEqual(row["captured_at"], "2026-08-20T02:00:00Z")
        self.assertEqual(row["rank"], "1")
        self.assertEqual(row["status"], "ranked")
        self.assertEqual(row["top3_1"], pr.OUR_PACKAGE)

    def test_absence_in_a_full_window_is_not_written_as_proven(self):
        # 30 results and no us: we may be at 31. The series must say so.
        row = self._row([f"pkg.{i}" for i in range(pr.WINDOW)])
        self.assertEqual(row["rank"], "")
        self.assertEqual(row["status"], "absent_window_capped")
        self.assertEqual(row["truncated"], "true")

    def test_absence_below_the_window_is_written_as_proven(self):
        row = self._row([f"pkg.{i}" for i in range(12)])
        self.assertEqual(row["rank"], "")
        self.assertEqual(row["status"], "absent")
        self.assertEqual(row["truncated"], "false")

    def test_the_two_absences_do_not_write_the_same_row(self):
        capped = self._row([f"pkg.{i}" for i in range(pr.WINDOW)])
        proven = self._row([f"pkg.{i}" for i in range(12)])
        self.assertNotEqual(capped["status"], proven["status"])


if __name__ == "__main__":
    unittest.main()
