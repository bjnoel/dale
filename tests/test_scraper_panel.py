"""
Regression tests: one nursery's crash must not stop the rest of its platform.

2026-09-27 to 09-29, Guildford (first in the WooCommerce dict) crashed on an
unexpected API response and main() re-raised, so the seven WooCommerce
nurseries after it never ran for three nights. Shopify, Ecwid, Squarespace and
Wix had the same loop. Each scraper's real main() is run here with a first
nursery that crashes; the second must still run and both must leave a health
record.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import contextlib
import importlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

from stocklib.panel import run_panel  # noqa: E402

CRASH = AttributeError("'str' object has no attribute 'get'")

# module: (scrape function, what it returns, what save_snapshot returns)
SCRAPERS = {
    "shopify_scraper": ("scrape_shopify", [{"id": 1}],
                        [{"any_available": True, "min_price": 25.0}]),
    "ecwid_scraper": ("scrape_ecwid", [{"available": True, "price": 25.0}], None),
    "squarespace_scraper": ("scrape_squarespace",
                            [{"available": True, "min_price": 25.0}], None),
    "wix_scraper": ("scrape_wix", [{"available": True, "min_price": 25.0}], None),
    "woocommerce_scraper": ("scrape_woocommerce", [{"id": 1}],
                            {"product_count": 1, "in_stock_count": 1,
                             "products": [{"min_price": 25.0}]}),
}


def _health_records(data_dir):
    out = []
    for f in sorted(Path(data_dir, "scraper-health").glob("*.jsonl")):
        out += [json.loads(line) for line in f.read_text().splitlines() if line]
    return {r["nursery"]: r for r in out}


class EveryScraperSurvivesOneCrash(unittest.TestCase):
    def _run_main(self, module_name):
        mod = importlib.import_module(module_name)
        scrape_attr, scraped, saved = SCRAPERS[module_name]
        ran = []

        def scrape(key, config, health=None):
            ran.append(key)
            if key == "first":
                raise CRASH
            return scraped

        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, {"DALE_DATA_DIR": tmp}))
            stack.enter_context(mock.patch.object(
                mod, "NURSERIES", {"first": {"name": "First"}, "second": {"name": "Second"}}))
            stack.enter_context(mock.patch.object(mod, scrape_attr, scrape))
            stack.enter_context(mock.patch.object(mod, "save_snapshot", return_value=saved))
            if hasattr(mod, "print_summary"):
                stack.enter_context(mock.patch.object(mod, "print_summary"))
            stack.enter_context(mock.patch.object(mod.sys, "argv", [f"{module_name}.py"]))
            stack.enter_context(mock.patch("time.sleep"))
            stack.enter_context(mock.patch("sys.stderr", new_callable=io.StringIO))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            with self.assertRaises(SystemExit) as cm:
                mod.main()
            records = _health_records(tmp)
        return ran, cm.exception.code, records

    def test_each_scraper(self):
        for module_name in SCRAPERS:
            with self.subTest(module_name):
                ran, code, records = self._run_main(module_name)
                self.assertEqual(ran, ["first", "second"])
                self.assertEqual(code, 1)
                self.assertFalse(records["first"]["ok"])
                self.assertIn("AttributeError", records["first"]["error"])
                self.assertTrue(records["second"]["ok"])
                self.assertEqual(records["second"]["products"], 1)
                self.assertEqual(records["second"]["in_stock"], 1)
                self.assertEqual(records["second"]["priced"], 1)


class RunPanel(unittest.TestCase):
    def _run(self, targets, scrape_one, **kw):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"DALE_DATA_DIR": tmp}), \
                contextlib.redirect_stdout(io.StringIO()):
            run_panel(targets, "test", scrape_one, **kw)
            return _health_records(tmp)

    def test_clean_night_does_not_exit(self):
        records = self._run({"a": {}, "b": {}}, lambda k, c, h: {"products": 3, "in_stock": 2})
        self.assertEqual({k: r["products"] for k, r in records.items()}, {"a": 3, "b": 3})

    def test_none_result_uses_finish_defaults(self):
        records = self._run({"a": {}}, lambda k, c, h: None)
        self.assertEqual(records["a"]["products"], 0)
        self.assertTrue(records["a"]["ok"])  # no error noted, as health.finish() decides

    def test_pause_runs_between_nurseries_not_after_the_last(self):
        pauses = []
        self._run({"a": {}, "b": {}, "c": {}}, lambda k, c, h: None,
                  pause=lambda: pauses.append(1))
        self.assertEqual(len(pauses), 2)


if __name__ == "__main__":
    unittest.main()
