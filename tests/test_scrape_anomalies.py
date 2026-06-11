"""
Tests for detect_scrape_anomalies.py (DAL-193 P0.2): fixture-based, one per
alert condition (failed run, zero products where yesterday had stock, any
403/429, 3-day failure streak), plus the dry-run output contract.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "scrapers"))

from detect_scrape_anomalies import (  # noqa: E402
    STREAK_DAYS, build_email, detect_anomalies, latest_by_nursery, main,
)
from stocklib.scrape_health import append_record  # noqa: E402


def rec(nursery, ok=True, products=100, in_stock=80, http_403=0, http_429=0,
        error=None):
    return {
        "ts": "2026-06-11T01:00:00", "nursery": nursery, "ok": ok,
        "products": products, "in_stock": in_stock, "duration_s": 1.0,
        "http_403": http_403, "http_429": http_429, "error": error,
    }


def types_for(anomalies, nursery):
    return [a["type"] for a in anomalies if a["nursery"] == nursery]


class DetectAnomaliesTest(unittest.TestCase):
    def test_healthy_day_has_no_anomalies(self):
        days = [[rec("daleys"), rec("ladybird")], [rec("daleys")], []]
        self.assertEqual(detect_anomalies(days), [])

    def test_failed_run_is_flagged(self):
        days = [[rec("daleys", ok=False, products=0, error="HTTP 500")], [], []]
        anomalies = detect_anomalies(days)
        self.assertIn("failed", types_for(anomalies, "daleys"))
        self.assertIn("HTTP 500", anomalies[0]["detail"])

    def test_zero_products_where_yesterday_had_stock(self):
        days = [[rec("ladybird", products=0, in_stock=0)],
                [rec("ladybird", products=240)], []]
        anomalies = detect_anomalies(days)
        self.assertIn("zero_products", types_for(anomalies, "ladybird"))
        self.assertIn("240 yesterday", anomalies[0]["detail"])

    def test_zero_products_with_zero_yesterday_is_not_flagged(self):
        # A store that was already empty yesterday is not a new anomaly.
        days = [[rec("forever-seeds", products=0)],
                [rec("forever-seeds", products=0)], []]
        self.assertEqual(detect_anomalies(days), [])

    def test_zero_products_with_no_yesterday_record_is_not_flagged(self):
        days = [[rec("new-nursery", products=0)], [], []]
        self.assertEqual(detect_anomalies(days), [])

    def test_403_is_flagged_as_blocked(self):
        days = [[rec("diggers", http_403=4)], [], []]
        anomalies = detect_anomalies(days)
        self.assertEqual(types_for(anomalies, "diggers"), ["blocked"])
        self.assertIn("4x HTTP 403", anomalies[0]["detail"])

    def test_429_is_flagged_as_blocked(self):
        days = [[rec("guildford", http_429=2)], [], []]
        anomalies = detect_anomalies(days)
        self.assertEqual(types_for(anomalies, "guildford"), ["blocked"])
        self.assertIn("2x HTTP 429", anomalies[0]["detail"])

    def test_three_day_failure_streak(self):
        failing = rec("heritage-fruit-trees", ok=False, products=0)
        days = [[failing], [failing], [failing]]
        anomalies = detect_anomalies(days)
        self.assertIn("failure_streak", types_for(anomalies, "heritage-fruit-trees"))

    def test_two_day_failure_is_not_a_streak(self):
        failing = rec("heritage-fruit-trees", ok=False, products=0)
        days = [[failing], [failing], [rec("heritage-fruit-trees")]]
        anomalies = detect_anomalies(days)
        types = types_for(anomalies, "heritage-fruit-trees")
        self.assertIn("failed", types)
        self.assertNotIn("failure_streak", types)

    def test_missing_prior_day_record_breaks_the_streak(self):
        failing = rec("daleys", ok=False, products=0)
        days = [[failing], [], [failing]]
        types = types_for(detect_anomalies(days), "daleys")
        self.assertNotIn("failure_streak", types)

    def test_rerun_uses_latest_record_for_the_day(self):
        # Pipeline re-run on the same day: first run failed, re-run succeeded.
        days = [[rec("daleys", ok=False, products=0, error="boom"),
                 rec("daleys")], [], []]
        self.assertEqual(detect_anomalies(days), [])

    def test_latest_by_nursery_keeps_last(self):
        latest = latest_by_nursery([rec("a", products=1), rec("a", products=2)])
        self.assertEqual(latest["a"]["products"], 2)


class BuildEmailTest(unittest.TestCase):
    def test_email_contains_each_anomaly(self):
        anomalies = [
            {"nursery": "daleys", "type": "failed", "detail": "HTTP 500"},
            {"nursery": "diggers", "type": "blocked", "detail": "1x HTTP 403, 0x HTTP 429"},
        ]
        subject, html, text = build_email(anomalies, "2026-06-11")
        self.assertIn("2 anomalies", subject)
        for needle in ("daleys", "diggers", "HTTP 500"):
            self.assertIn(needle, html)
            self.assertIn(needle, text)


class MainDryRunTest(unittest.TestCase):
    def _write_day(self, tmp, offset, records):
        day = (date.today() - timedelta(days=offset)).isoformat()
        path = Path(tmp) / f"{day}.jsonl"
        import json
        with open(path, "a") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def test_dry_run_prints_email_without_sending(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_day(tmp, 0, [rec("daleys", ok=False, products=0,
                                         error="connection refused")])
            out = io.StringIO()
            with redirect_stdout(out):
                code = main([tmp, "--dry-run"])
            self.assertEqual(code, 0)
            output = out.getvalue()
            self.assertIn("[DRY RUN]", output)
            self.assertIn("Subject: Scrape health: 1 anomalies", output)
            self.assertIn("connection refused", output)

    def test_no_records_today_is_a_clean_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with redirect_stdout(out):
                code = main([tmp, "--dry-run"])
            self.assertEqual(code, 0)
            self.assertIn("no records", out.getvalue())

    def test_healthy_records_report_no_anomalies(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_day(tmp, 0, [rec("daleys"), rec("ladybird")])
            out = io.StringIO()
            with redirect_stdout(out):
                code = main([tmp, "--dry-run"])
            self.assertEqual(code, 0)
            self.assertIn("no anomalies", out.getvalue())


class AppendRecordIntegrationTest(unittest.TestCase):
    def test_detector_reads_what_the_writer_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            append_record(rec("daleys", ok=False, products=0, error="dead"), tmp)
            out = io.StringIO()
            with redirect_stdout(out):
                main([tmp, "--dry-run"])
            self.assertIn("daleys: failed - dead", out.getvalue())


if __name__ == "__main__":
    unittest.main()
