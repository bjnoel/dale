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

    def test_a_comma_inside_an_app_name_survives(self):
        # "Journey - Diary, Journal" is really in our iOS top 3, so the file
        # genuinely contains quoted cells. Anything reading this artefact needs
        # a real CSV parser; a naive line.split(",") shifts every column after
        # the name and silently reads a competitor as a rank.
        records = rh.to_records(
            "appstore",
            {"AU": [apple_row(top3=[{"name": "Journey - Diary, Journal",
                                     "ratings": 12},
                                    {"name": 'He said "hi"', "ratings": 0}])]},
            STAMP,
        )
        with TempCSV() as path:
            rh.append(path, records)
            raw = Path(path).read_text(encoding="utf-8")
            back = rh.read(path)
        self.assertEqual(back[0]["top3_1"], "Journey - Diary, Journal")
        self.assertEqual(back[0]["top3_2"], 'He said "hi"')
        self.assertIn('"Journey - Diary, Journal"', raw)

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


class TestAttribution(unittest.TestCase):
    """Whether a rival took the slot, or we simply left it.

    Two different business facts, and the whole reason the top3 columns exist.
    Built from the real iOS AU `graft tracker` capture: we fell 1 -> 11 and the
    apps that arrived were a reading tracker and a peptide tracker. Nobody beat
    us; we stopped matching the term and Apple's graft/craft fuzzy match filled
    the hole. On the same capture AU `fruit tree care` fell 81 -> 125 and the
    arrival was Fruit Tree Tracker - Grove, which is a rival (DEC-237).
    """

    US_AND_TWO = ["TreeSmith: Plant Graft Tracker",
                  "Peptide Tracker - PeptideKit",
                  "Blood Sugar Tracker-AI Health"]

    def _rec(self, top3, **kw):
        rec = dict(
            captured_at=STAMP, store="appstore", country="AU",
            group="niche_tracker", term="graft tracker", rank=1,
            result_count=184, truncated=False, status=rh.RANKED,
            name_match_top5=0.2, error="",
            top3_1=top3[0] if len(top3) > 0 else "",
            top3_2=top3[1] if len(top3) > 1 else "",
            top3_3=top3[2] if len(top3) > 2 else "",
        )
        rec.update(kw)
        return rec

    def test_the_real_graft_tracker_fall_is_vacated_not_displaced(self):
        # Verbatim from the 2026-08-20 capture. A positional rule calls this a
        # displacement, because dropping out of a 3-slot window always lets
        # something backfill slot 3.
        prev = self._rec(self.US_AND_TWO)
        curr = self._rec(["StoryGraph: Reading Tracker",
                          "Peptide Tracker - PeptideKit",
                          "Peptide Tracker Log & Reminder"])
        kind, names = rh.attribute(prev, curr)
        self.assertEqual(kind, rh.VACATED)
        # Named, not blamed: an arrival is still evidence.
        self.assertIn("StoryGraph: Reading Tracker", names)

    def test_a_tracked_rival_arriving_is_a_displacement(self):
        prev = self._rec(self.US_AND_TWO)
        curr = self._rec(["Peptide Tracker - PeptideKit",
                          "Blood Sugar Tracker-AI Health",
                          "Fruit Tree Tracker - Grove"])
        kind, names = rh.attribute(prev, curr)
        self.assertEqual(kind, rh.DISPLACED)
        self.assertEqual(names, ["Fruit Tree Tracker - Grove"])

    def test_the_two_readings_never_render_alike(self):
        prev = self._rec(self.US_AND_TWO)
        backfill = self._rec(["Peptide Tracker - PeptideKit",
                              "Blood Sugar Tracker-AI Health",
                              "StoryGraph: Reading Tracker"])
        rival = self._rec(["Peptide Tracker - PeptideKit",
                           "Blood Sugar Tracker-AI Health",
                           "Fruit Tree Tracker - Grove"])
        item = {"country": "AU", "term": "graft tracker", "prev_rank": 1,
                "curr_rank": 11, "delta": 10, "absence_proven": None}
        a = dict(item); a["attribution"], a["attributed_to"] = rh.attribute(prev, backfill)
        b = dict(item); b["attribution"], b["attributed_to"] = rh.attribute(prev, rival)
        self.assertNotEqual(rh.describe(a), rh.describe(b))
        self.assertIn("vacated", rh.describe(a))
        self.assertIn("displaced by Fruit Tree Tracker - Grove", rh.describe(b))

    def test_an_untracked_arrival_is_still_named(self):
        # The list of rivals will go stale. It must never hide who showed up.
        prev = self._rec(self.US_AND_TWO)
        curr = self._rec(["Peptide Tracker - PeptideKit",
                          "Blood Sugar Tracker-AI Health",
                          "Some Brand New Orchard App"])
        item = {"country": "AU", "term": "graft tracker", "prev_rank": 1,
                "curr_rank": 11, "delta": 10, "absence_proven": None}
        item["attribution"], item["attributed_to"] = rh.attribute(prev, curr)
        self.assertIn("Some Brand New Orchard App", rh.describe(item))

    def test_nothing_arriving_at_all_says_nobody_took_the_slot(self):
        prev = self._rec(self.US_AND_TWO)
        curr = self._rec(["Peptide Tracker - PeptideKit",
                          "Blood Sugar Tracker-AI Health"])
        kind, names = rh.attribute(prev, curr)
        self.assertEqual(kind, rh.VACATED)
        self.assertEqual(names, [])

    def test_no_survivor_is_a_turned_over_result_set(self):
        prev = self._rec(self.US_AND_TWO)
        curr = self._rec(["Totally Other A", "Totally Other B", "Totally Other C"])
        kind, _ = rh.attribute(prev, curr)
        self.assertEqual(kind, rh.TURNED_OVER)

    def test_our_own_rename_is_not_a_competitor(self):
        # Apple's top3 identifier is the app NAME, the name is the thing that
        # just changed, and our new name literally contains the fragment that
        # identifies Grove. Without both guards we displace ourselves.
        self.assertFalse(rh.is_competitor("TreeSmith: Fruit Tree Tracker"))
        prev = self._rec(self.US_AND_TWO)
        curr = self._rec(["TreeSmith: Fruit Tree Tracker",
                          "Peptide Tracker - PeptideKit",
                          "Blood Sugar Tracker-AI Health"])
        kind, names = rh.attribute(prev, curr)
        self.assertEqual(kind, rh.VACATED)
        self.assertEqual(names, [])

    def test_the_tracked_rivals_are_the_ones_dec_237_names(self):
        for rival in ("Fruit Tree Tracker - Grove", "FruitForest: Orchard Mapping",
                      "Trees Diary", "Rootstock: Seed & Plant Log"):
            self.assertTrue(rh.is_competitor(rival), rival)
        for bystander in ("StoryGraph: Reading Tracker", "Peptide Tracker - PeptideKit",
                          "Kawaii World - Craft and Build", "Blossom - Plant Care Guide"):
            self.assertFalse(rh.is_competitor(bystander), bystander)

    def test_our_play_package_is_recognised_as_us(self):
        self.assertTrue(rh.is_ours(rh.OUR_PACKAGE))
        self.assertTrue(rh.is_ours("TreeSmith: Plant Graft Tracker"))
        self.assertFalse(rh.is_ours("Fruit Tree Tracker - Grove"))


class TestDiffBuckets(unittest.TestCase):
    def _capture(self, stamp, rows, store="play"):
        return rh.to_records(store, {"AU": rows}, stamp)

    def _diff(self, before, after, **kw):
        return rh.diff_captures(
            self._capture(STAMP, before),
            self._capture("2026-08-20T02:00:00Z", after),
            **kw,
        )

    def test_drift_inside_the_band_is_flat(self):
        # Two runs 20 minutes apart already disagreed by one position.
        out = self._diff([play_row(rank=7)], [play_row(rank=10)])
        self.assertEqual(out["flat_n"], 1)
        self.assertEqual(out["moved"], [])

    def test_one_position_past_the_band_is_a_move(self):
        out = self._diff([play_row(rank=7)], [play_row(rank=11)])
        self.assertEqual(out["flat_n"], 0)
        self.assertEqual(len(out["moved"]), 1)
        self.assertEqual(out["moved"][0]["delta"], 4)

    def test_delta_is_positive_when_the_position_gets_worse(self):
        out = self._diff([play_row(rank=1)], [play_row(rank=11)])
        self.assertEqual(out["moved"][0]["delta"], 10)
        self.assertIn("down 10", rh.describe(out["moved"][0]))

    def test_entering_from_a_proven_absence_says_so(self):
        out = self._diff(
            [play_row(rank=None, result_count=12, truncated=False)],
            [play_row(rank=36)],
        )
        self.assertEqual(len(out["entered"]), 1)
        self.assertTrue(out["entered"][0]["absence_proven"])
        self.assertIn("entered at 36 from absent", rh.describe(out["entered"][0]))

    def test_entering_from_a_capped_window_never_claims_proof(self):
        # Identical arrow, different finding: we may have been at 31 all along.
        # Collapsing this into "newly entered" is precisely the DEC-255 error.
        out = self._diff([play_row(rank=None)], [play_row(rank=1)])
        self.assertFalse(out["entered"][0]["absence_proven"])
        self.assertIn("never proven", rh.describe(out["entered"][0]))

    def test_the_two_entry_kinds_do_not_render_alike(self):
        proven = self._diff(
            [play_row(rank=None, result_count=12, truncated=False)],
            [play_row(rank=1)])["entered"][0]
        capped = self._diff([play_row(rank=None)], [play_row(rank=1)])["entered"][0]
        self.assertNotEqual(rh.describe(proven), rh.describe(capped))

    def test_a_drop_is_listed_however_small(self):
        # Crossing the ranked/absent boundary is an event, not drift, so the
        # noise band must not swallow it.
        out = self._diff([play_row(rank=29)], [play_row(rank=None)])
        self.assertEqual(len(out["dropped"]), 1)
        self.assertEqual(out["flat_n"], 0)

    def test_absent_both_times_is_counted_not_reported_as_movement(self):
        out = self._diff([play_row(rank=None)], [play_row(rank=None)])
        self.assertEqual(out["still_absent_n"], 1)
        self.assertEqual(out["dropped"], [])
        self.assertEqual(out["entered"], [])

    def test_an_error_on_either_side_is_never_movement(self):
        # DEC-249: a term that failed to fetch has not moved. Folding it into
        # `dropped` would invent a loss out of a timeout.
        boom = {"group": "brand", "term": "fruit tree tracker", "country": "AU",
                "error": "TimeoutError: upstream timed out"}
        out = self._diff([play_row(rank=7)], [boom])
        self.assertEqual(out["dropped"], [])
        self.assertEqual(out["moved"], [])
        self.assertEqual(len(out["unmeasured"]), 1)
        self.assertIn("error", out["unmeasured"][0]["reason"])

    def test_a_regrouped_term_is_not_a_drop_and_an_entry(self):
        # The group is our own label in TERMS, not a store fact. Moving a term
        # between groups must not read as it falling off the store.
        out = self._diff(
            [play_row(rank=7, group="niche_tracker")],
            [play_row(rank=7, group="subject")],
        )
        self.assertEqual(out["dropped"], [])
        self.assertEqual(out["entered"], [])
        self.assertEqual(out["unmeasured"], [])
        self.assertEqual(out["flat_n"], 1)

    def test_a_term_missing_from_one_capture_is_unmeasured_not_dropped(self):
        # A partial re-run (--term) must not read as 35 apps falling off Play.
        out = self._diff(
            [play_row(term="fruit tree tracker", rank=7),
             play_row(term="orchard tracker", rank=9)],
            [play_row(term="fruit tree tracker", rank=7)],
        )
        self.assertEqual(out["dropped"], [])
        self.assertEqual(len(out["unmeasured"]), 1)
        self.assertEqual(out["unmeasured"][0]["term"], "orchard tracker")

    def test_buckets_and_counts_account_for_every_term(self):
        before = [play_row(term=t, rank=r) for t, r in
                  [("fruit tree tracker", 7), ("orchard tracker", 9),
                   ("tree tracker", None), ("graft tracker", 1)]]
        after = [play_row(term=t, rank=r) for t, r in
                 [("fruit tree tracker", 7), ("orchard tracker", 29),
                  ("tree tracker", None), ("graft tracker", None)]]
        out = self._diff(before, after)
        total = (len(out["moved"]) + len(out["entered"]) + len(out["dropped"])
                 + out["flat_n"] + out["still_absent_n"] + len(out["unmeasured"]))
        self.assertEqual(total, 4)

    def test_losing_the_top_slot_outranks_a_bigger_shuffle_further_down(self):
        # Both are real rows from the 2026-08-20 iOS capture. Sorting on raw
        # places put the 55-place shuffle in the digest's top five and pushed
        # losing the #1 slot below the fold.
        before = [play_row(term="graft tracker", rank=1),
                  play_row(term="harvest tracker", rank=117)]
        after = [play_row(term="graft tracker", rank=11),
                 play_row(term="harvest tracker", rank=62)]
        out = self._diff(before, after)
        self.assertEqual(out["moved"][0]["term"], "graft tracker")
        self.assertGreater(abs(out["moved"][1]["delta"]),
                           abs(out["moved"][0]["delta"]))

    def test_equal_ratios_fall_back_to_the_bigger_move(self):
        before = [play_row(term="graft tracker", rank=1),
                  play_row(term="orchard tracker", rank=10)]
        after = [play_row(term="graft tracker", rank=5),
                 play_row(term="orchard tracker", rank=50)]
        out = self._diff(before, after)
        self.assertEqual(out["moved"][0]["term"], "orchard tracker")

    def test_a_downward_move_carries_attribution(self):
        out = self._diff([play_row(rank=1)], [play_row(rank=11)])
        self.assertIsNotNone(out["moved"][0]["attribution"])

    def test_an_upward_move_does_not_pretend_to_explain_itself(self):
        out = self._diff([play_row(rank=11)], [play_row(rank=1)])
        self.assertIsNone(out["moved"][0]["attribution"])


class TestCaptureSelectionIsPerStore(unittest.TestCase):
    """iOS and Play were baselined 5 minutes apart and Play has a third capture.

    A global "last two" would compare Apple against Play and report the
    difference between two shops as a week of movement.
    """

    def test_play_compares_against_the_play_baseline_not_the_apple_one(self):
        with TempCSV() as path:
            rh.backfill(path, write=True)
            records = rh.read(path)
        out = rh.diff(records, "play")
        self.assertEqual(out["prev"], "2026-08-13T01:56:00Z")
        self.assertEqual(out["curr"], "2026-08-13T02:55:00Z")
        # The Apple baseline sits between the two in wall-clock order.
        self.assertLess(out["prev"], "2026-08-13T02:01:00Z")
        self.assertGreater(out["curr"], "2026-08-13T02:01:00Z")

    def test_a_store_with_one_capture_reports_nothing_rather_than_guessing(self):
        with TempCSV() as path:
            rh.backfill(path, write=True)
            out = rh.diff(rh.read(path), "appstore")
        self.assertIsNone(out["prev"])
        self.assertEqual(out["moved"], [])
        self.assertIn("nothing to compare", rh.render_diff(out))

    def test_the_recorded_dal_257_predictions_are_reproduced(self):
        # DAL-257 recorded these before the rename so they could not be moved
        # afterwards: Play AU "fruit tree tracker" improves from #26/30, and
        # Play US improves from absent-in-30.
        with TempCSV() as path:
            rh.backfill(path, write=True)
            out = rh.diff(rh.read(path), "play")
        moved = {(i["country"], i["term"]): i for i in out["moved"]}
        entered = {(i["country"], i["term"]): i for i in out["entered"]}
        au = moved[("AU", "fruit tree tracker")]
        self.assertEqual((au["prev_rank"], au["curr_rank"]), (26, 1))
        us = entered[("US", "fruit tree tracker")]
        self.assertEqual(us["curr_rank"], 1)
        self.assertFalse(us["absence_proven"])  # it was a capped window

    def test_an_unknown_against_stamp_is_refused(self):
        with TempCSV() as path:
            rh.backfill(path, write=True)
            with self.assertRaises(ValueError):
                rh.diff(rh.read(path), "play", against="2026-01-01T00:00:00Z")


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
