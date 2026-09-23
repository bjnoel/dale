"""stocklib.jsonio.atomic_write_json: a failed write never tears the target."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "scrapers"))

from stocklib.jsonio import atomic_write_json  # noqa: E402


class AtomicWriteJson(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.target = self.dir / "latest.json"

    def test_round_trip(self):
        atomic_write_json(self.target, {"products": [1, 2]})
        self.assertEqual(json.loads(self.target.read_text()), {"products": [1, 2]})

    def test_failure_mid_dump_keeps_the_old_file_and_leaves_no_temp(self):
        atomic_write_json(self.target, {"day": "yesterday"})

        class Boom:
            pass  # json.dump raises TypeError partway through the object

        with self.assertRaises(TypeError):
            atomic_write_json(self.target, {"day": "today", "x": Boom()})
        self.assertEqual(json.loads(self.target.read_text()), {"day": "yesterday"})
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["latest.json"])

    def test_creates_parent_dir(self):
        p = self.dir / "new-nursery" / "2026-09-23.json"
        atomic_write_json(p, [])
        self.assertTrue(p.exists())


if __name__ == "__main__":
    unittest.main()
