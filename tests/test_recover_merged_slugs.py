"""Tests for recover_merged_slugs.py, task R1's proposal builder.

The valuable part of this tool is not that it finds candidates -- prefix
matching finds candidates -- it is that every proposal it will not act on
automatically is separated from the ones it will. So these pin the refusals:
a split is never silently narrowed to its most popular successor, a slug that is
still a live page never gets proposed at all, and a redirect onto something that
is not a page today is flagged rather than emitted.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"

sys.path.insert(0, str(SCRAPERS))

from recover_merged_slugs import (  # noqa: E402
    build_proposals, classify, load_titles, summarise, watch_counts,
)


def group(title, *product_titles):
    """A group_by_cultivar entry: display title plus the products behind it."""
    return {"title": title, "products": [{"title": t} for t in product_titles]}


class ClassifyTest(unittest.TestCase):
    """What became of one dead slug's products under the current parser."""

    def test_one_agreed_successor_is_a_rename(self):
        record = classify(
            ["Apple Akane 5L", "Apple - Akane (bare rooted)"],
            lambda t: "apple-akane")
        self.assertEqual(record["verdict"], "rename")
        self.assertEqual(record["target"], "apple-akane")

    def test_nothing_maps_anywhere_is_retired(self):
        """No successor exists, so a redirect would be a lie about where it went."""
        record = classify(["Grevillea Robyn Gordon"], lambda t: None)
        self.assertEqual(record["verdict"], "retired")
        self.assertIsNone(record["target"])
        self.assertEqual(record["unmapped_titles"], 1)

    def test_two_successors_never_silently_become_one(self):
        """The failure this whole tool exists to avoid.

        Naming one successor for a split discards the others permanently, and a
        crawler believes it. `target` stays None so nothing downstream can treat
        it as applicable without a person having looked.
        """
        record = classify(
            ["Avocado Hass", "Avocado Lamb Hass"],
            lambda t: "avocado-lamb-hass" if "Lamb" in t else "avocado-hass")
        self.assertEqual(record["verdict"], "split")
        self.assertIsNone(record["target"])
        self.assertEqual(record["targets"],
                         {"avocado-hass": 1, "avocado-lamb-hass": 1})

    def test_a_dominant_successor_is_suggested_but_still_not_a_target(self):
        titles = ["Fig Black Genoa"] * 9 + ["Fig Genoa Something Else"]
        record = classify(
            titles,
            lambda t: "fig-something-else" if "Else" in t else "fig-black-genoa")
        self.assertEqual(record["verdict"], "split")
        self.assertEqual(record["suggested"], "fig-black-genoa")
        self.assertIsNone(record["target"], "a suggestion is not an instruction")

    def test_an_even_split_suggests_nothing(self):
        record = classify(
            ["Plum A", "Plum B"],
            lambda t: "plum-a" if t.endswith("A") else "plum-b")
        self.assertIsNone(record["suggested"])

    def test_titles_that_map_nowhere_do_not_block_a_rename(self):
        """A listing that fell out of the taxonomy is not evidence of a split.

        It is evidence of nothing, and counting it as a second successor would
        push a clean rename into the review queue for no reason.
        """
        record = classify(
            ["Cherry Stella", "Cherry Stella Seeds 20 pack"],
            lambda t: None if "Seeds" in t else "cherry-stella")
        self.assertEqual(record["verdict"], "rename")
        self.assertEqual(record["target"], "cherry-stella")
        self.assertEqual(record["unmapped_titles"], 1)


class BuildProposalsTest(unittest.TestCase):

    def _proposals(self, old, new, live, mapping, watchers=None):
        return build_proposals(old, new, set(live),
                               lambda t: mapping.get(t), watchers or {})

    def test_a_slug_that_is_still_a_page_is_not_proposed(self):
        """Whatever the old parser thought, a slug in today's index is live.

        Proposing it would be proposing to redirect a working URL onto itself,
        which is how a recovery task turns into an outage.
        """
        old = {"apple-akane": group("Apple - Akane", "Apple Akane")}
        proposals = self._proposals(
            old, {}, {"apple-akane"}, {"Apple Akane": "apple-akane"})
        self.assertEqual(proposals, [])

    def test_a_slug_the_new_parser_still_generates_is_not_proposed(self):
        old = {"fig-black-genoa": group("Fig - Black Genoa", "Fig Black Genoa")}
        new = {"fig-black-genoa": group("Fig - Black Genoa", "Fig Black Genoa")}
        self.assertEqual(self._proposals(old, new, set(), {}), [])

    def test_a_rename_onto_a_live_page_is_ready(self):
        old = {"apple-akane-5l": group("Apple - Akane 5l", "Apple Akane 5L")}
        new = {"apple-akane": group("Apple - Akane", "Apple Akane 5L")}
        proposals = self._proposals(
            old, new, {"apple-akane"}, {"Apple Akane 5L": "apple-akane"})
        self.assertEqual(len(proposals), 1)
        p = proposals[0]
        self.assertEqual(p["verdict"], "rename")
        self.assertEqual(p["target"], "apple-akane")
        self.assertTrue(p["target_live"])
        self.assertEqual(p["title"], "Apple - Akane 5l",
                         "the stub says what the OLD url was called")
        self.assertEqual(p["target_title"], "Apple - Akane")

    def test_a_successor_that_is_not_a_page_today_is_flagged(self):
        """Swapping a 404 for a 404, and spending the redirect to do it."""
        old = {"pear-nashi-20th": group("Pear - Nashi 20th", "Pear Nashi 20th Century")}
        new = {"pear-nashi-20th-century": group(
            "Pear - Nashi 20th Century", "Pear Nashi 20th Century")}
        proposals = self._proposals(
            old, new, set(), {"Pear Nashi 20th Century": "pear-nashi-20th-century"})
        self.assertEqual(proposals[0]["verdict"], "rename")
        self.assertFalse(proposals[0]["target_live"])
        self.assertEqual(summarise(proposals)["ready_to_apply"], 0)

    def test_watchers_ride_along_with_the_proposal(self):
        """A watch on a dead slug is a person waiting for an email about it.

        It must reach the reviewer on the same row as the mapping, because the
        decision it changes is that mapping's.
        """
        old = {"mango-kp": group("Mango - Kp", "Mango KP")}
        new = {"mango-kensington-pride": group(
            "Mango - Kensington Pride", "Mango KP")}
        proposals = self._proposals(
            old, new, {"mango-kensington-pride"},
            {"Mango KP": "mango-kensington-pride"}, {"mango-kp": 3})
        self.assertEqual(proposals[0]["watchers"], 3)

    def test_proposals_are_ordered_so_two_runs_can_be_diffed(self):
        old = {
            "zzz-late": group("Zzz - Late", "Zzz Late"),
            "aaa-early": group("Aaa - Early", "Aaa Early"),
        }
        proposals = self._proposals(old, {}, set(), {})
        self.assertEqual([p["slug"] for p in proposals], ["aaa-early", "zzz-late"])


class SummariseTest(unittest.TestCase):

    def test_ready_counts_only_renames_onto_a_live_page(self):
        proposals = [
            {"verdict": "rename", "target_live": True, "watchers": 0},
            {"verdict": "rename", "target_live": False, "watchers": 1},
            {"verdict": "split", "target_live": False, "watchers": 0},
            {"verdict": "retired", "target_live": False, "watchers": 0},
        ]
        summary = summarise(proposals)
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["rename"], 2)
        self.assertEqual(summary["ready_to_apply"], 1)
        self.assertEqual(summary["watched"], 1)


class LoadTitlesTest(unittest.TestCase):
    """The dated snapshot, read the way the builder reads tonight's."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _nursery(self, key, day, products):
        d = self.data / key
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{day}.json").write_text(json.dumps(
            {"products": [{"title": t} for t in products]}))

    def test_reads_the_requested_day_not_the_latest(self):
        """Holding the input date fixed is what isolates the parser change.

        Run against a later snapshot, half the difference would be overnight
        stock churn attributed to the parser.
        """
        self._nursery("daleys", "2026-08-16", ["Apple Akane"])
        self._nursery("daleys", "2026-08-17", ["Pear Williams"])
        titles = [p["title"] for p in load_titles(self.data, "2026-08-16")]
        self.assertEqual(titles, ["Apple Akane"])

    def test_non_plant_listings_are_filtered_like_the_builder_does(self):
        self._nursery("daleys", "2026-08-16",
                      ["Apple Akane", "Gift Voucher $50"])
        titles = [p["title"] for p in load_titles(self.data, "2026-08-16")]
        self.assertEqual(titles, ["Apple Akane"])

    def test_a_nursery_with_no_snapshot_for_that_day_is_skipped(self):
        self._nursery("daleys", "2026-08-16", ["Apple Akane"])
        (self.data / "empty-nursery").mkdir()
        self.assertEqual(len(load_titles(self.data, "2026-08-16")), 1)


class WatchCountsTest(unittest.TestCase):

    def test_missing_database_is_no_evidence_rather_than_a_crash(self):
        self.assertEqual(watch_counts(Path("/nonexistent/watches.db")), {})

    def test_counts_watchers_per_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "watches.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE watches (email TEXT, variety_slug TEXT)")
            conn.executemany("INSERT INTO watches VALUES (?, ?)", [
                ("a@example.com", "mango-kp"),
                ("b@example.com", "mango-kp"),
                ("c@example.com", "apple-akane"),
            ])
            conn.commit()
            conn.close()
            self.assertEqual(watch_counts(db),
                             {"mango-kp": 2, "apple-akane": 1})


if __name__ == "__main__":
    unittest.main()
