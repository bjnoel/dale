"""Tests for the nursery relationship register (DAL-80).

The register is hand-edited data plus a CLI that mutates it, so the risks are
(a) the data drifting out of sync with the nurseries we actually monitor,
(b) a mutation silently corrupting a record, and (c) the referral join failing
open and reporting 0 clicks as if that were a measurement.
"""

import copy
import json
import os
import sys
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools", "autonomous"))
sys.path.insert(0, os.path.join(REPO, "tools", "scrapers"))

import nursery_crm as crm  # noqa: E402


class TestRegisterData(unittest.TestCase):
    def setUp(self):
        self.reg = crm.load_register()

    def test_register_validates(self):
        self.assertEqual([], crm.validate(self.reg))

    def test_covers_exactly_the_monitored_nurseries(self):
        """A nursery we track but cannot contact is the gap this file closes."""
        from stocklib.registry import NURSERIES
        self.assertEqual({n.key for n in NURSERIES},
                         {n["key"] for n in self.reg["nurseries"]})

    def test_domains_are_unique(self):
        """Two nurseries sharing a domain would double-count referral clicks."""
        domains = [n["domain"] for n in self.reg["nurseries"]]
        self.assertEqual(len(domains), len(set(domains)))

    def test_every_touch_cites_its_evidence(self):
        """Recorded history must be traceable, not remembered."""
        for n in self.reg["nurseries"]:
            for t in n.get("touches", []):
                self.assertTrue(t.get("evidence"),
                                f"{n['key']} touch {t['date']} has no evidence")

    def test_no_nursery_claims_a_reply_without_an_outbound_touch_first(self):
        for n in self.reg["nurseries"]:
            touches = n.get("touches", [])
            if touches:
                self.assertEqual("out", touches[0]["direction"],
                                 f"{n['key']} history starts with an inbound reply")

    def test_contact_route_recorded_for_all_but_the_known_gaps(self):
        missing = [n["key"] for n in self.reg["nurseries"]
                   if crm.contact_route(n) == "NONE"]
        # Primal Fruits is deliberately blank: Benedict contacts Cyrus on
        # WhatsApp and must not be cold-emailed.
        self.assertNotIn("ladybird", missing)
        for key in missing:
            n = crm.find(self.reg, key)
            self.assertTrue(n.get("open_action") or n["status"] == "personal",
                            f"{key} has no contact route and nobody owns fixing it")

    def test_no_em_dashes_in_register_text(self):
        """CLAUDE.md rule 4. Notes get pasted into outreach copy."""
        self.assertNotIn("\u2014", json.dumps(self.reg))


class TestValidate(unittest.TestCase):
    def base(self, **over):
        n = {"key": "x", "name": "X", "domain": "x.com.au", "status": "not_contacted",
             "touches": [], "open_action": None}
        n.update(over)
        return {"nurseries": [n]}

    def test_rejects_unknown_status(self):
        self.assertTrue(crm.validate(self.base(status="lukewarm")))

    def test_rejects_unnormalised_domain(self):
        """'www.x.com.au' would never match Plausible's normalised host."""
        self.assertTrue(crm.validate(self.base(domain="www.x.com.au")))

    def test_rejects_missing_domain(self):
        self.assertTrue(crm.validate(self.base(domain="")))

    def test_rejects_touches_with_not_contacted_status(self):
        t = [{"date": "2026-01-01", "direction": "out"}]
        self.assertTrue(crm.validate(self.base(touches=t)))

    def test_rejects_warm_status_with_no_touches(self):
        self.assertTrue(crm.validate(self.base(status="warm")))

    def test_rejects_unparseable_touch_date(self):
        t = [{"date": "last March", "direction": "out"}]
        self.assertTrue(crm.validate(self.base(status="contacted", touches=t)))

    def test_rejects_action_owned_by_nobody(self):
        act = {"owner": "the nursery", "what": "reply", "since": "2026-01-01"}
        self.assertTrue(crm.validate(self.base(open_action=act)))

    def test_rejects_duplicate_keys(self):
        reg = self.base()
        reg["nurseries"].append(copy.deepcopy(reg["nurseries"][0]))
        self.assertIn("duplicate nursery keys", crm.validate(reg))


class TestLogging(unittest.TestCase):
    def setUp(self):
        self.reg = {"nurseries": [
            {"key": "x", "name": "X", "domain": "x.com.au",
             "status": "not_contacted", "touches": [], "open_action": None}]}
        self.saved = []
        patcher = mock.patch.object(crm, "save_register",
                                    lambda r, *a, **k: self.saved.append(r))
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_log(self, *argv):
        with mock.patch.object(crm, "load_register", lambda *a, **k: self.reg):
            return crm.main(list(argv))

    def test_outbound_touch_moves_not_contacted_to_contacted(self):
        self.run_log("log", "x", "--direction", "out", "--summary", "hi",
                     "--date", "2026-07-30")
        self.assertEqual("contacted", self.reg["nurseries"][0]["status"])

    def test_inbound_touch_moves_contacted_to_warm(self):
        self.run_log("log", "x", "--direction", "out", "--summary", "hi",
                     "--date", "2026-07-30")
        self.run_log("log", "x", "--direction", "in", "--summary", "thanks",
                     "--date", "2026-08-01")
        self.assertEqual("warm", self.reg["nurseries"][0]["status"])

    def test_inbound_touch_does_not_downgrade_a_personal_relationship(self):
        self.reg["nurseries"][0]["status"] = "personal"
        self.run_log("log", "x", "--direction", "in", "--summary", "hi",
                     "--date", "2026-07-30")
        self.assertEqual("personal", self.reg["nurseries"][0]["status"])

    def test_touches_stay_in_date_order_when_backfilled(self):
        self.run_log("log", "x", "--direction", "out", "--summary", "b",
                     "--date", "2026-07-30")
        self.run_log("log", "x", "--direction", "out", "--summary", "a",
                     "--date", "2026-03-01")
        dates = [t["date"] for t in self.reg["nurseries"][0]["touches"]]
        self.assertEqual(sorted(dates), dates)

    def test_unknown_key_raises_rather_than_creating_a_record(self):
        with self.assertRaises(KeyError):
            self.run_log("log", "nope", "--direction", "out", "--summary", "hi")

    def test_set_can_clear_an_outstanding_action(self):
        self.reg["nurseries"][0]["open_action"] = {
            "owner": "dale", "what": "find email", "since": "2026-07-30"}
        self.run_log("set", "x", "--clear-action")
        self.assertIsNone(self.reg["nurseries"][0]["open_action"])


class TestReferralJoin(unittest.TestCase):
    def test_domains_are_normalised_consistently(self):
        for raw in ("https://www.daleysfruit.com.au/x?y=1", "www.daleysfruit.com.au",
                    "DaleysFruit.com.au", "daleysfruit.com.au:443"):
            self.assertEqual("daleysfruit.com.au", crm.normalise_domain(raw))

    def test_breakdown_is_paginated(self):
        """A single page silently undercounts: the breakdown is per product URL
        and there are ~1,000 distinct ones a month. This is the bug that made
        an unpaginated query report 516 clicks instead of 1,245."""
        pages = [
            {"results": [{"url": f"https://a.com/{i}", "events": 1, "visitors": 1}
                         for i in range(1000)]},
            {"results": [{"url": "https://a.com/last", "events": 5, "visitors": 5}]},
        ]
        calls = []

        def fake_get(base, token, endpoint, params):
            calls.append(params["page"])
            return pages[params["page"] - 1] if params["page"] <= len(pages) else {"results": []}

        with mock.patch.dict(sys.modules, {"plausible_stats": mock.MagicMock(
                load_plausible_config=lambda: ("t", "http://x"),
                api_get=fake_get)}):
            agg = crm.outbound_clicks("30d")
        self.assertEqual([1, 2], calls)
        self.assertEqual(1005, agg["a.com"]["clicks"])

    def test_missing_plausible_config_degrades_instead_of_crashing(self):
        def boom():
            raise ValueError("no token")
        with mock.patch.dict(sys.modules, {"plausible_stats": mock.MagicMock(
                load_plausible_config=boom)}):
            self.assertEqual({}, crm.outbound_clicks("30d"))

    def test_filters_on_the_outbound_goal(self):
        """Without the goal filter this would count every pageview."""
        seen = {}

        def fake_get(base, token, endpoint, params):
            seen.update(params)
            return {"results": []}
        with mock.patch.dict(sys.modules, {"plausible_stats": mock.MagicMock(
                load_plausible_config=lambda: ("t", "http://x"), api_get=fake_get)}):
            crm.outbound_clicks("30d")
        self.assertEqual("event:name==Outbound Link: Click", seen["filters"])
        self.assertEqual("event:props:url", seen["property"])


if __name__ == "__main__":
    unittest.main()
