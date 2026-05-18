"""
Tests for tools/autonomous/uptime_monitor.py.

Regression coverage for a bug (2026-05-18):
  uptime_state.json was truncated to 0 bytes on 2026-03-19. load_state()
  called json.load() unconditionally and crashed with JSONDecodeError,
  so the monitor logged ~34k tracebacks and ran zero checks for two
  months. load_state() now treats empty/corrupt state as a fresh start.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTONOMOUS = REPO_ROOT / "tools" / "autonomous"


def load_uptime_monitor():
    # notify is imported at module top; stub it so the test doesn't need Resend creds.
    sys.modules.setdefault("notify", mock.MagicMock())
    spec = importlib.util.spec_from_file_location(
        "uptime_monitor", AUTONOMOUS / "uptime_monitor.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LoadStateTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_uptime_monitor()
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.path_patch = mock.patch.object(self.mod, "STATE_PATH", self.tmp.name)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_missing_file_returns_empty(self):
        Path(self.tmp.name).unlink()
        self.assertEqual(self.mod.load_state(), {})

    def test_empty_file_returns_empty(self):
        # Regression: the file existed but was 0 bytes; json.load() raised.
        Path(self.tmp.name).write_text("")
        self.assertEqual(self.mod.load_state(), {})

    def test_corrupt_file_returns_empty(self):
        Path(self.tmp.name).write_text("{not valid json")
        self.assertEqual(self.mod.load_state(), {})

    def test_valid_file_returns_parsed(self):
        Path(self.tmp.name).write_text('{"treestock": {"status": "up"}}')
        self.assertEqual(self.mod.load_state(), {"treestock": {"status": "up"}})


if __name__ == "__main__":
    unittest.main()
