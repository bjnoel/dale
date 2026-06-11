"""
Tests for stocklib.scrape_health: the per-nursery scrape-health JSONL writer
(DAL-193 P0.1). One record per nursery per run, including failures, is the
contract the anomaly detector and the /admin health grid depend on.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "scrapers"))

from stocklib.scrape_health import (  # noqa: E402
    ScrapeHealth, append_record, default_health_dir, read_records,
)

REQUIRED_FIELDS = {
    "ts", "nursery", "ok", "products", "in_stock",
    "duration_s", "http_403", "http_429", "error",
}


class AppendRecordTest(unittest.TestCase):
    def test_appends_one_line_per_record_to_dated_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = append_record({"nursery": "daleys", "ok": True}, tmp)
            append_record({"nursery": "ladybird", "ok": False}, tmp)

            self.assertEqual(path.name, f"{date.today().isoformat()}.jsonl")
            lines = path.read_text().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["nursery"], "daleys")
            self.assertEqual(json.loads(lines[1])["nursery"], "ladybird")

    def test_creates_missing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "scraper-health"
            path = append_record({"nursery": "daleys"}, target)
            self.assertTrue(path.exists())

    def test_default_dir_respects_env(self):
        import os
        old = os.environ.get("DALE_DATA_DIR")
        os.environ["DALE_DATA_DIR"] = "/tmp/dale-test-data"
        try:
            self.assertEqual(default_health_dir(),
                             Path("/tmp/dale-test-data/scraper-health"))
        finally:
            if old is None:
                del os.environ["DALE_DATA_DIR"]
            else:
                os.environ["DALE_DATA_DIR"] = old


class ReadRecordsTest(unittest.TestCase):
    def test_reads_back_what_was_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            append_record({"nursery": "daleys", "ok": True}, tmp)
            day = date.today().isoformat()
            records = read_records(day, tmp)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["nursery"], "daleys")

    def test_missing_day_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(read_records("1999-01-01", tmp), [])

    def test_torn_line_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            day = date.today().isoformat()
            path = Path(tmp) / f"{day}.jsonl"
            path.write_text('{"nursery": "daleys", "ok": true}\n{"nursery": "lady\n')
            records = read_records(day, tmp)
            self.assertEqual(len(records), 1)


class ScrapeHealthTest(unittest.TestCase):
    def _finish(self, health, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            health.health_dir = tmp
            return health.finish(**kwargs)

    def test_success_record_has_all_fields(self):
        rec = self._finish(ScrapeHealth("ross-creek"), products=120, in_stock=80)
        self.assertEqual(set(rec), REQUIRED_FIELDS)
        self.assertTrue(rec["ok"])
        self.assertEqual(rec["products"], 120)
        self.assertEqual(rec["in_stock"], 80)
        self.assertEqual(rec["http_403"], 0)
        self.assertEqual(rec["http_429"], 0)
        self.assertIsNone(rec["error"])
        self.assertGreaterEqual(rec["duration_s"], 0)

    def test_http_403_and_429_are_counted(self):
        health = ScrapeHealth("ladybird")
        health.note_http_error(403, "https://x/p1")
        health.note_http_error(403, "https://x/p2")
        health.note_http_error(429, "https://x/p3")
        health.note_http_error(500, "https://x/p4")
        rec = self._finish(health, products=10, in_stock=5)
        self.assertEqual(rec["http_403"], 2)
        self.assertEqual(rec["http_429"], 1)
        self.assertIn("HTTP 500", rec["error"])

    def test_zero_products_with_error_means_failed(self):
        health = ScrapeHealth("fruitopia")
        health.note_error("connection refused")
        rec = self._finish(health)
        self.assertFalse(rec["ok"])
        self.assertEqual(rec["error"], "connection refused")

    def test_zero_products_without_error_is_ok(self):
        # A store legitimately filtered to zero products is not a failed
        # scrape; the anomaly detector handles 0-where-yesterday>0 instead.
        rec = self._finish(ScrapeHealth("forever-seeds"))
        self.assertTrue(rec["ok"])

    def test_partial_errors_with_products_is_ok_but_recorded(self):
        health = ScrapeHealth("primal-fruits")
        health.note_error("timed out")
        rec = self._finish(health, products=50, in_stock=30)
        self.assertTrue(rec["ok"])
        self.assertEqual(rec["error"], "timed out")

    def test_explicit_ok_false_wins(self):
        rec = self._finish(ScrapeHealth("daleys"), products=100, ok=False)
        self.assertFalse(rec["ok"])

    def test_finish_writes_exactly_one_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            health = ScrapeHealth("guildford", health_dir=tmp)
            health.finish(products=1, in_stock=1)
            records = read_records(date.today().isoformat(), tmp)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["nursery"], "guildford")


if __name__ == "__main__":
    unittest.main()
