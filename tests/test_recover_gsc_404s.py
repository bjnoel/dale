"""Recovering redirects from a Search Console 404 export.

The cohort this covers died before the page ledger existed, so `recover_merged_slugs.py`
structurally cannot see it: that tool diffs two builds off nursery snapshots, and no
build we can still reach generates these slugs. Google's crawl history does.

Measured on the 2026-08-20 export (the 1,000 most recently crawled of 3,447): 928
unique dead `/variety/` URLs, of which 782 are correct 404s with no live page to
point at, and 146 have one. The tests below are about which of those 146 a machine
may act on by itself.
"""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "scrapers"))

import recover_gsc_404s as rec


LIVE = {
    "loquat-champagne", "apple-granny-smith", "apricot-moorpark",
    "banana-red-dacca", "banana-dwarf-red-dacca",
    "pear-nashi", "pear-nashi-sunshu",
    "apricot-storeys", "mango-bowen",
}


def _export(tmp, paths):
    p = Path(tmp) / "Table.csv"
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["URL", "Last crawled"])
        for path in paths:
            w.writerow([f"https://treestock.com.au{path}", "2026-08-18"])
    return p


class ClassificationTests(unittest.TestCase):
    """Which side of the line each dead URL falls on."""

    def classify(self, slugs, live=None, ledger=None):
        rows = [{"path": f"/variety/{s}.html", "crawled": "2026-08-18"}
                for s in slugs]
        return rec.classify(rows, set(live or LIVE), ledger or {},
                            Path("/nonexistent"))

    def test_a_pot_size_tail_is_recoverable(self):
        """`loquat-champagne-5l` and `loquat-champagne` are one plant and two
        URLs, and the one Google holds is the dead one. This is the whole
        reason the tool exists."""
        out = self.classify(["loquat-champagne-5l"])
        self.assertEqual([(e["slug"], e["target"]) for e in out["recoverable"]],
                         [("loquat-champagne-5l", "loquat-champagne")])

    def test_a_typo_for_bare_rooted_is_still_noise(self):
        """`apple-granny-smith-bear-rooted` is a real live slug from a real
        listing. A vocabulary that only knows the correct spelling leaves the
        typo 404ing forever."""
        out = self.classify(["apple-granny-smith-bear-rooted"])
        self.assertEqual(len(out["recoverable"]), 1)

    def test_a_cultivar_in_the_tail_needs_a_human(self):
        """"Early Moorpark" is its own apricot, not a size. The prefix match is
        real and the target page exists, and it is still the wrong answer."""
        out = self.classify(["apricot-storeys-early-moorpark"])
        self.assertEqual(out["recoverable"], [])
        self.assertIn("early", out["needs_human"][0]["why"])

    def test_a_longer_live_page_beats_the_prefix(self):
        """`pear-nashi-tropical-sunshu` prefix-matches the generic `pear-nashi`,
        which is live, so the naive answer folds a named cultivar onto an index
        page. `pear-nashi-sunshu` is live too and is obviously the real
        successor. The tool can see the better target exists without being able
        to prove it, so it reports rather than proposes."""
        out = self.classify(["pear-nashi-tropical-sunshu"])
        self.assertEqual(out["recoverable"], [])
        self.assertIn("pear-nashi-sunshu", out["needs_human"][0]["why"])

    def test_dwarf_is_noise_when_no_dwarf_page_exists(self):
        """The site's own vocabulary calls dwarf listing noise for every species
        but banana, and `apricot-moorpark-dwarf` has no dwarf sibling to be
        confused with. Refusing it here would leave the URL dead over a
        distinction the rest of the site does not draw."""
        out = self.classify(["apricot-moorpark-dwarf"])
        self.assertEqual(len(out["recoverable"]), 1)

    def test_dwarf_is_ambiguous_when_a_dwarf_page_exists(self):
        """`banana-red-dacca-dwarf-90mm-qld-only` sits between a live
        `banana-red-dacca` and a live `banana-dwarf-red-dacca`. Every token in
        the tail is noise by the vocabulary, so the pure-noise test passes it,
        and the shorter prefix would still file a dwarf plant under the standard
        one. Banana is also the one species whose dwarf IS a cultivar name."""
        out = self.classify(["banana-red-dacca-dwarf-90mm-qld-only"])
        self.assertEqual(out["recoverable"], [])
        self.assertIn("banana-dwarf-red-dacca", out["needs_human"][0]["why"])

    def test_no_live_prefix_is_a_correct_404(self):
        """Ornamentals and veg gated out by DEC-195 have no fruit page to
        receive them. 782 of the 928 are this, and a 404 is the honest answer."""
        out = self.classify(["hydrangea-magical-revolution"])
        self.assertEqual(len(out["correct"]), 1)
        self.assertEqual(out["recoverable"], [])

    def test_the_bare_species_is_never_a_target(self):
        """Every variety slug starts with its species, so a one-token prefix
        matches anything. `mango-bowen` is live; a dead `mango-something-odd`
        must not become a redirect to it just because both start with mango."""
        out = self.classify(["mango-unknown-thing"], live=LIVE | {"mango"})
        self.assertEqual(out["recoverable"], [])
        self.assertEqual(len(out["correct"]), 1)

    def test_a_slug_already_in_the_ledger_is_left_alone(self):
        """A redirect or tombstone already serves 200. The export row is stale,
        and re-proposing it would seed the same entry twice."""
        out = self.classify(["loquat-champagne-5l"],
                            ledger={"loquat-champagne-5l": {"state": "redirect"}})
        self.assertEqual(out["recoverable"], [])
        self.assertEqual(len(out["serving"]), 1)


class ExportReadingTests(unittest.TestCase):
    def test_the_two_hostnames_collapse_to_one_row(self):
        """www.treestock.com.au serves the site rather than redirecting to the
        apex, so every dead path arrives twice in these exports (85 of the 1,000
        rows in the 2026-08-20 one). Proposing both would seed the same ledger
        entry twice."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "Table.csv"
            with open(p, "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["URL", "Last crawled"])
                w.writerow(["https://treestock.com.au/variety/x.html", "2026-08-18"])
                w.writerow(["https://www.treestock.com.au/variety/x.html", "2026-08-18"])
            self.assertEqual(len(rec.read_export(p)), 1)


class ProposalTests(unittest.TestCase):
    """The rows have to be readable by `build_variety_pages.seed_reviewed`."""

    ENTRY = {"slug": "loquat-champagne-5l", "target": "loquat-champagne",
             "crawled": "2026-08-18", "tail": "5l"}

    def test_a_proposal_is_inert_until_someone_approves_it(self):
        """`seed_reviewed` applies only rows with `approved is True`, so a
        generated file does nothing on its own. That is the property that makes
        it safe to merge into the file the nightly reads."""
        row = rec.to_proposal(self.ENTRY)
        self.assertNotIn("approved", row)

    def test_the_verdict_is_always_rename(self):
        """Having a live successor is the entire test for getting into this
        list, and `retired` would turn into a tombstone. Asserting a plant is
        gone because Google could not fetch a URL is not something this evidence
        supports."""
        self.assertEqual(rec.to_proposal(self.ENTRY)["verdict"], "rename")

    def test_merging_never_rewrites_an_existing_row(self):
        """An approval already recorded against a slug is a decision, including
        a deliberate refusal. R1's 194 rows live in the same file."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "proposals.json"
            p.write_text(json.dumps({"proposals": [
                {"slug": "loquat-champagne-5l", "verdict": "retired",
                 "approved": False}]}))
            added, skipped = rec.merge_into(p, [rec.to_proposal(self.ENTRY, "x@y", "now")])
            self.assertEqual((added, skipped), (0, 1))
            doc = json.loads(p.read_text())
            self.assertEqual(doc["proposals"][0]["verdict"], "retired")

    def test_merging_adds_a_new_row_and_counts_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "proposals.json"
            p.write_text(json.dumps({"proposals": [], "summary": {"total": 0}}))
            added, _ = rec.merge_into(p, [rec.to_proposal(self.ENTRY, "x@y", "now")])
            doc = json.loads(p.read_text())
            self.assertEqual(added, 1)
            self.assertEqual(doc["summary"]["gsc_recovered"], 1)
            self.assertTrue(doc["proposals"][0]["approved"])


class VocabularyTests(unittest.TestCase):
    def test_the_shared_noise_list_is_imported_not_copied(self):
        """Two lists that disagree is how a redirect gets proposed for a slug
        the rest of the site treats as meaningful. `tests/test_no_forking.py`
        enforces the same rule across the scrapers."""
        from admin_view import NOISE_SLUG_TOKENS
        self.assertIs(rec.NOISE_SLUG_TOKENS, NOISE_SLUG_TOKENS)

    def test_sizes_are_recognised_in_every_shape_the_export_contains(self):
        for token in ("5l", "180mm", "14cm", "165ml", "60", "4l", "250mm"):
            self.assertTrue(rec.is_noise_token(token), token)

    def test_a_cultivar_that_looks_like_a_size_is_not_eaten(self):
        """`ga866` is a jujube selection and `h5` is a sultana one. Both carry
        digits and neither is a pot."""
        for token in ("ga866", "h5", "r2e2"):
            self.assertFalse(rec.is_noise_token(token), token)


if __name__ == "__main__":
    unittest.main()
