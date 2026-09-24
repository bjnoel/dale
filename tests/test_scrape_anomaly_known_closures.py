"""
A nursery a human has marked closed (registry dormant_note) must not email
"failed" every night. Aus Nurseries went on holiday 2026-09-20 (reopening
2026-10-20) and produced four identical alert mails in four days.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "scrapers"))

import detect_scrape_anomalies as dsa  # noqa: E402


def _rec(nursery, ok, products=0, **kw):
    r = {"nursery": nursery, "ok": ok, "products": products, "in_stock": 0,
         "http_403": 0, "http_429": 0, "source": "shopify",
         "error": None if ok else "page 1 failed after retries; snapshot aborted"}
    r.update(kw)
    return r


def _nights(n, *recs):
    return [list(recs) for _ in range(n)]


class KnownClosures(unittest.TestCase):
    def test_the_aus_nurseries_nights_send_nothing(self):
        days = _nights(dsa.STREAK_DAYS, _rec("ausnurseries", False),
                       _rec("ladybird", True, 7300))
        found = dsa.detect_anomalies(days)
        self.assertEqual({a["type"] for a in found}, {"failed", "failure_streak"})
        alertable, muted = dsa.split_acknowledged(found, {"ausnurseries"})
        self.assertEqual(alertable, [])
        self.assertEqual(len(muted), 2)

    def test_unacknowledged_failure_still_alerts(self):
        found = dsa.detect_anomalies(_nights(dsa.STREAK_DAYS, _rec("garden-world", False)))
        alertable, _ = dsa.split_acknowledged(found, {"ausnurseries"})
        self.assertTrue(alertable)

    def test_other_anomaly_types_are_never_muted(self):
        blocked = {"nursery": "ausnurseries", "type": "blocked", "detail": "3x HTTP 403"}
        alertable, muted = dsa.split_acknowledged([blocked], {"ausnurseries"})
        self.assertEqual(alertable, [blocked])
        self.assertEqual(muted, [])

    def test_muted_nursery_is_named_in_a_real_alert(self):
        real = {"nursery": "ladybird", "type": "count_swing", "detail": "7300 -> 750"}
        quiet = {"nursery": "ausnurseries", "type": "failed", "detail": "401"}
        _, html, text = dsa.build_email([real], "2026-09-24", [quiet])
        self.assertIn("Known closures, not alerted: ausnurseries", text)
        self.assertIn("ausnurseries", html)


class NoteOnlyMutesAContinuingFailure(unittest.TestCase):
    def test_note_with_failed_yesterday_is_acknowledged(self):
        y = {"ausnurseries": _rec("ausnurseries", False)}
        self.assertIn("ausnurseries", dsa.acknowledged_closures(y))

    def test_first_failure_after_a_good_night_is_not_muted(self):
        # Heritage: note still set, but scraping fine for weeks. If it breaks,
        # the first night must reach Benedict.
        y = {"heritage-fruit-trees": _rec("heritage-fruit-trees", True, 378)}
        self.assertNotIn("heritage-fruit-trees", dsa.acknowledged_closures(y))

    def test_no_history_is_not_muted(self):
        self.assertEqual(dsa.acknowledged_closures({}), set())


if __name__ == "__main__":
    unittest.main()
