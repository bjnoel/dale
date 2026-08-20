"""
Tests for detect_scrape_anomalies.py (DAL-193 P0.2): fixture-based, one per
alert condition (failed run, zero products where yesterday had stock, any
403/429, 3-day failure streak, source change, product count swing),
plus the dry-run output contract.

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
    COUNT_SWING_RATIO, STREAK_DAYS, build_email, detect_anomalies,
    latest_by_nursery, main,
)
from stocklib.scrape_health import append_record  # noqa: E402


def rec(nursery, ok=True, products=100, in_stock=80, http_403=0, http_429=0,
        error=None, source=None):
    return {
        "ts": "2026-06-11T01:00:00", "nursery": nursery, "ok": ok,
        "products": products, "in_stock": in_stock, "duration_s": 1.0,
        "http_403": http_403, "http_429": http_429, "error": error,
        **({"source": source} if source else {}),
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



class SourceChangeTest(unittest.TestCase):
    """1.7. On 2026-08-20 Daleys moved from the HTML plant_list scraper to a
    CSV supplier feed. The catalogue went 647 -> 1,998 in one night, out of
    band, three hours after the nightly had already written a snapshot and
    sent that day's digest and alerts against the old numbers. Nothing
    noticed, because the envelope had no way to say which scraper made it.
    """

    def test_the_daleys_swap_now_alarms(self):
        today = [rec("daleys", products=1998, source="feed")]
        yesterday = [rec("daleys", products=647, source="plant_list")]
        found = detect_anomalies([today, yesterday, yesterday])
        kinds = {a["type"] for a in found}
        self.assertIn("source_change", kinds)
        detail = next(a["detail"] for a in found if a["type"] == "source_change")
        self.assertIn("plant_list -> feed", detail)
        self.assertIn("647 -> 1998", detail)

    def test_same_source_is_silent(self):
        today = [rec("ladybird", products=7200, source="shopify")]
        yesterday = [rec("ladybird", products=7150, source="shopify")]
        self.assertEqual(detect_anomalies([today, yesterday, yesterday]), [])

    def test_a_first_ever_source_is_not_a_change(self):
        """Every nursery gains the field on the same deploy. Yesterday's
        records predate it, so a missing prior source must not read as a swap
        and email about all 27 nurseries at once.
        """
        today = [rec("ross-creek", products=1111, source="shopify")]
        yesterday = [rec("ross-creek", products=1100)]  # no source key
        self.assertEqual(detect_anomalies([today, yesterday, yesterday]), [])

    def test_a_failed_run_does_not_report_a_source_change(self):
        """A failed run already has its own anomaly, and its product count is
        not evidence of anything."""
        today = [rec("garden-express", ok=False, products=0, source="shopify")]
        yesterday = [rec("garden-express", products=103, source="woocommerce")]
        kinds = {a["type"] for a in detect_anomalies([today, yesterday, yesterday])}
        self.assertNotIn("source_change", kinds)
        self.assertIn("failed", kinds)


class CountSwingTest(unittest.TestCase):
    """The threshold is deliberately blunt (a doubling or a halving) rather
    than matched to detect_stock_surges.py's +/-20%. That job already owns
    ordinary stock movement and emails on it; a second alarm at the same
    sensitivity would double-send on every seasonal restock, which is the
    noise that trains an alarm to be ignored. This one is for structural
    events: a source swap, a truncated run, a catalogue that vanished.
    """

    def test_the_daleys_tripling_alarms(self):
        today = [rec("daleys", products=1998, source="feed")]
        yesterday = [rec("daleys", products=647, source="feed")]
        found = detect_anomalies([today, yesterday, yesterday])
        swing = [a for a in found if a["type"] == "count_swing"]
        self.assertEqual(len(swing), 1)
        self.assertIn("+209%", swing[0]["detail"])

    def test_a_halving_alarms_too(self):
        today = [rec("fruitopia", products=300, source="shopify")]
        yesterday = [rec("fruitopia", products=639, source="shopify")]
        kinds = {a["type"] for a in detect_anomalies([today, yesterday, yesterday])}
        self.assertIn("count_swing", kinds)

    def test_ordinary_seasonal_movement_is_silent(self):
        """detect_stock_surges.py owns this range. Nothing here should fire at
        the +/-20% that would double up with it."""
        for products in (120, 85, 100, 118):
            with self.subTest(products=products):
                today = [rec("guildford", products=products, source="woocommerce")]
                yesterday = [rec("guildford", products=100, source="woocommerce")]
                kinds = {a["type"] for a in
                         detect_anomalies([today, yesterday, yesterday])}
                self.assertNotIn("count_swing", kinds)

    def test_threshold_is_the_named_constant(self):
        base = 100
        just_over = int(base * COUNT_SWING_RATIO) + 1
        today = [rec("rayners", products=just_over, source="wix")]
        yesterday = [rec("rayners", products=base, source="wix")]
        kinds = {a["type"] for a in detect_anomalies([today, yesterday, yesterday])}
        self.assertIn("count_swing", kinds)

    def test_zero_products_is_left_to_its_own_condition(self):
        """0 today after stock yesterday is already 'zero_products'. Dividing
        by it, or reporting -100% as a swing, adds nothing."""
        today = [rec("engalls", products=0, source="shopify")]
        yesterday = [rec("engalls", products=70, source="shopify")]
        kinds = {a["type"] for a in detect_anomalies([today, yesterday, yesterday])}
        self.assertIn("zero_products", kinds)
        self.assertNotIn("count_swing", kinds)


class SourceRecordedTest(unittest.TestCase):
    """The health record carries source because ScrapeHealth takes it at
    construction, so failure paths carry it too."""

    def test_scrape_health_records_the_source(self):
        from stocklib.scrape_health import ScrapeHealth
        with tempfile.TemporaryDirectory() as tmp:
            h = ScrapeHealth("ross-creek", health_dir=tmp, source="shopify")
            self.assertEqual(h.finish(products=10, in_stock=5)["source"], "shopify")

    def test_failure_path_still_records_the_source(self):
        from stocklib.scrape_health import ScrapeHealth
        with tempfile.TemporaryDirectory() as tmp:
            h = ScrapeHealth("garden-express", health_dir=tmp, source="woocommerce")
            h.note_error("HTTP 400")
            self.assertEqual(h.finish(ok=False)["source"], "woocommerce")

    def test_source_is_optional_so_old_callers_still_work(self):
        from stocklib.scrape_health import ScrapeHealth
        with tempfile.TemporaryDirectory() as tmp:
            rec_ = ScrapeHealth("diacos", health_dir=tmp).finish(products=71)
            self.assertNotIn("source", rec_)



class EveryScraperDeclaresItsSourceTest(unittest.TestCase):
    """A static scan, so a NEW scraper cannot quietly ship without the field.

    The alarm above is only as good as the data reaching it: a scraper whose
    envelope has no source can never report a swap, and the day it is swapped
    is the day you want to know. validate_snapshot requires the key, but that
    is warn-only at runtime and nobody reads cron logs on a good night.
    """

    SCRAPERS = Path(__file__).resolve().parent.parent / "tools" / "scrapers"

    def _scraper_files(self):
        return sorted(f for f in self.SCRAPERS.glob("*_scraper.py"))

    def test_every_scraper_sets_an_envelope_source(self):
        files = self._scraper_files()
        self.assertGreaterEqual(len(files), 6, "expected at least six scrapers")
        for f in files:
            text = f.read_text()
            if "validate_and_warn(snapshot" not in text:
                continue  # not an envelope writer
            with self.subTest(scraper=f.name):
                self.assertIn('"source":', text,
                              f"{f.name} writes a snapshot envelope but sets no "
                              f'"source" field')

    def test_every_scraper_tags_its_health_records(self):
        for f in self._scraper_files():
            text = f.read_text()
            if "ScrapeHealth(" not in text:
                continue
            with self.subTest(scraper=f.name):
                self.assertIn("source=", text,
                              f"{f.name} builds a ScrapeHealth without a source=, "
                              f"so its health records cannot report a swap")


if __name__ == "__main__":
    unittest.main()
