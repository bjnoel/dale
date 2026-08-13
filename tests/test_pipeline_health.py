"""Regression tests for the daily digest's pipeline-health section.

The second half of the 2026-08-12 outage (DEC-293). The scrape failure was
detected correctly on both dead nights and written to data/scraper-health/, and
detect_scrape_anomalies.py would have emailed it, except that it was the last
step of the run that had already aborted. The daily digest, the one report
Benedict actually reads, had no notion of scraper health at all: it reported
traffic, tickets and subscribers as normal for two days while treestock.com.au
served a two-day-old page.

test_reproduces_the_12_august_state is the bug stated as behaviour, built from
the real health record shape and the real staleness.

daily-digest.py has a hyphen, so it cannot be imported by name.
"""

import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIGEST_PATH = REPO_ROOT / "tools" / "autonomous" / "daily-digest.py"

_spec = importlib.util.spec_from_file_location("daily_digest_mod", DIGEST_PATH)
digest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(digest)

NOW = datetime(2026, 8, 13, 22, 0, tzinfo=timezone.utc)


def health_record(nursery, ok=True, products=100):
    return {
        "ts": "2026-08-13T00:34:00", "nursery": nursery, "ok": ok,
        "products": products if ok else 0, "in_stock": 0, "duration_s": 1.0,
        "http_403": 0, "http_429": 0,
        "error": None if ok else "HTTP 503 https://example.com/x",
    }


class PipelineHealthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.dashboard = self.root / "dashboard"
        (self.data / "scraper-health").mkdir(parents=True)
        self.dashboard.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write_health(self, records, day="2026-08-13"):
        p = self.data / "scraper-health" / f"{day}.jsonl"
        p.write_text("".join(json.dumps(r) + "\n" for r in records))

    def write_index(self, age_hours):
        p = self.dashboard / "index.html"
        p.write_text("<html></html>")
        ts = (NOW - timedelta(hours=age_hours)).timestamp()
        os.utime(p, (ts, ts))

    def check(self):
        return digest.get_pipeline_health(
            str(self.data), dashboard_dir=str(self.dashboard), now=NOW)

    # --- the bug -----------------------------------------------------------

    def test_reproduces_the_12_august_state(self):
        """26 nurseries fine, Heritage failed, site last published two days
        ago. The digest must call this broken and name both facts."""
        recs = [health_record(f"nursery-{i}") for i in range(26)]
        recs.append(health_record("heritage-fruit-trees", ok=False))
        self.write_health(recs)
        self.write_index(age_hours=45.4)

        h = self.check()
        self.assertFalse(h["ok"])
        self.assertEqual(h["nurseries_failed"], ["heritage-fruit-trees"])
        self.assertEqual(h["nurseries_ok"], 26)
        joined = " ".join(h["problems"])
        self.assertIn("heritage-fruit-trees", joined)
        self.assertIn("45h ago", joined)

    def test_broken_pipeline_reaches_the_email_and_the_subject(self):
        """It has to be visible without opening anything."""
        self.write_health([health_record("heritage-fruit-trees", ok=False)])
        self.write_index(age_hours=45.4)
        h = self.check()

        html = digest.build_digest_html(
            [], [], [], {"count": 0, "duration_min": 0, "tokens_in": 0,
                         "tokens_out": 0, "cost_usd": 0.0},
            "", "focus", {"total_subscribers": 0, "variety_watch_count": 0,
                          "variety_watch_emails": 0, "variety_watches": {}},
            "2026-08-13", pipeline=h)
        text = digest.build_digest_text(
            [], [], [], {"count": 0, "duration_min": 0, "tokens_in": 0,
                         "tokens_out": 0, "cost_usd": 0.0},
            "", "focus", {"total_subscribers": 0, "variety_watch_count": 0,
                          "variety_watch_emails": 0, "variety_watches": {}},
            "2026-08-13", pipeline=h)

        self.assertIn("Pipeline BROKEN", html)
        self.assertIn("heritage-fruit-trees", html)
        # Ahead of the queue: nothing else matters if the site is not publishing.
        self.assertLess(html.index("Pipeline BROKEN"), html.index("Waiting on you"))
        self.assertIn("BROKEN", text)

    # --- staleness ---------------------------------------------------------

    def test_stale_site_is_broken_even_when_every_scraper_passed(self):
        """The exact shape of this outage: scraping was fine, publishing was
        not. A health-records-only check would have called this healthy."""
        self.write_health([health_record(f"n{i}") for i in range(27)])
        self.write_index(age_hours=45.4)
        h = self.check()
        self.assertFalse(h["ok"])
        self.assertEqual(h["nurseries_failed"], [])
        self.assertTrue(any("last published" in p for p in h["problems"]))

    def test_normal_night_is_healthy(self):
        """21h old at 22:00 UTC is what a good night looks like."""
        self.write_health([health_record(f"n{i}") for i in range(27)])
        self.write_index(age_hours=21.4)
        h = self.check()
        self.assertTrue(h["ok"], h["problems"])
        self.assertEqual(h["nurseries_ok"], 27)

    def test_missing_health_file_is_broken_not_healthy(self):
        """A missing file means the run never reached a nursery. Absence of
        evidence must not read as evidence of health."""
        self.write_index(age_hours=1)
        h = self.check()
        self.assertFalse(h["ok"])
        self.assertTrue(any("No scrape recorded" in p for p in h["problems"]))

    def test_missing_index_is_broken(self):
        self.write_health([health_record("n1")])
        h = self.check()
        self.assertFalse(h["ok"])
        self.assertTrue(any("unreadable" in p for p in h["problems"]))

    # --- robustness --------------------------------------------------------

    def test_rerun_uses_the_last_record_for_a_nursery(self):
        """Re-runs append. A nursery that failed then succeeded is healthy."""
        self.write_health([
            health_record("heritage-fruit-trees", ok=False),
            health_record("heritage-fruit-trees", ok=True),
        ])
        self.write_index(age_hours=1)
        h = self.check()
        self.assertTrue(h["ok"], h["problems"])

    def test_torn_line_does_not_kill_the_reader(self):
        p = self.data / "scraper-health" / "2026-08-13.jsonl"
        p.write_text(json.dumps(health_record("n1")) + "\n{not json\n")
        self.write_index(age_hours=1)
        h = self.check()
        self.assertTrue(h["ok"], h["problems"])
        self.assertEqual(h["nurseries_ok"], 1)

    def test_healthy_pipeline_stays_quiet_and_sits_below_the_queue(self):
        self.write_health([health_record("n1")])
        self.write_index(age_hours=21)
        h = self.check()
        html = digest.build_digest_html(
            [], [], [], {"count": 0, "duration_min": 0, "tokens_in": 0,
                         "tokens_out": 0, "cost_usd": 0.0},
            "", "focus", {"total_subscribers": 0, "variety_watch_count": 0,
                          "variety_watch_emails": 0, "variety_watches": {}},
            "2026-08-13", pipeline=h)
        self.assertIn("treestock healthy", html)
        self.assertGreater(html.index("treestock healthy"), html.index("Waiting on you"))


if __name__ == "__main__":
    unittest.main()
