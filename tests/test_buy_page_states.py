"""
One state list, five builders: the guard that adding a state is a single edit.

Before DAL-297 the four buy-page states were typed out in at least nine places
(six inline list literals in build_species_state_pages, its COMBO_FILE_RE
alternation, an inline slug dict in build_location_pages.build_state_page, a
hardcoded regex in build_sitemap, plus the test fixtures). Adding South
Australia meant finding all of them, and the half that got missed would have
shipped a page set that built but was never swept, tombstoned, cross-linked or
listed in the sitemap.

They now all derive from stocklib.registry.BUY_PAGE_STATE_SLUGS. These tests
fail if a copy comes back, and they fail if a new state is added to that dict
without the per-state copy every builder needs.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from stocklib.registry import BUY_PAGE_STATE_SLUGS  # noqa: E402

EM_DASH = "\u2014"
EN_DASH = "\u2013"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bssp = _load(SCRAPERS / "build_species_state_pages.py")
blp = _load(SCRAPERS / "build_location_pages.py")
bs = _load(SCRAPERS / "build_sitemap.py")

STATES = list(BUY_PAGE_STATE_SLUGS)


class OneStateListTests(unittest.TestCase):
    """Every builder reads the registry, none keeps its own copy."""

    def test_the_builders_share_the_registry_list(self):
        self.assertEqual(bssp.STATE_SLUGS, BUY_PAGE_STATE_SLUGS)
        self.assertEqual(blp.STATE_SLUGS, BUY_PAGE_STATE_SLUGS)
        self.assertEqual(list(bssp.STATES), STATES)
        self.assertEqual(list(blp.STATES), STATES)

    def test_combo_filenames_are_recognised_for_every_state(self):
        # This regex decides which files in the output dir the combo sweeper owns.
        # A state missing from it produces pages that are built and never retired.
        for st, slug in BUY_PAGE_STATE_SLUGS.items():
            self.assertRegex(f"buy-avocado-trees-{slug}.html",
                             bssp.COMBO_FILE_RE, st)

    def test_the_combo_sweeper_ignores_the_landing_pages(self):
        for st in STATES:
            self.assertNotRegex(f"buy-fruit-trees-{st.lower()}.html",
                                bssp.COMBO_FILE_RE, st)

    def test_the_sitemap_lists_and_recognises_every_state_landing_page(self):
        listed = {name for name, _, _ in bs.STATE_LANDING_PAGES}
        for st in STATES:
            page = f"buy-fruit-trees-{st.lower()}.html"
            self.assertIn(page, listed, f"{st} landing page missing from the sitemap")
            self.assertRegex(page, bs.LOCATION_PAGE_PATTERN, st)


class EveryStateHasItsCopyTests(unittest.TestCase):
    """A state in the registry with no copy written renders an empty section.

    Nothing crashes, which is the problem: it ships.
    """

    COPY = ("STATE_NAMES", "STATE_INTROS", "STATE_INFO_BOX", "STATE_GROWING_GUIDE")

    def test_location_page_copy_covers_every_state(self):
        for name in self.COPY:
            block = getattr(blp, name)
            for st in STATES:
                self.assertIn(st, block, f"{name} has no entry for {st}")
                # STATE_GROWING_GUIDE["WA"] is a deliberate None: WA's differentiated
                # content is the quarantine section, which no other state gets. Every
                # other entry must carry copy.
                if not (name == "STATE_GROWING_GUIDE" and st == "WA"):
                    self.assertTrue((block[st] or "").strip(),
                                    f"{name}[{st}] is empty")

    def test_full_state_names_cover_every_state(self):
        for st in STATES:
            self.assertIn(st, bssp.STATE_FULL_NAMES, st)

    def test_climate_notes_cover_every_state_and_the_same_categories(self):
        # Every combo page picks one note by the species' climate category. A state
        # short of a category falls through to a note written for somewhere else.
        categories = set(bssp.STATE_CLIMATE_NOTES["WA"])
        for st in STATES:
            self.assertIn(st, bssp.STATE_CLIMATE_NOTES, st)
            self.assertEqual(set(bssp.STATE_CLIMATE_NOTES[st]), categories,
                             f"{st} climate notes do not cover the same categories as WA")

    def test_cross_links_reach_every_other_state(self):
        # Derived, not typed: a new state that nothing links to is invisible.
        for st in STATES:
            linked = {other for other, _ in blp.CROSS_LINKS[st]}
            self.assertEqual(linked, set(STATES) - {st}, st)

    def test_no_em_or_en_dashes_in_any_state_copy(self):
        blocks = [getattr(blp, n) for n in self.COPY]
        blocks.append({st: " ".join(bssp.STATE_CLIMATE_NOTES[st].values())
                       for st in STATES})
        for block in blocks:
            for st in STATES:
                self.assertNotIn(EM_DASH, block[st] or "", st)
                self.assertNotIn(EN_DASH, block[st] or "", st)


if __name__ == "__main__":
    unittest.main()
