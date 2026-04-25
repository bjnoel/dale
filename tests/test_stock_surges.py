"""
Tests for tools/scrapers/detect_stock_surges.py.

Regression coverage for two bugs (2026-04-25):
  1. Threshold was 20% OR 10+ items, which fired on routine churn at
     large nurseries (Ladybird at ~1700 items would trip on a 0.6%
     change). Changed to AND.
  2. No idempotency guard: when the autonomous Dale rebuilt the
     dashboard mid-day, the script re-sent the alert email. Added a
     dated send marker.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dss = _load(SCRAPERS / "detect_stock_surges.py")


def _write_snapshot(nursery_dir: Path, date_str: str, in_stock: int, name: str):
    nursery_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "nursery_name": name,
        "product_count": in_stock + 50,
        "in_stock_count": in_stock,
        "out_of_stock_count": 50,
        "scraped_at": f"{date_str}T00:00:00Z",
    }
    (nursery_dir / f"{date_str}.json").write_text(json.dumps(payload))


def _setup_fixture(root: Path, yesterday_stock: int, today_stock: int, name="Big Nursery"):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    nursery = root / "big-nursery"
    _write_snapshot(nursery, yesterday, yesterday_stock, name)
    _write_snapshot(nursery, today, today_stock, name)
    # detect_surges loads today via latest.json
    (nursery / "latest.json").write_text((nursery / f"{today}.json").read_text())


class ThresholdLogic(unittest.TestCase):
    """Both 20% AND 10+ items must be true for an alert to trigger."""

    def test_large_nursery_small_pct_does_not_fire(self):
        # Ladybird-style: 1692 -> 1768 is +76 (+4%). 76 >= 10 but 4 < 20.
        # Old (OR) logic fired; new (AND) logic should not.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _setup_fixture(root, yesterday_stock=1692, today_stock=1768)
            self.assertEqual(dss.detect_surges(root), [])

    def test_small_nursery_high_pct_low_abs_does_not_fire(self):
        # Tiny nursery: 5 -> 8 is +3 (+60%). 60 >= 20 but 3 < 10.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _setup_fixture(root, yesterday_stock=5, today_stock=8)
            self.assertEqual(dss.detect_surges(root), [])

    def test_real_surge_fires(self):
        # 50 -> 80 is +30 (+60%). Both thresholds met.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _setup_fixture(root, yesterday_stock=50, today_stock=80)
            surges = dss.detect_surges(root)
            self.assertEqual(len(surges), 1)
            self.assertEqual(surges[0]["abs_change"], 30)
            self.assertEqual(surges[0]["direction"], "up")

    def test_real_drop_fires(self):
        # 100 -> 70 is -30 (-30%). Both thresholds met.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _setup_fixture(root, yesterday_stock=100, today_stock=70)
            surges = dss.detect_surges(root)
            self.assertEqual(len(surges), 1)
            self.assertEqual(surges[0]["direction"], "down")


class IdempotencyLog(unittest.TestCase):
    """The send marker prevents duplicate emails on the same UTC day."""

    def test_load_returns_empty_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            dss.SENDS_LOG_FILE = Path(td) / "missing.json"
            self.assertEqual(dss.load_sends_log(), {})

    def test_load_returns_empty_on_corrupt_json(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "log.json"
            log.write_text("{not valid json")
            dss.SENDS_LOG_FILE = log
            self.assertEqual(dss.load_sends_log(), {})

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            dss.SENDS_LOG_FILE = Path(td) / "log.json"
            dss.save_sends_log({"last_sent": "2026-04-25"})
            self.assertEqual(dss.load_sends_log(), {"last_sent": "2026-04-25"})


if __name__ == "__main__":
    unittest.main()
