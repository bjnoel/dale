"""Guards for the DAL-292 alarm retune.

Each test pins a shape that was measured over the 99 nights of health records,
not a constant. Asserting the constants would go circular the next time one is
retuned; asserting "the six known outages alarm and the recovery rows do not"
survives a retune and fails a regression.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "scrapers"))

import detect_scrape_anomalies as dsa  # noqa: E402
from stocklib.registry import NURSERIES  # noqa: E402

KEYS = [n.key for n in NURSERIES]


def rec(nursery, ok=True, products=100, in_stock=50, priced=100, source="html", **kw):
    r = {"nursery": nursery, "ok": ok, "products": products,
         "in_stock": in_stock, "priced": priced, "source": source}
    r.update(kw)
    return r


class ZeroProductsIsNotASecondRowAboutAFailure(unittest.TestCase):
    """36 of 36 zero_products rows ever raised were on a nursery already
    reported failed the same night. It never fired independently."""

    def test_failed_run_does_not_also_raise_zero_products(self):
        days = [
            [rec("daleys", ok=False, products=0, in_stock=0, priced=None)],
            [rec("daleys", products=647)],
            [rec("daleys", products=647)],
        ]
        types = [a["type"] for a in dsa.detect_anomalies(days)]
        self.assertIn("failed", types)
        self.assertNotIn("zero_products", types)

    def test_successful_but_empty_run_still_raises_zero_products(self):
        """The case the rule was written for must stay covered."""
        days = [
            [rec("daleys", ok=True, products=0, in_stock=0, priced=0)],
            [rec("daleys", products=647)],
            [rec("daleys", products=647)],
        ]
        types = [a["type"] for a in dsa.detect_anomalies(days)]
        self.assertIn("zero_products", types)
        self.assertNotIn("failed", types)


class CountSwingIgnoresRecoveries(unittest.TestCase):
    """Four V-shaped pairs produced 8 of the 9 count swings ever raised. The
    drop is worth an email; "it is back" is not."""

    def test_the_drop_alarms(self):
        days = [
            [rec("ladybird", products=750)],
            [rec("ladybird", products=7022)],
            [rec("ladybird", products=7010)],
        ]
        swings = [a for a in dsa.detect_anomalies(days) if a["type"] == "count_swing"]
        self.assertEqual(len(swings), 1)

    def test_the_recovery_does_not(self):
        days = [
            [rec("ladybird", products=7035)],
            [rec("ladybird", products=750)],
            [rec("ladybird", products=7022)],
        ]
        swings = [a for a in dsa.detect_anomalies(days) if a["type"] == "count_swing"]
        self.assertEqual(swings, [])

    def test_a_structural_swing_is_not_a_recovery(self):
        """daleys 647 -> 1998 on 2026-08-20, the source swap. Two nights ago
        was 647, so the new level is genuinely new and must survive."""
        days = [
            [rec("daleys", products=1998)],
            [rec("daleys", products=646)],
            [rec("daleys", products=647)],
        ]
        swings = [a for a in dsa.detect_anomalies(days) if a["type"] == "count_swing"]
        self.assertEqual(len(swings), 1)

    def test_a_failed_night_before_last_is_not_a_level_to_return_to(self):
        days = [
            [rec("ladybird", products=7035)],
            [rec("ladybird", products=750)],
            [rec("ladybird", ok=False, products=0, priced=None)],
        ]
        swings = [a for a in dsa.detect_anomalies(days) if a["type"] == "count_swing"]
        self.assertEqual(len(swings), 1)


class PanelCoverage(unittest.TestCase):
    """The six worst nights on record raised one or two ordinary anomalies each
    and read as quieter than a routine night."""

    def _dir(self, days):
        tmp = tempfile.mkdtemp()
        for day, records in days.items():
            with open(Path(tmp) / f"{day}.jsonl", "w") as fh:
                for r in records:
                    fh.write(json.dumps(r) + "\n")
        return tmp

    def test_a_total_outage_alarms_even_though_it_raises_almost_nothing(self):
        history = {f"2026-06-{d:02d}": [rec(k) for k in KEYS] for d in range(10, 24)}
        today = [rec(KEYS[0]), rec(KEYS[1], ok=False, products=0, priced=None)]
        history["2026-06-24"] = today
        hd = self._dir(history)

        ordinary = dsa.detect_anomalies([today, [rec(k) for k in KEYS],
                                         [rec(k) for k in KEYS]])
        self.assertLessEqual(len(ordinary), 2)  # reads as a routine night

        panel = dsa.detect_panel_coverage("2026-06-24", [today], hd)
        self.assertIsNotNone(panel)
        self.assertEqual(panel["type"], "panel_coverage")
        self.assertLess(panel["coverage"], 0.2)

    def test_a_full_panel_does_not_alarm(self):
        history = {f"2026-06-{d:02d}": [rec(k) for k in KEYS] for d in range(10, 25)}
        hd = self._dir(history)
        today = [rec(k) for k in KEYS]
        self.assertIsNone(dsa.detect_panel_coverage("2026-06-24", [today], hd))

    def test_the_first_night_of_instrumentation_does_not_alarm(self):
        """2026-06-11 had one record because the feature had just landed, not
        because the panel collapsed. A nursery never seen is not missing."""
        hd = self._dir({"2026-06-11": [rec(KEYS[0])]})
        self.assertIsNone(dsa.detect_panel_coverage("2026-06-11", [[rec(KEYS[0])]], hd))

    def test_a_partial_night_does_not_read_as_an_outage(self):
        """2026-07-11: 25 of 27 ran and 11 failed. Many failure rows is the
        right shape for that; a panel banner is not."""
        history = {f"2026-07-{d:02d}": [rec(k) for k in KEYS] for d in range(1, 11)}
        today = [rec(k, ok=(i > 10), products=0 if i <= 10 else 100,
                     priced=None if i <= 10 else 100)
                 for i, k in enumerate(KEYS[:25])]
        history["2026-07-11"] = today
        hd = self._dir(history)
        self.assertIsNone(dsa.detect_panel_coverage("2026-07-11", [today], hd))

    def test_the_outage_leads_the_email_not_the_row_count(self):
        panel = {"nursery": "(whole panel)", "type": "panel_coverage",
                 "detail": "only 2 of 25 nurseries ran (8%); 23 never reported",
                 "coverage": 0.08, "missing": KEYS[2:]}
        other = {"nursery": "daleys", "type": "failed", "detail": "timeout"}
        subject, html, text = dsa.build_email([panel, other], "2026-06-24")
        self.assertIn("PANEL OUTAGE", subject)
        self.assertNotIn("2 anomalies", subject)
        self.assertIn("PANEL OUTAGE", text)
        self.assertIn("Panel outage", html)

    def test_an_ordinary_night_keeps_the_plain_subject(self):
        other = {"nursery": "daleys", "type": "failed", "detail": "timeout"}
        subject, html, text = dsa.build_email([other], "2026-08-20")
        self.assertIn("1 anomalies", subject)
        self.assertNotIn("PANEL OUTAGE", subject)
        self.assertNotIn("PANEL OUTAGE", text)


if __name__ == "__main__":
    unittest.main()
