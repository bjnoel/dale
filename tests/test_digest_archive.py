"""Tests for the /admin/digest archive of the Dale daily digest.

Two things matter here and neither is cosmetic:

  1. The day comes off the URL and is used to build a filesystem path, so the
     validator is a traversal guard.
  2. tools/autonomous/daily-digest.py WRITES the archive and
     tools/scrapers/digest_archive.py READS it, across two deploy trees with no
     shared import. test_write_and_read_agree_on_path is what keeps that
     convention from silently drifting apart.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import digest_archive  # noqa: E402


def _load_daily_digest():
    """tools/autonomous/daily-digest.py, whose hyphen blocks a normal import."""
    path = REPO_ROOT / "tools" / "autonomous" / "daily-digest.py"
    spec = importlib.util.spec_from_file_location("autonomous_daily_digest", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestDayValidation(unittest.TestCase):
    def test_accepts_a_real_day(self):
        self.assertTrue(digest_archive.is_valid_day("2026-08-09"))

    def test_rejects_traversal_and_junk(self):
        for bad in [
            "../../etc/passwd",
            "2026-08-09/../../../etc/passwd",
            "..",
            "",
            None,
            "2026-8-9",
            "2026-08-09.html",
            "latest",
            "2026-13-01",   # no month 13
            "2026-02-30",   # not a real date
            "%2e%2e%2f",
        ]:
            with self.subTest(bad=bad):
                self.assertFalse(digest_archive.is_valid_day(bad))

    def test_digest_path_refuses_bad_day(self):
        with self.assertRaises(ValueError):
            digest_archive.digest_path("/tmp", "../secrets")

    def test_load_digest_returns_none_for_bad_day(self):
        # Must not raise: this is reached straight from the URL.
        self.assertIsNone(digest_archive.load_digest("/tmp", "../../etc/passwd"))


class TestSaveAndList(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip(self):
        digest_archive.save_digest(self.data, "2026-08-09", "<h2>hello</h2>")
        self.assertEqual(
            digest_archive.load_digest(self.data, "2026-08-09"), "<h2>hello</h2>"
        )

    def test_list_is_newest_first(self):
        for day in ["2026-07-01", "2026-08-09", "2026-08-02"]:
            digest_archive.save_digest(self.data, day, "x")
        self.assertEqual(
            digest_archive.list_digest_days(self.data),
            ["2026-08-09", "2026-08-02", "2026-07-01"],
        )

    def test_list_ignores_foreign_files(self):
        digest_archive.save_digest(self.data, "2026-08-09", "x")
        d = digest_archive.digests_dir(self.data)
        (d / "notes.txt").write_text("x")
        (d / "backup.html").write_text("x")
        (d / "2026-08-09.html.tmp").write_text("x")
        self.assertEqual(digest_archive.list_digest_days(self.data), ["2026-08-09"])

    def test_missing_dir_is_empty_not_an_error(self):
        self.assertEqual(digest_archive.list_digest_days(self.data / "nope"), [])


class TestRender(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        for day in ["2026-07-30", "2026-08-08", "2026-08-09"]:
            digest_archive.save_digest(
                self.data, day, f"<h2>Dale Daily Digest &mdash; {day}</h2>"
            )

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_shows_newest(self):
        status, page = digest_archive.render_digest_page(self.data)
        self.assertEqual(status, 200)
        self.assertIn("Dale Daily Digest &mdash; 2026-08-09", page)
        self.assertNotIn("Dale Daily Digest &mdash; 2026-08-08", page)

    def test_specific_day(self):
        status, page = digest_archive.render_digest_page(self.data, "2026-08-08")
        self.assertEqual(status, 200)
        self.assertIn("Dale Daily Digest &mdash; 2026-08-08", page)

    def test_older_and_newer_links(self):
        _, page = digest_archive.render_digest_page(self.data, "2026-08-08")
        self.assertIn('href="/admin/digest/2026-08-09"', page)  # newer
        self.assertIn('href="/admin/digest/2026-07-30"', page)  # older

    def test_newest_has_no_newer_link(self):
        _, page = digest_archive.render_digest_page(self.data, "2026-08-09")
        self.assertIn('<span class="off">&larr; Newer</span>', page)

    def test_oldest_has_no_older_link(self):
        _, page = digest_archive.render_digest_page(self.data, "2026-07-30")
        self.assertIn('<span class="off">Older &rarr;</span>', page)

    def test_archive_lists_every_day(self):
        _, page = digest_archive.render_digest_page(self.data)
        for day in ["2026-07-30", "2026-08-08", "2026-08-09"]:
            self.assertIn(f'href="/admin/digest/{day}"', page)

    def test_older_month_is_collapsed(self):
        _, page = digest_archive.render_digest_page(self.data)
        self.assertIn("<details><summary>July 2026 (1)</summary>", page)
        self.assertIn("<h3>August 2026</h3>", page)

    def test_unknown_day_is_404_with_the_list(self):
        status, page = digest_archive.render_digest_page(self.data, "2026-01-01")
        self.assertEqual(status, 404)
        self.assertIn("No digest for 2026-01-01", page)
        self.assertIn('href="/admin/digest/2026-08-09"', page)

    def test_malformed_day_is_404_and_escaped(self):
        status, page = digest_archive.render_digest_page(self.data, "<script>x</script>")
        self.assertEqual(status, 404)
        self.assertNotIn("<script>x</script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_empty_archive_explains_itself(self):
        empty = Path(self.tmp.name) / "empty"
        status, page = digest_archive.render_digest_page(empty)
        self.assertEqual(status, 200)
        self.assertIn("No digests archived yet", page)

    def test_links_back_to_admin(self):
        _, page = digest_archive.render_digest_page(self.data)
        self.assertIn('href="/admin"', page)

    def test_page_is_noindex(self):
        _, page = digest_archive.render_digest_page(self.data)
        self.assertIn('name="robots" content="noindex, nofollow"', page)


class TestWriterReaderContract(unittest.TestCase):
    """daily-digest.py writes; digest_archive.py reads. No shared import."""

    def test_write_and_read_agree_on_path(self):
        dd = _load_daily_digest()
        with tempfile.TemporaryDirectory() as tmp:
            # Write exactly the way the cron does.
            dd.write_digest_archive(tmp, "2026-08-09", "<h2>from the cron</h2>")
            # Read exactly the way /admin/digest does.
            self.assertEqual(
                digest_archive.load_digest(tmp, "2026-08-09"), "<h2>from the cron</h2>"
            )
            self.assertEqual(digest_archive.list_digest_days(tmp), ["2026-08-09"])

    def test_dirname_constant_matches(self):
        dd = _load_daily_digest()
        self.assertEqual(dd.DIGESTS_DIRNAME, digest_archive.DIGESTS_DIRNAME)

    def test_writer_never_raises_on_a_bad_dir(self):
        # A full or unwritable disk must not stop the email going out.
        dd = _load_daily_digest()
        dd.write_digest_archive("/proc/nonexistent-cannot-mkdir", "2026-08-09", "x")

    def test_writer_leaves_no_tmp_file(self):
        dd = _load_daily_digest()
        with tempfile.TemporaryDirectory() as tmp:
            dd.write_digest_archive(tmp, "2026-08-09", "x")
            leftovers = list(digest_archive.digests_dir(tmp).glob("*.tmp"))
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
