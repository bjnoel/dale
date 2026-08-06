"""Guards for the App Store keyword rank reader (DAL-270).

The failure modes this file pins are the ones this business has already
shipped once each, aimed at the one code path that scores ASO decisions:

1. An error must never render as "not ranked" (DEC-249). An absence of
   measurement and a measured zero must not look alike, and a rank report
   is exactly where that confusion would silently reverse a conclusion.
2. The denominator must reach the reader (DEC-255). "absent from 191
   results" is a finding; "absent" on its own could be truncation.
3. A storefront must not disappear from the comparison because it returned
   nothing useful, for the same reason DEC-261's empty Android bucket had
   to keep being printed.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "autonomous" / "appstore_rank.py"
spec = importlib.util.spec_from_file_location("appstore_rank", MODULE_PATH)
ar = importlib.util.module_from_spec(spec)
sys.modules["appstore_rank"] = ar
spec.loader.exec_module(ar)


def app(track_id, name, ratings=0):
    return {"trackId": track_id, "trackName": name, "userRatingCount": ratings}


class TestRankOf(unittest.TestCase):
    def test_rank_is_one_based(self):
        results = [app(1, "A"), app(ar.OUR_TRACK_ID, "TreeSmith"), app(3, "C")]
        self.assertEqual(ar.rank_of(results), 2)

    def test_absent_is_none_not_zero(self):
        # None and 0 must not be interchangeable: 0 would format as a rank.
        self.assertIsNone(ar.rank_of([app(1, "A"), app(2, "B")]))

    def test_empty_result_set_is_absent(self):
        self.assertIsNone(ar.rank_of([]))


class TestNameMatch(unittest.TestCase):
    def test_counts_only_names_carrying_every_token(self):
        results = [
            app(1, "Fruit Tree Tracker - Grove"),
            app(2, "Tree Identifier AI"),
            app(3, "FruitForest: Orchard Mapping"),
            app(4, "fruit tree TRACKER pro"),
        ]
        # 2 of the top 4 carry all three tokens.
        self.assertAlmostEqual(
            ar.name_match_share(results, "fruit tree tracker", top_n=4), 0.5
        )

    def test_no_results_is_none_not_zero(self):
        self.assertIsNone(ar.name_match_share([], "fruit tree tracker"))


class TestMeasureRecordsErrors(unittest.TestCase):
    def test_an_error_is_recorded_not_reported_as_unranked(self):
        def boom(term, country):
            raise TimeoutError("upstream timed out")

        rows = ar.measure("US", terms=[("brand", "treesmith")], pause=0, searcher=boom)
        self.assertEqual(len(rows), 1)
        self.assertIn("error", rows[0])
        # The decisive assertion: a failed lookup must NOT carry a rank key
        # that reads as "we do not rank for this".
        self.assertNotIn("rank", rows[0])

    def test_error_row_renders_as_ERR_and_is_listed(self):
        def boom(term, country):
            raise TimeoutError("upstream timed out")

        rows = ar.measure("US", terms=[("brand", "treesmith")], pause=0, searcher=boom)
        text = ar.render({"US": rows})
        self.assertIn("ERR", text)
        self.assertIn("ERRORS", text)
        self.assertIn("NOT 'not ranked'", text)
        # And the row itself must not claim we are simply absent. Checked on
        # the row rather than the whole render, because the legend legitimately
        # explains what a "none/191" cell means.
        row = next(l for l in text.splitlines() if l.startswith("treesmith "))
        self.assertIn("ERR", row)
        self.assertNotIn("none", row)

    def test_absent_row_renders_with_its_denominator(self):
        def wide(term, country):
            return [app(i, f"App {i}") for i in range(191)]

        rows = ar.measure("US", terms=[("brand", "treesmith")], pause=0, searcher=wide)
        text = ar.render({"US": rows})
        # "absent from 191 results" is the finding; a bare "none" is not.
        self.assertIn("none/191", text)

    def test_rank_row_renders_with_its_denominator(self):
        def found(term, country):
            return [app(1, "A"), app(ar.OUR_TRACK_ID, "TreeSmith")] + [
                app(i + 10, f"App {i}") for i in range(50)
            ]

        rows = ar.measure("AU", terms=[("brand", "treesmith")], pause=0, searcher=found)
        text = ar.render({"AU": rows})
        self.assertIn("#2/52", text)


class TestComparison(unittest.TestCase):
    def test_a_storefront_where_we_never_rank_still_appears(self):
        """DEC-261: a bucket that produced nothing must still be printed."""

        def au(term, country):
            return [app(ar.OUR_TRACK_ID, "TreeSmith")]

        def us(term, country):
            return [app(i, f"App {i}") for i in range(120)]

        terms = [("brand", "treesmith")]
        text = ar.render(
            {
                "AU": ar.measure("AU", terms=terms, pause=0, searcher=au),
                "US": ar.measure("US", terms=terms, pause=0, searcher=us),
            }
        )
        self.assertIn("US", text)
        self.assertIn("none/120", text)
        self.assertIn("Ranked on AU only", text)


class TestTermSet(unittest.TestCase):
    def test_term_set_is_stable_and_unique(self):
        """DAL-257 compares against this run, so the list cannot drift silently."""
        terms = [t for _, t in ar.all_terms()]
        self.assertEqual(len(terms), len(set(terms)), "duplicate term in TERMS")
        # The terms DEC-247 drew its conclusions from must all still be measured.
        for t in (
            "fruit tree tracker",
            "orchard tracker",
            "tree tracker",
            "graft tracker",
            "plant tracker",
            "garden journal",
        ):
            self.assertIn(t, terms)

    def test_requests_apples_maximum_page_size(self):
        """limit=200 is what turns 'not in top 50' into a real rank (DEC-255)."""
        self.assertEqual(ar.LIMIT, 200)


if __name__ == "__main__":
    unittest.main()
