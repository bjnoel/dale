"""
Tests for server-owned variety titles (stocklib/variety_index.py).

`POST /api/watch-variety` took a `variety_title` from the caller, stored it,
and `send_variety_alerts.py` then interpolated the FIRST watcher's copy of that
string into the subject line and HTML body of mail sent to every OTHER watcher
of the same slug. With an endpoint that accepts any valid-looking email and no
authentication, that is a stranger choosing the copy in mail we send to real
people.

These pin the replacement:

  * the builder emits a canonical {slug: title} map, grandfathered slugs
    included, because those slugs have live watchers even though they are kept
    out of the browsable index;
  * the map is written atomically, because the server reads it while the
    nightly build rewrites it;
  * the reader notices a rebuild (mtime cache) without re-reading per lookup,
    and treats a missing file as "no index yet" rather than latching to empty,
    because a deploy restarts the server before the builders run;
  * a slug that reaches a render path without an index entry still cannot carry
    an injection, because the slug shape is validated and the fallback title is
    derived from the slug.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from stocklib.variety_index import (  # noqa: E402
    DEFAULT_INDEX_PATH, INDEX_FILENAME, VarietyIndex, is_valid_slug,
    title_from_slug, write_variety_index,
)


class SlugValidationTests(unittest.TestCase):
    def test_real_slugs_pass(self):
        for slug in ("avocado-hass", "mango-r2e2", "fig-pingo-de-mel",
                     "piper-excelsum-kawakawa", "blueberry-ob1",
                     "avocado-shepard-persea-americana-type-b-fruit-tree"):
            with self.subTest(slug=slug):
                self.assertTrue(is_valid_slug(slug))

    def test_anything_with_html_or_js_meaning_fails(self):
        for slug in ("", "Avocado-Hass", "avocado hass", "avocado'hass",
                     '<script>', "avocado-hass\"", "avocado/hass",
                     "-avocado-hass", "avocado\nhass", "a" * 200):
            with self.subTest(slug=slug):
                self.assertFalse(is_valid_slug(slug))

    def test_slug_derived_title_is_readable(self):
        self.assertEqual(title_from_slug("avocado-hass"), "Avocado Hass")
        self.assertEqual(title_from_slug("fig-pingo-de-mel"), "Fig Pingo De Mel")


class IndexPathTests(unittest.TestCase):
    def test_default_is_the_server_state_dir(self):
        """Not the snapshot dir the builders are invoked with, and not the web
        root: it sits beside subscribers.json, which is what the server reads.
        Deliberately a constant rather than derived from the builder's
        <data_dir>, because the golden fixture's data dir is itself named
        nursery-stock and any derivation rule would write into it."""
        self.assertEqual(DEFAULT_INDEX_PATH,
                         Path("/opt/dale/data") / INDEX_FILENAME)


class WriteAndReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / INDEX_FILENAME

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip(self):
        write_variety_index(self.path, {"avocado-hass": "Avocado - Hass"})
        idx = VarietyIndex(self.path)
        self.assertEqual(idx.title("avocado-hass"), "Avocado - Hass")
        self.assertIn("avocado-hass", idx)
        self.assertTrue(idx.available)
        self.assertEqual(len(idx), 1)

    def test_no_temp_file_left_behind(self):
        """The write is temp-file-plus-rename so a reader never sees a partial
        file; the temp must not survive the rename."""
        write_variety_index(self.path, {"a-b": "A - B"})
        leftovers = [p.name for p in Path(self.tmp.name).iterdir()
                     if p.name != INDEX_FILENAME]
        self.assertEqual(leftovers, [])

    def test_missing_file_is_not_available_but_still_serves_a_title(self):
        idx = VarietyIndex(self.path)
        self.assertFalse(idx.available)
        self.assertIsNone(idx.title("avocado-hass"))
        self.assertEqual(idx.display_title("avocado-hass"), "Avocado Hass")

    def test_a_missing_file_is_re_checked_not_latched(self):
        """A deploy restarts the server before the builders run, so the index
        legitimately appears minutes later. Latching to empty would leave the
        process rejecting or degrading until the next restart."""
        idx = VarietyIndex(self.path)
        self.assertFalse(idx.available)
        write_variety_index(self.path, {"avocado-hass": "Avocado - Hass"})
        self.assertTrue(idx.available)
        self.assertEqual(idx.title("avocado-hass"), "Avocado - Hass")

    def test_rebuild_is_picked_up(self):
        write_variety_index(self.path, {"avocado-hass": "Avocado - Hass"})
        idx = VarietyIndex(self.path)
        self.assertEqual(idx.title("avocado-hass"), "Avocado - Hass")
        write_variety_index(self.path, {"avocado-hass": "Avocado - Hass Type A",
                                        "mango-r2e2": "Mango - R2E2"})
        self.assertEqual(idx.title("avocado-hass"), "Avocado - Hass Type A")
        self.assertEqual(idx.title("mango-r2e2"), "Mango - R2E2")

    def test_corrupt_file_reads_as_no_index_rather_than_raising(self):
        self.path.write_text("{not json")
        idx = VarietyIndex(self.path)
        self.assertFalse(idx.available)
        self.assertIsNone(idx.title("avocado-hass"))

    def test_non_string_entries_are_dropped(self):
        self.path.write_text(json.dumps({"avocado-hass": "Avocado - Hass",
                                         "bad": 12, "worse": None}))
        idx = VarietyIndex(self.path)
        self.assertEqual(idx.titles, {"avocado-hass": "Avocado - Hass"})

    def test_display_title_prefers_index_over_a_stored_fallback(self):
        """The stored title is the one a caller may have chosen. Whenever we
        have our own, ours wins."""
        write_variety_index(self.path, {"avocado-hass": "Avocado - Hass"})
        idx = VarietyIndex(self.path)
        self.assertEqual(
            idx.display_title("avocado-hass", "<script>alert(1)</script>"),
            "Avocado - Hass",
        )

    def test_display_title_falls_back_to_the_stored_title_for_unknown_slugs(self):
        """~12 watched slugs have dropped out of live stock, so they have no
        page and no index entry. Their watchers keep a recognisable name; the
        render sites escape it."""
        write_variety_index(self.path, {"mango-r2e2": "Mango - R2E2"})
        idx = VarietyIndex(self.path)
        self.assertEqual(idx.display_title("gone-forever", "Gone - Forever"),
                         "Gone - Forever")

    def test_display_title_last_resort_is_derived_from_the_slug(self):
        write_variety_index(self.path, {"mango-r2e2": "Mango - R2E2"})
        idx = VarietyIndex(self.path)
        self.assertEqual(idx.display_title("gone-forever"), "Gone Forever")


class BuilderEmitsIndexTests(unittest.TestCase):
    """build_variety_pages.py writes the index the server reads.

    Run against the golden fixture, so this also proves the builder does not
    write into the fixture directory when given --index-out.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "out"
        self.index = Path(self.tmp.name) / INDEX_FILENAME
        fixture = REPO_ROOT / "tests" / "golden" / "fixture" / "nursery-stock"
        import subprocess
        subprocess.run(
            [sys.executable, str(SCRAPERS / "build_variety_pages.py"),
             str(fixture), str(self.out), "--index-out", str(self.index)],
            cwd=str(SCRAPERS), capture_output=True, text=True, check=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_index_is_written(self):
        self.assertTrue(self.index.exists(), "builder wrote no variety index")
        titles = json.loads(self.index.read_text())
        self.assertTrue(titles)

    def test_every_generated_page_has_an_entry(self):
        """The server rejects a slug it cannot find here, so a page without an
        entry would be a variety nobody could set an alert on."""
        titles = json.loads(self.index.read_text())
        pages = {p.stem for p in (self.out / "variety").glob("*.html")
                 if p.stem != "index"}
        self.assertEqual(pages - set(titles), set())

    def test_titles_are_canonical_not_raw_listing_titles(self):
        titles = json.loads(self.index.read_text())
        for slug, title in titles.items():
            with self.subTest(slug=slug):
                self.assertNotIn("Pot", title)
                self.assertNotIn("  ", title)

    def test_nothing_was_written_into_the_fixture(self):
        fixture_parent = REPO_ROOT / "tests" / "golden" / "fixture"
        self.assertFalse((fixture_parent / INDEX_FILENAME).exists())
        self.assertFalse((fixture_parent / "nursery-stock" / INDEX_FILENAME).exists())


class GrandfatheredSlugsAreIndexedTests(unittest.TestCase):
    """Grandfathered slugs are kept OUT of the browsable /variety/ index, but
    they must be IN this one.

    They exist only because real people watch them (DEC-195). If the server
    cannot find one here it rejects the watch, and the alert sender cannot name
    the variety, which is precisely the group with the most to lose.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        data = root / "data" / "somenursery"
        data.mkdir(parents=True)
        (data / "latest.json").write_text(json.dumps({
            "nursery": "somenursery",
            "nursery_name": "Some Nursery",
            "scraped_at": "2026-03-05T03:12:48",
            "products": [
                {"nursery": "somenursery", "nursery_name": "Some Nursery",
                 "title": "Mandevilla - Peach Sunrise",
                 "url": "https://example.test/mandevilla",
                 "category": "Plants", "min_price": 19.95,
                 "any_available": True,
                 "variants": [{"title": "140mm", "price": 19.95, "available": True}]},
                {"nursery": "somenursery", "nursery_name": "Some Nursery",
                 "title": "Avocado - Hass",
                 "url": "https://example.test/avocado",
                 "category": "Fruit Trees", "min_price": 46.95,
                 "any_available": True,
                 "variants": [{"title": "Large", "price": 46.95, "available": True}]},
            ],
        }))
        self.out = root / "out"
        self.index = root / INDEX_FILENAME
        import subprocess
        subprocess.run(
            [sys.executable, str(SCRAPERS / "build_variety_pages.py"),
             str(root / "data"), str(self.out), "--index-out", str(self.index)],
            cwd=str(SCRAPERS), capture_output=True, text=True, check=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_grandfathered_slug_has_a_page_and_an_index_entry(self):
        self.assertTrue((self.out / "variety" / "mandevilla-peach-sunrise.html").exists())
        titles = json.loads(self.index.read_text())
        self.assertEqual(titles.get("mandevilla-peach-sunrise"),
                         "Mandevilla - Peach Sunrise")

    def test_grandfathered_slug_still_stays_out_of_the_browsable_index(self):
        listing = (self.out / "variety" / "index.html").read_text()
        self.assertNotIn("mandevilla-peach-sunrise", listing)
        self.assertIn("avocado-hass", listing)


if __name__ == "__main__":
    unittest.main()
