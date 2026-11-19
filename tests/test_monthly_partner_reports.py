"""Tests for tools/autonomous/monthly_partner_reports.py: who gets a report,
when it runs, and that a rerun keeps the link Benedict may already have sent."""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "autonomous"))
import monthly_partner_reports as mpr  # noqa: E402


class FirstTuesday(unittest.TestCase):
    def test_first_tuesdays(self):
        self.assertTrue(mpr.is_first_tuesday(date(2026, 12, 1)))
        self.assertTrue(mpr.is_first_tuesday(date(2027, 1, 5)))

    def test_second_tuesday_and_first_monday(self):
        self.assertFalse(mpr.is_first_tuesday(date(2026, 12, 8)))
        self.assertFalse(mpr.is_first_tuesday(date(2027, 1, 4)))

    def test_previous_month_crosses_year(self):
        self.assertEqual(mpr.previous_month(date(2027, 1, 5)), "2026-12")
        self.assertEqual(mpr.previous_month(date(2026, 12, 1)), "2026-11")


class Selection(unittest.TestCase):
    REG = {"nurseries": [
        {"key": "daleys", "status": "warm"},
        {"key": "heritage-fruit-trees", "status": "courtesy"},
        {"key": "primal-fruits", "status": "personal"},
        {"key": "ladybird", "status": "contacted"},
        {"key": "guildford", "status": "cold"},
        {"key": "plantnet", "status": "not_contacted"},
        {"key": "garden-world", "status": "unreachable"},
        {"key": "kalamunda-plants", "status": "courtesy"},
    ]}

    def test_only_established_and_scraped(self):
        chosen, skipped = mpr.select_nurseries(self.REG, lambda k: k != "kalamunda-plants")
        self.assertEqual([n["key"] for n in chosen],
                         ["daleys", "heritage-fruit-trees", "primal-fruits"])
        # Established but unscraped is reported as skipped; cold/contacted are silent.
        self.assertEqual([n["key"] for n, _ in skipped], ["kalamunda-plants"])


class StableLinks(unittest.TestCase):
    def test_rerun_reuses_existing_file(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "primal-fruits-2026-10-1a70c90300.html").write_text("x")
            self.assertEqual(mpr.report_path(d, "primal-fruits", "2026-10").name,
                             "primal-fruits-2026-10-1a70c90300.html")
            new = mpr.report_path(d, "primal-fruits", "2026-11")
            self.assertRegex(new.name, r"^primal-fruits-2026-11-[0-9a-f]{10}\.html$")


class Email(unittest.TestCase):
    def test_lists_contact_link_and_failures(self):
        n = {"key": "fruitopia", "name": "Fruitopia", "contact_name": None,
             "preferred_channel": "instagram"}
        a = {"key": "all-rare-herbs", "name": "All Rare Herbs", "contact_name": "Lauretta Archer",
             "preferred_channel": "email", "email": "x@example.com"}
        html, text = mpr.render_email("November 2026",
            [{"nursery": n, "url": "https://treestock.com.au/reports/f.html",
              "people": 40, "prev": 30, "full": False}],
            [(a, "Plausible error")], [])
        self.assertIn("Fruitopia: no contact name on file, via instagram", text)
        self.assertIn("40 people (was 30), traffic only", text)
        self.assertIn("https://treestock.com.au/reports/f.html", html)
        self.assertIn("All Rare Herbs: Plausible error", text)
        self.assertNotIn("—", html + text)


if __name__ == "__main__":
    unittest.main()
