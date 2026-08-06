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


class TestApplyTouch(unittest.TestCase):
    """Shared by `log` and `merge-inbound`, so a hand-logged touch and a BCC'd
    one must behave identically."""

    def _n(self, status="not_contacted", touches=None):
        return {"key": "k", "name": "N", "status": status,
                "touches": list(touches or [])}

    def test_outbound_advances_not_contacted_to_contacted(self):
        n = self._n("not_contacted")
        crm.apply_touch(n, {"date": "2026-08-06", "direction": "out",
                            "channel": "email", "by": "benedict", "summary": "s"})
        self.assertEqual(n["status"], "contacted")

    def test_inbound_advances_contacted_to_warm(self):
        n = self._n("contacted")
        crm.apply_touch(n, {"date": "2026-08-06", "direction": "in",
                            "channel": "email", "by": "k", "summary": "s"})
        self.assertEqual(n["status"], "warm")

    def test_warm_is_not_downgraded(self):
        n = self._n("warm")
        crm.apply_touch(n, {"date": "2026-08-06", "direction": "out",
                            "channel": "email", "by": "benedict", "summary": "s"})
        self.assertEqual(n["status"], "warm")

    def test_touches_stay_sorted_by_date(self):
        n = self._n(touches=[{"date": "2026-08-01", "direction": "out",
                              "summary": "old"}])
        crm.apply_touch(n, {"date": "2026-07-01", "direction": "out",
                            "channel": "email", "by": "b", "summary": "older"})
        self.assertEqual([t["date"] for t in n["touches"]],
                         ["2026-07-01", "2026-08-01"])

    def test_duplicate_evidence_is_refused(self):
        n = self._n(touches=[{"date": "2026-08-01", "direction": "out",
                              "summary": "x", "evidence": "resend:e_1"}])
        added = crm.apply_touch(n, {"date": "2026-08-06", "direction": "out",
                                    "channel": "email", "by": "b",
                                    "summary": "y", "evidence": "resend:e_1"})
        self.assertFalse(added)
        self.assertEqual(len(n["touches"]), 1)

    def test_touch_without_evidence_is_always_added(self):
        n = self._n(touches=[{"date": "2026-08-01", "direction": "out",
                              "summary": "x"}])
        self.assertTrue(crm.apply_touch(n, {
            "date": "2026-08-06", "direction": "out", "channel": "email",
            "by": "b", "summary": "y"}))


class TestMergeInbound(unittest.TestCase):
    """Folds the webhook's JSONL into the repo register. The webhook cannot
    write the register itself: deploy.sh copies the repo copy over the data-dir
    copy every hourly deploy, so anything written there is gone within the hour.
    """

    def setUp(self):
        import tempfile
        from pathlib import Path
        self.tmp = Path(tempfile.mkdtemp())
        self.log = self.tmp / "inbound.jsonl"
        self.reg = {"nurseries": [
            {"key": "daleys", "name": "Daleys", "domain": "d.com.au",
             "status": "not_contacted", "touches": []}]}
        self.saved = []
        self._orig_save = crm.save_register
        crm.save_register = lambda r, path=None: self.saved.append(copy.deepcopy(r))

    def tearDown(self):
        crm.save_register = self._orig_save

    def _args(self, dry_run=False):
        class A:
            pass
        a = A()
        a.log = str(self.log)
        a.dry_run = dry_run
        return a

    def _write(self, *records):
        self.log.write_text("".join(json.dumps(r) + "\n" for r in records))

    def _record(self, evidence="resend:e_1", nursery="daleys", merged=False):
        return {"nursery": nursery, "date": "2026-08-06", "direction": "out",
                "channel": "email", "by": "benedict", "summary": "Scion wood",
                "evidence": evidence, "merged": merged}

    def test_merges_an_unmerged_record(self):
        self._write(self._record())
        crm.cmd_merge_inbound(self.reg, self._args())
        self.assertEqual(len(self.reg["nurseries"][0]["touches"]), 1)
        self.assertEqual(self.reg["nurseries"][0]["status"], "contacted")

    def test_already_merged_records_are_skipped(self):
        self._write(self._record(merged=True))
        crm.cmd_merge_inbound(self.reg, self._args())
        self.assertEqual(self.reg["nurseries"][0]["touches"], [])

    def test_log_is_marked_merged_so_a_rerun_is_a_noop(self):
        self._write(self._record())
        crm.cmd_merge_inbound(self.reg, self._args())
        on_disk = [json.loads(l) for l in self.log.read_text().splitlines() if l]
        self.assertTrue(all(r["merged"] for r in on_disk))

    def test_rerun_adds_nothing(self):
        self._write(self._record())
        crm.cmd_merge_inbound(self.reg, self._args())
        crm.cmd_merge_inbound(self.reg, self._args())
        self.assertEqual(len(self.reg["nurseries"][0]["touches"]), 1)

    def test_dry_run_changes_nothing_on_disk(self):
        self._write(self._record())
        crm.cmd_merge_inbound(self.reg, self._args(dry_run=True))
        on_disk = [json.loads(l) for l in self.log.read_text().splitlines() if l]
        self.assertFalse(on_disk[0]["merged"])
        self.assertEqual(self.saved, [])

    def test_unknown_nursery_key_is_left_unmerged_not_dropped(self):
        self._write(self._record(nursery="vanished"))
        crm.cmd_merge_inbound(self.reg, self._args())
        on_disk = [json.loads(l) for l in self.log.read_text().splitlines() if l]
        self.assertFalse(on_disk[0]["merged"])

    def test_malformed_lines_do_not_stop_the_merge(self):
        self.log.write_text("{not json\n" + json.dumps(self._record()) + "\n")
        crm.cmd_merge_inbound(self.reg, self._args())
        self.assertEqual(len(self.reg["nurseries"][0]["touches"]), 1)

    def test_missing_log_is_not_an_error(self):
        self.assertEqual(
            crm.cmd_merge_inbound(self.reg, self._args()), 0)


if __name__ == "__main__":
    unittest.main()
