"""Guards for the append-only keyword rank series (DAL-257).

The readers already enforce DEC-249 structurally: an errored row omits `rank`,
`result_count` and `truncated` entirely, so an absence of measurement cannot be
read as a measured zero. A CSV cell cannot be absent, only empty, so this layer
has to hold the same three-way distinction by naming the states instead.

Everything here is aimed at one failure: two different facts rendering the same
way. Specifically

    error                 nothing was measured (DEC-249)
    absent                measured, and absence is PROVEN (DEC-255)
    absent_window_capped  measured, and absence is NOT proven -- we may be at 31

If any pair of those ever collapses, a rename that pushed us from #25 to #31
reads as unchanged-and-absent, and the name-field theory gets scored on a
measurement that cannot see the move.
"""

import csv
import importlib.util
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "tools" / "autonomous" / "rank_history.py"
)
spec = importlib.util.spec_from_file_location("rank_history", MODULE_PATH)
rh = importlib.util.module_from_spec(spec)
sys.modules["rank_history"] = rh
spec.loader.exec_module(rh)

STAMP = "2026-08-13T02:01:00Z"


def apple_row(term="fruit tree tracker", **kw):
    row = {
        "group": "niche_tracker",
        "term": term,
        "country": "AU",
        "result_count": 158,
        "rank": 7,
        "name_match_top5": 0.2,
        "top3": [
            {"name": "Fruit Tree Tracker - Grove", "ratings": 0},
            {"name": "FruitForest: Orchard Mapping", "ratings": 0},
            {"name": "Fruit Juice Farm", "ratings": 183},
        ],
    }
    row.update(kw)
    return row


def play_row(term="fruit tree tracker", **kw):
    row = {
        "group": "niche_tracker",
        "term": term,
        "country": "AU",
        "result_count": 30,
        "truncated": True,
        "rank": 26,
        "top3": [
            "com.zht.fruit_trees",
            "org.greenstand.android.TreeTracker",
            "com.PlayMore.FruitTree",
        ],
    }
    row.update(kw)
    return row


class TempCSV:
    """A path in a temp dir, so append() gets to exercise its create branch."""

    def __enter__(self):
        self._dir = tempfile.TemporaryDirectory()
        return os.path.join(self._dir.name, "series.csv")

    def __exit__(self, *exc):
        self._dir.cleanup()
        return False


class TestStatusDerivation(unittest.TestCase):
    def test_ranked(self):
        rec = rh.to_records("appstore", {"AU": [apple_row()]}, STAMP)[0]
        self.assertEqual(rec["status"], rh.RANKED)
        self.assertEqual(rec["rank"], 7)

    def test_proven_absence_on_apple(self):
        # 174 < LIMIT 200: Apple ran out of results, so absence is a finding.
        rec = rh.to_records(
            "appstore", {"AU": [apple_row(rank=None, result_count=174)]}, STAMP
        )[0]
        self.assertEqual(rec["status"], rh.ABSENT)
        self.assertIs(rec["truncated"], False)

    def test_capped_window_on_apple_is_not_proven_absence(self):
        # Never observed (iOS counts run 37-193), and derived anyway so that a
        # future capped window cannot read as proof of absence.
        rec = rh.to_records(
            "appstore", {"AU": [apple_row(rank=None, result_count=rh.LIMIT)]}, STAMP
        )[0]
        self.assertEqual(rec["status"], rh.ABSENT_CAPPED)
        self.assertIs(rec["truncated"], True)

    def test_play_absence_in_a_full_window_is_not_proven(self):
        rec = rh.to_records("play", {"AU": [play_row(rank=None)]}, STAMP)[0]
        self.assertEqual(rec["status"], rh.ABSENT_CAPPED)

    def test_play_absence_below_the_window_is_proven(self):
        rec = rh.to_records(
            "play", {"AU": [play_row(rank=None, result_count=12, truncated=False)]},
            STAMP,
        )[0]
        self.assertEqual(rec["status"], rh.ABSENT)

    def test_play_truncation_uses_saturated_not_equality(self):
        # Real AU data carries result_count 50 still flagged truncated, because
        # saturated() is >= WINDOW. Re-deriving it as == would call this proven.
        rec = rh.to_records(
            "play", {"AU": [play_row(rank=None, result_count=50)]}, STAMP
        )[0]
        self.assertEqual(rec["status"], rh.ABSENT_CAPPED)

    def test_the_two_absences_are_never_equal(self):
        self.assertNotEqual(rh.ABSENT, rh.ABSENT_CAPPED)

    def test_error_measures_nothing_and_says_so(self):
        rec = rh.to_records(
            "play",
            {"AU": [{"group": "brand", "term": "treesmith", "country": "AU",
                     "error": "TimeoutError: upstream timed out"}]},
            STAMP,
        )[0]
        self.assertEqual(rec["status"], rh.ERROR)
        # The decisive assertion: an error carries no measurement at all. A 0 or
        # a False here would be a fact we never established.
        self.assertIsNone(rec["rank"])
        self.assertIsNone(rec["result_count"])
        self.assertIsNone(rec["truncated"])
        self.assertIn("Timeout", rec["error"])

    def test_error_and_absent_do_not_look_alike(self):
        err = rh.to_records(
            "play",
            {"AU": [{"group": "brand", "term": "t", "country": "AU", "error": "boom"}]},
            STAMP,
        )[0]
        absent = rh.to_records(
            "play", {"AU": [play_row(term="t", rank=None, result_count=12)]}, STAMP
        )[0]
        self.assertNotEqual(err["status"], absent["status"])
        # And the difference survives the thing that would blur it: result_count
        # is a number for one and nothing at all for the other.
        self.assertIsNone(err["result_count"])
        self.assertEqual(absent["result_count"], 12)

    def test_unknown_store_is_refused(self):
        # Truncation semantics differ per store, so a typo'd store name would
        # silently derive Apple's rule over Play data.
        with self.assertRaises(ValueError):
            rh.to_records("googleplay", {"AU": [play_row()]}, STAMP)


class TestTop3(unittest.TestCase):
    def test_apple_dicts_flatten_to_names(self):
        rec = rh.to_records("appstore", {"AU": [apple_row()]}, STAMP)[0]
        self.assertEqual(rec["top3_1"], "Fruit Tree Tracker - Grove")
        self.assertEqual(rec["top3_3"], "Fruit Juice Farm")

    def test_play_strings_flatten_to_packages(self):
        rec = rh.to_records("play", {"AU": [play_row()]}, STAMP)[0]
        self.assertEqual(rec["top3_1"], "com.zht.fruit_trees")

    def test_short_result_sets_pad_rather_than_shift(self):
        rec = rh.to_records(
            "play", {"AU": [play_row(top3=["only.one"], result_count=1)]}, STAMP
        )[0]
        self.assertEqual(rec["top3_1"], "only.one")
        self.assertEqual(rec["top3_2"], "")
        self.assertEqual(rec["top3_3"], "")


class TestRoundTrip(unittest.TestCase):
    def test_all_four_statuses_survive_write_then_read(self):
        rows = [
            play_row(term="fruit tree tracker"),                       # ranked
            play_row(term="orchard tracker", rank=None, result_count=12,
                     truncated=False),                                 # absent
            play_row(term="tree tracker", rank=None),                  # capped
            {"group": "brand", "term": "treesmith", "country": "AU",
             "error": "TimeoutError: upstream timed out"},             # error
        ]
        records = rh.to_records("play", {"AU": rows}, STAMP)
        with TempCSV() as path:
            rh.append(path, records)
            back = rh.read(path)
        # to_records and read return the same typed shape, so this is equality
        # rather than a comparison of two conversions.
        self.assertEqual(back, records)
        self.assertEqual(
            sorted(r["status"] for r in back),
            sorted([rh.ABSENT, rh.ABSENT_CAPPED, rh.ERROR, rh.RANKED]),
        )

    def test_apple_name_match_survives_as_a_float(self):
        records = rh.to_records("appstore", {"AU": [apple_row()]}, STAMP)
        with TempCSV() as path:
            rh.append(path, records)
            back = rh.read(path)
        self.assertAlmostEqual(back[0]["name_match_top5"], 0.2)

    def test_play_has_no_name_match_and_that_is_not_zero(self):
        records = rh.to_records("play", {"AU": [play_row()]}, STAMP)
        with TempCSV() as path:
            rh.append(path, records)
            back = rh.read(path)
        self.assertIsNone(back[0]["name_match_top5"])


class TestAppendOnly(unittest.TestCase):
    def test_header_is_written_once(self):
        with TempCSV() as path:
            rh.append(path, rh.to_records("play", {"AU": [play_row()]}, STAMP))
            rh.append(path, rh.to_records(
                "play", {"AU": [play_row()]}, "2026-08-20T02:00:00Z"))
            lines = Path(path).read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], ",".join(rh.CSV_COLUMNS))
        self.assertEqual(sum(1 for l in lines if l.startswith("captured_at,")), 1)

    def test_earlier_rows_are_never_rewritten(self):
        with TempCSV() as path:
            rh.append(path, rh.to_records("play", {"AU": [play_row()]}, STAMP))
            first = Path(path).read_text(encoding="utf-8")
            rh.append(path, rh.to_records(
                "appstore", {"AU": [apple_row()]}, "2026-08-20T02:00:00Z"))
            after = Path(path).read_text(encoding="utf-8")
        self.assertTrue(after.startswith(first))

    def test_missing_series_reads_as_empty_not_an_error(self):
        with TempCSV() as path:
            self.assertEqual(rh.read(path), [])

    def test_a_changed_header_is_refused(self):
        # The header is a contract with the published artefact and the admin
        # worker that fetches it. Silently mapping a renamed column would put
        # wrong numbers in the digest.
        with TempCSV() as path:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["captured_at", "store", "rank"])
                w.writerow([STAMP, "play", "1"])
            with self.assertRaises(ValueError):
                rh.read(path)


class TestCapturedAt(unittest.TestCase):
    def test_canonical_form_is_stable(self):
        self.assertEqual(rh.normalise_captured_at(STAMP), STAMP)

    def test_offsets_are_converted_to_utc(self):
        # A local-time stamp from the wrapper must not create a second capture
        # group an hour away from the one it belongs to.
        self.assertEqual(
            rh.normalise_captured_at("2026-08-13T10:01:00+08:00"), STAMP
        )

    def test_junk_is_refused_rather_than_written(self):
        with self.assertRaises(ValueError):
            rh.normalise_captured_at("last tuesday")

    def test_same_store_same_date_different_time_stays_two_captures(self):
        # The Play baseline and the Play day-0 capture are the same store, same
        # date, same 36 terms. A date-only key would let day 0 overwrite the
        # baseline and destroy the most informative pair in the dataset.
        baseline = rh.to_records("play", {"AU": [play_row()]}, "2026-08-13T01:56:00Z")
        day0 = rh.to_records("play", {"AU": [play_row(rank=1)]}, "2026-08-13T02:55:00Z")
        with TempCSV() as path:
            rh.append(path, baseline)
            rh.append(path, day0)
            self.assertEqual(len(rh.captures(rh.read(path), "play")), 2)


class TestCaptures(unittest.TestCase):
    def test_newest_first_and_per_store(self):
        records = (
            rh.to_records("play", {"AU": [play_row()]}, "2026-08-13T01:56:00Z")
            + rh.to_records("appstore", {"AU": [apple_row()]}, "2026-08-13T02:01:00Z")
            + rh.to_records("play", {"AU": [play_row()]}, "2026-08-13T02:55:00Z")
        )
        self.assertEqual(
            rh.captures(records, "play"),
            ["2026-08-13T02:55:00Z", "2026-08-13T01:56:00Z"],
        )
        self.assertEqual(rh.captures(records, "appstore"), ["2026-08-13T02:01:00Z"])


class TestBackfill(unittest.TestCase):
    def test_the_three_pre_series_captures_land_once(self):
        with TempCSV() as path:
            first = rh.backfill(path, write=True)
            self.assertEqual(len(first), 216)  # 3 captures x 2 countries x 36 terms
            again = rh.backfill(path, write=True)
            self.assertEqual(again, [])
            self.assertEqual(len(rh.read(path)), 216)

    def test_dry_run_writes_nothing(self):
        with TempCSV() as path:
            pending = rh.backfill(path, write=False)
            self.assertEqual(len(pending), 216)
            self.assertFalse(os.path.exists(path))

    def test_the_known_pre_rename_facts_are_in_the_series(self):
        # Sanity-checks the timestamp map as well as the parse: if day 0 were
        # keyed by date it would have overwritten the baseline and both of these
        # would read 1.
        with TempCSV() as path:
            rh.backfill(path, write=True)
            records = rh.read(path)
        by_key = {(r["captured_at"], r["store"], r["country"], r["term"]): r
                  for r in records}
        self.assertEqual(
            by_key[("2026-08-13T01:56:00Z", "play", "AU", "fruit tree tracker")]["rank"],
            26,
        )
        self.assertEqual(
            by_key[("2026-08-13T02:55:00Z", "play", "AU", "fruit tree tracker")]["rank"],
            1,
        )
        self.assertEqual(
            by_key[("2026-08-13T02:01:00Z", "appstore", "AU", "graft tracker")]["rank"],
            1,
        )


class TestSharedTermSet(unittest.TestCase):
    """The same anti-fork guard the two readers carry, extended to this module.

    A forked term list here would silently stop the series being comparable to
    the readers that fill it.
    """

    def test_the_series_never_defines_its_own_term_set(self):
        src = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIsNone(
            re.search(r"^TERMS\s*[:=]", src, re.MULTILINE),
            "rank_history.py defines TERMS itself; import it from appstore_rank",
        )
        self.assertIsNotNone(
            re.search(r"^from appstore_rank import .*\bTERMS\b", src, re.MULTILINE),
            "rank_history.py must import TERMS from appstore_rank",
        )

    def test_play_truncation_is_imported_not_re_derived(self):
        src = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIsNotNone(
            re.search(r"^from playstore_rank import .*\bsaturated\b", src, re.MULTILINE),
            "rank_history.py must import saturated() rather than restate >= WINDOW",
        )


if __name__ == "__main__":
    unittest.main()
