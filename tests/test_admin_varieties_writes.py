"""
The admin write path (DAL-284) and the curation queue (DAL-285).

This is the first endpoint on the site that changes anything from a browser, so
the tests are weighted towards the ways it must REFUSE rather than the happy
path. In rough order of how much damage the absence of each would do:

  - a live slug cannot be redirected from here, ever (its name is recomputed
    nightly, so the write would be undone by morning and the reviewer would
    never learn why)
  - a stale stamp is refused, not merged
  - a target that is not a live page is refused (it would serve a 404)
  - an alias chain is refused (canonical_cultivar applies the map once)
  - nothing in the write path touches the ledger or the override file directly

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import admin_view
from stocklib import admin_decisions as ad


def entry(**over):
    base = {
        "state": "live", "first_seen": "2026-03-05", "last_seen": "2026-08-17",
        "live_days": 100, "in_stock_days": 50, "last_in_stock": "2026-08-17",
        "since": "2026-03-05", "seeded": False, "title": "", "species": "Avocado",
        "species_slug": "avocado", "variety": "", "rows": [], "rows_as_of": None,
        "redirect_to": None, "retired_reason": None, "see_also": [],
        "absent_nights": 0,
    }
    base.update(over)
    return base


PAGES = {
    "avocado-hass": entry(rows=[{"nursery_key": "daleys", "available": True}]),
    "avocado-hass-potted": entry(rows=[{"nursery_key": "exotica", "available": True}]),
    "avocado-hass-type-a": entry(state="redirect", redirect_to="avocado-hass"),
    "avocado-gone": entry(state="tombstone"),
    "avocado-left": entry(state="retired", retired_reason="denied"),
}


class WriteHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        led = self.data / "page-ledger"
        led.mkdir()
        (led / "variety.json").write_text(json.dumps(
            {"schema": 1, "family": "variety", "updated": "2026-08-17",
             "pages": PAGES}))

    def tearDown(self):
        self.tmp.cleanup()

    def stamp(self, slug):
        e = PAGES[slug]
        return admin_view.row_stamp({"state": e["state"],
                                     "redirect_to": e["redirect_to"]})

    def apply(self, action, rows, by="b@bjnoel.com"):
        return admin_view.apply_decisions({"action": action, "rows": rows},
                                          by=by, data_dir=self.data)

    def store(self):
        return ad.load_decisions(ad.decisions_path(self.data))

    def with_overrides(self, alias):
        """Pretend variety_overrides.json already carries these aliases.

        That file sits beside the code rather than in data_dir, so the write
        path reads it directly. Patching the loader keeps these tests off the
        live curation file, which has four real aliases in it and would make
        them pass or fail depending on what was folded last week.
        """
        real = admin_view.load_overrides
        admin_view.load_overrides = lambda: {"deny": [], "alias": dict(alias),
                                             "error": ""}
        self.addCleanup(setattr, admin_view, "load_overrides", real)


class RefusalTests(WriteHarness):
    def test_a_live_slug_cannot_be_redirected_and_the_error_says_why(self):
        """The single most important refusal here. `canonical_cultivar`
        recomputes a live slug from the nursery's product title every run, so a
        redirect written against one is undone the same night. A reviewer who
        was allowed to set it would watch it silently revert and conclude the
        admin page is broken."""
        with self.assertRaises(admin_view.DecisionRefused) as cm:
            self.apply("retarget", [{"slug": "avocado-hass-potted",
                                     "target": "avocado-hass",
                                     "stamp": self.stamp("avocado-hass-potted")}])
        self.assertIn("live", str(cm.exception))
        self.assertIn("alias", str(cm.exception))

    def test_a_stale_stamp_is_refused_not_merged(self):
        with self.assertRaises(admin_view.DecisionRefused) as cm:
            self.apply("retarget", [{"slug": "avocado-hass-type-a",
                                     "target": "avocado-hass",
                                     "stamp": "deadbeefcafe"}])
        self.assertIn("changed since", str(cm.exception))

    def test_a_target_that_is_not_a_live_page_is_refused(self):
        for target in ("avocado-gone", "avocado-nonexistent", ""):
            with self.subTest(target=target):
                with self.assertRaises(admin_view.DecisionRefused) as cm:
                    self.apply("retarget", [{"slug": "avocado-hass-type-a",
                                             "target": target,
                                             "stamp": self.stamp("avocado-hass-type-a")}])
                self.assertIn("not a live page", str(cm.exception))

    def test_an_action_cannot_apply_to_a_state_it_does_not_fit(self):
        """A tombstone has no target to retarget. Silently treating it as
        `to_redirect` would be the UI guessing at intent."""
        with self.assertRaises(admin_view.DecisionRefused) as cm:
            self.apply("retarget", [{"slug": "avocado-gone",
                                     "target": "avocado-hass",
                                     "stamp": self.stamp("avocado-gone")}])
        self.assertIn("tombstone", str(cm.exception))

    def test_a_slug_cannot_point_at_itself(self):
        with self.assertRaises(admin_view.DecisionRefused):
            self.apply("alias", [{"slug": "avocado-hass-potted",
                                  "target": "avocado-hass-potted"}])

    def test_an_alias_chain_is_refused(self):
        """canonical_cultivar applies the override map ONCE, with no chain
        resolution, so A -> B where B -> C leaves A sitting at B. A queue that
        accepted both would produce a map that does half of what it reads as."""
        self.apply("alias", [{"slug": "avocado-hass-potted",
                              "target": "avocado-hass"}])
        with self.assertRaises(admin_view.DecisionRefused) as cm:
            self.apply("alias", [{"slug": "avocado-hass-type-a",
                                  "target": "avocado-hass-potted"}])
        self.assertIn("already queued", str(cm.exception))

    def test_a_chain_inside_one_batch_is_refused(self):
        """The hole the DAL-286 sections opened. The chain guard read only the
        stored queue, which was enough while aliases arrived one row at a time
        from the noise section. The sibling and near-miss sections submit whole
        ticked groups, and ticking the mango-bambaroo group offers
        `-kp -> bambaroo` alongside `-kp-l -> -kp`: neither is in the store
        during validation, so both landed, and promote_curation.merge then
        dropped one of them on an ordering nobody chose."""
        with self.assertRaises(admin_view.DecisionRefused) as cm:
            self.apply("alias", [
                {"slug": "avocado-hass-potted", "target": "avocado-hass"},
                {"slug": "avocado-hass-type-a", "target": "avocado-hass-potted"},
            ])
        self.assertIn("not chained", str(cm.exception))
        self.assertEqual(self.store()["curation_pending"], [])

    def test_a_chain_is_refused_from_either_direction(self):
        """A -> B queued, then B -> C. Same broken map, and the guard only
        looked for the other direction."""
        self.apply("alias", [{"slug": "avocado-hass-type-a",
                              "target": "avocado-hass-potted"}])
        with self.assertRaises(admin_view.DecisionRefused) as cm:
            self.apply("alias", [{"slug": "avocado-hass-potted",
                                  "target": "avocado-hass"}])
        self.assertIn("avocado-hass-type-a", str(cm.exception))
        self.assertEqual(len(self.store()["curation_pending"]), 1)

    def test_one_slug_cannot_be_ticked_for_two_destinations(self):
        """The sibling queue lists a slug under every base it is a prefix-child
        of, so mango-bambaroo-kp-l appears under mango-bambaroo AND under
        mango-bambaroo-kp. Ticking both rows used to be accepted silently, and
        `queue_curation` replaces by `from`, so whichever the loop reached last
        won. The reviewer asked for two destinations and got one chosen by
        array order."""
        with self.assertRaises(admin_view.DecisionRefused) as cm:
            self.apply("alias", [
                {"slug": "avocado-hass-type-a", "target": "avocado-hass"},
                {"slug": "avocado-hass-type-a", "target": "avocado-hass-potted"},
            ])
        self.assertIn("one destination", str(cm.exception))
        self.assertEqual(self.store()["curation_pending"], [])

    def test_the_same_row_twice_is_not_a_clash(self):
        """Identical rows are a double-tick, not two answers."""
        res = self.apply("alias", [
            {"slug": "avocado-hass-potted", "target": "avocado-hass"},
            {"slug": "avocado-hass-potted", "target": "avocado-hass"},
        ])
        self.assertEqual(res["applied"], 2)
        self.assertEqual(len(self.store()["curation_pending"]), 1)

    def test_redeciding_an_already_queued_slug_is_allowed(self):
        """Different from a clash: the rows did not arrive together, so the
        second is a correction and wins, as record_redirect documents."""
        self.apply("alias", [{"slug": "avocado-hass-type-a",
                              "target": "avocado-hass"}])
        self.apply("alias", [{"slug": "avocado-hass-type-a",
                              "target": "avocado-hass-potted"}])
        self.assertEqual(
            {r["from"]: r["to"] for r in self.store()["curation_pending"]},
            {"avocado-hass-type-a": "avocado-hass-potted"})

    def test_two_slugs_folding_onto_one_target_is_not_a_chain(self):
        """The bambaroo shape itself. Both ASP-WA listings fold into
        mango-bambaroo, and refusing the second would make the section useless
        for the case it was built for."""
        res = self.apply("alias", [
            {"slug": "avocado-hass-potted", "target": "avocado-hass"},
            {"slug": "avocado-hass-type-a", "target": "avocado-hass"},
        ])
        self.assertEqual(res["applied"], 2)
        self.assertEqual(
            {r["from"]: r["to"] for r in self.store()["curation_pending"]},
            {"avocado-hass-potted": "avocado-hass",
             "avocado-hass-type-a": "avocado-hass"})

    def test_an_alias_onto_an_already_committed_alias_is_refused(self):
        """The chain guard only ever read the queue, so the hazard vanished from
        view the moment promote_curation.py ran. `mango-bambaroo-kp ->
        mango-bambaroo` lands in the file tonight; a fold onto
        `mango-bambaroo-kp` tomorrow would have been accepted, and
        canonical_cultivar applies the map once, so those products would sit on
        a slug the build no longer produces."""
        self.with_overrides({"avocado-hass-potted": "avocado-hass"})
        with self.assertRaises(admin_view.DecisionRefused) as cm:
            self.apply("alias", [{"slug": "avocado-hass-type-a",
                                  "target": "avocado-hass-potted"}])
        msg = str(cm.exception)
        self.assertIn("already aliased", msg)
        self.assertIn("variety_overrides.json", msg)
        # Naming the slug to use instead is the whole value of the refusal.
        self.assertIn("point this at avocado-hass ", msg)
        self.assertEqual(self.store()["curation_pending"], [])

    def test_a_committed_alias_pointing_at_this_slug_is_refused(self):
        """The other direction. A -> B in the file, then B -> C, and A is left
        on a page that has moved."""
        self.with_overrides({"avocado-hass-type-a": "avocado-hass-potted"})
        with self.assertRaises(admin_view.DecisionRefused) as cm:
            self.apply("alias", [{"slug": "avocado-hass-potted",
                                  "target": "avocado-hass"}])
        self.assertIn("avocado-hass-type-a", str(cm.exception))
        self.assertEqual(self.store()["curation_pending"], [])

    def test_an_unrelated_committed_alias_does_not_block_anything(self):
        """The file grows a row every time something is folded, so a guard that
        was even slightly too wide would make the queue harder to empty the more
        of it had been emptied."""
        self.with_overrides({"apple-2-way-gala": "apple-2way-gala"})
        res = self.apply("alias", [{"slug": "avocado-hass-potted",
                                    "target": "avocado-hass"}])
        self.assertEqual(res["applied"], 1)

    def test_a_batch_is_all_or_nothing(self):
        """Half of 126 rows landing is worse than none: nobody can tell which
        half without reading the file."""
        with self.assertRaises(admin_view.DecisionRefused):
            self.apply("retarget", [
                {"slug": "avocado-hass-type-a", "target": "avocado-hass",
                 "stamp": self.stamp("avocado-hass-type-a")},
                {"slug": "avocado-hass-potted", "target": "avocado-hass",
                 "stamp": self.stamp("avocado-hass-potted")},   # live, refused
            ])
        self.assertEqual(self.store()["redirects"], {})

    def test_unknown_actions_and_empty_batches(self):
        for payload in ({"action": "delete", "rows": [{"slug": "x"}]},
                        {"action": "retarget", "rows": []},
                        {"action": "retarget", "rows": "nope"}):
            with self.subTest(payload=payload):
                with self.assertRaises(admin_view.DecisionRefused):
                    admin_view.apply_decisions(payload, by="x", data_dir=self.data)


class AcceptedTests(WriteHarness):
    def test_retarget_records_an_intent_and_nothing_else(self):
        out = self.apply("retarget", [{"slug": "avocado-hass-type-a",
                                       "target": "avocado-hass",
                                       "stamp": self.stamp("avocado-hass-type-a")}])
        self.assertEqual(out["applied"], 1)
        self.assertIn("00:00 UTC", out["effective"])
        self.assertEqual(self.store()["redirects"]["avocado-hass-type-a"],
                         {"action": "retarget", "target": "avocado-hass",
                          "by": "b@bjnoel.com",
                          "at": self.store()["redirects"]["avocado-hass-type-a"]["at"]})

    def test_the_ledger_is_not_touched(self):
        """Both builders rewrite the whole ledger nightly, so a web write to it
        is gone by morning. The intent file is the only shape that survives."""
        before = (self.data / "page-ledger" / "variety.json").read_bytes()
        self.apply("tombstone", [{"slug": "avocado-hass-type-a",
                                  "stamp": self.stamp("avocado-hass-type-a")}])
        self.assertEqual((self.data / "page-ledger" / "variety.json").read_bytes(),
                         before)

    def test_a_tombstone_can_become_a_redirect_when_a_successor_turns_up(self):
        out = self.apply("redirect", [{"slug": "avocado-gone",
                                       "target": "avocado-hass",
                                       "stamp": self.stamp("avocado-gone")}])
        self.assertEqual(out["applied"], 1)

    def test_a_retired_page_can_go_either_way(self):
        for action in ("tombstone", "redirect"):
            with self.subTest(action=action):
                self.apply(action, [{"slug": "avocado-left",
                                     "target": "avocado-hass",
                                     "stamp": self.stamp("avocado-left")}])

    def test_deciding_twice_replaces_rather_than_stacks(self):
        for target in ("avocado-hass", "avocado-hass"):
            self.apply("retarget", [{"slug": "avocado-hass-type-a",
                                     "target": target,
                                     "stamp": self.stamp("avocado-hass-type-a")}])
        self.assertEqual(len(self.store()["redirects"]), 1)

    def test_a_queued_decision_can_be_cancelled(self):
        self.apply("retarget", [{"slug": "avocado-hass-type-a",
                                 "target": "avocado-hass",
                                 "stamp": self.stamp("avocado-hass-type-a")}])
        out = self.apply("unqueue-redirect", [{"slug": "avocado-hass-type-a"}])
        self.assertEqual(out["applied"], 1)
        self.assertEqual(self.store()["redirects"], {})

    def test_sibling_dismissal_is_order_independent_and_reversible(self):
        self.apply("distinct", [{"base": "avocado-hass",
                                 "other": "avocado-hass-potted"}])
        self.assertIn(ad.sibling_key("avocado-hass-potted", "avocado-hass"),
                      ad.dismissed_pairs(self.store()))
        self.apply("undistinct", [{"base": "avocado-hass-potted",
                                   "other": "avocado-hass"}])
        self.assertEqual(ad.dismissed_pairs(self.store()), set())


class CurationQueueTests(unittest.TestCase):
    """promote_curation.py: the queue becomes a commit, or it becomes nothing."""

    def setUp(self):
        import promote_curation
        self.pc = promote_curation
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_an_alias_chain_never_reaches_the_file(self):
        current = {"deny": [], "alias": {"b": "c"}}
        new, applied, skipped = self.pc.merge(
            current, [{"kind": "alias", "from": "a", "to": "b"}])
        self.assertEqual(applied, [])
        self.assertIn("itself aliased", skipped[0][1])
        self.assertEqual(new["alias"], {"b": "c"})

    def test_aliasing_a_slug_others_point_at_is_refused(self):
        current = {"deny": [], "alias": {"a": "b"}}
        _, applied, skipped = self.pc.merge(
            current, [{"kind": "alias", "from": "b", "to": "c"}])
        self.assertEqual(applied, [])
        self.assertIn("point AT this slug", skipped[0][1])

    def test_a_no_op_row_is_skipped_so_the_commit_is_never_empty(self):
        current = {"deny": ["x"], "alias": {"a": "b"}}
        _, applied, skipped = self.pc.merge(current, [
            {"kind": "alias", "from": "a", "to": "b"},
            {"kind": "deny", "from": "x"},
        ])
        self.assertEqual(applied, [])
        self.assertEqual(len(skipped), 2)

    def test_a_good_batch_lands_sorted(self):
        new, applied, _ = self.pc.merge({"deny": [], "alias": {}}, [
            {"kind": "alias", "from": "z", "to": "t"},
            {"kind": "alias", "from": "a", "to": "t"},
            {"kind": "deny", "from": "junk"},
        ])
        self.assertEqual(list(new["alias"]), ["a", "z"])
        self.assertEqual(new["deny"], ["junk"])
        self.assertEqual(len(applied), 3)

    def test_promotion_keeps_the_parts_of_the_file_it_does_not_own(self):
        """The first --execute would have deleted the 29-line _readme block:
        how alias and deny interact, the instruction to check watch counts
        before aliasing, and "Do NOT run migrate_variety_watch_slugs.py", which
        is what stops live watches being moved onto pages that do not exist.
        Silently, in a commit whose message said it added four aliases.

        Nothing caught it because the alias map was empty, so the destructive
        path had never run in production."""
        path = Path(self.tmp.name) / "overrides.json"
        path.write_text(json.dumps({
            "_readme": ["do not run migrate_variety_watch_slugs.py"],
            "_schema_note": "keep me too",
            "deny": ["apple-mint"], "alias": {}}))
        current = self.pc.load_overrides(path)
        new, applied, _ = self.pc.merge(
            current, [{"kind": "alias", "from": "a", "to": "b"}])
        out = json.loads(self.pc.render(new))
        self.assertEqual(out["_readme"],
                         ["do not run migrate_variety_watch_slugs.py"])
        self.assertEqual(out["_schema_note"], "keep me too")
        self.assertEqual(out["deny"], ["apple-mint"])
        self.assertEqual(out["alias"], {"a": "b"})

    def test_a_row_the_file_already_satisfies_leaves_the_queue(self):
        """A push that failed after the commit left the queue full of rows the
        file already satisfied. Every later run skipped them as
        already-aliased, found nothing to apply, and returned without clearing,
        so the review UI showed "folded into X" forever with no run able to
        undo it. Automating promotion would have made that reachable nightly."""
        decisions = Path(self.tmp.name) / "variety-decisions.json"
        store = ad.empty()
        ad.queue_curation(store, ad.ALIAS, "a", target="b", by="b@bjnoel.com")
        ad.queue_curation(store, ad.DENY, "c", by="b@bjnoel.com")
        ad.save_decisions(decisions, store)

        overrides = {"deny": ["c"], "alias": {"a": "b"}}
        _, applied, skipped = self.pc.merge(overrides,
                                            store["curation_pending"])
        self.assertEqual(applied, [])
        satisfied = {r.get("from") for r, why in skipped
                     if why in self.pc.SATISFIED}
        self.assertEqual(satisfied, {"a", "c"})

        self.assertEqual(self.pc.clear_queue(decisions, satisfied), 2)
        self.assertEqual(ad.load_decisions(decisions)["curation_pending"], [])

    def test_clearing_spares_a_row_queued_while_the_suite_ran(self):
        decisions = Path(self.tmp.name) / "variety-decisions.json"
        store = ad.empty()
        ad.queue_curation(store, ad.ALIAS, "a", target="b")
        ad.save_decisions(decisions, store)
        later = ad.load_decisions(decisions)
        ad.queue_curation(later, ad.ALIAS, "late", target="b")
        ad.save_decisions(decisions, later)

        self.pc.clear_queue(decisions, {"a"})
        self.assertEqual([r["from"] for r in
                          ad.load_decisions(decisions)["curation_pending"]],
                         ["late"])

    def test_the_commit_message_names_who_approved(self):
        msg = self.pc.commit_message([
            {"kind": "alias", "from": "a", "to": "b", "by": "b@bjnoel.com"}])
        self.assertIn("Approved-by: b@bjnoel.com", msg)
        self.assertIn("a -> b", msg)


class SiblingTieringTests(unittest.TestCase):
    def test_noise_only_pairs_are_separated_from_the_ones_needing_judgement(self):
        self.assertEqual(
            admin_view.sibling_tier("almond-all-in-one", "almond-all-in-one-potted"),
            "noise")
        # avocado-hass-lamb is Lamb Hass. The whole reason nothing auto-folds.
        self.assertEqual(
            admin_view.sibling_tier("avocado-hass", "avocado-hass-lamb"),
            "judgement")

    def test_an_age_suffix_is_noise(self):
        self.assertEqual(
            admin_view.sibling_tier("jaboticaba-sabara", "jaboticaba-sabara-2-years-old"),
            "noise")


class NearMissTests(unittest.TestCase):
    """The detector behind DAL-286.

    Bambaroo was live at four slugs and the review page could act on none of
    them. `mango-bambaroo-kp` and `-kp-l` were in the sibling queue with only
    "different plants" to say about them; `mango-bamberoo` was on no queue at
    all, because prefix matching cannot see a substitution in the middle of a
    word.
    """

    def test_the_pair_that_was_invisible_is_found(self):
        self.assertEqual(
            admin_view.near_miss_tier("mango-bambaroo", "mango-bamberoo"),
            "letter")

    def test_a_code_is_tiered_away_from_a_respelling(self):
        """Where the genuinely different selections cluster. Folding
        macadamia-814 into -816 would merge two cultivars into one page and the
        redirect makes it stick."""
        for a, b in (("macadamia-814", "macadamia-816"),
                     ("jackfruit-j33", "jackfruit-j36"),
                     ("pomelo-k13", "pomelo-k15"),
                     ("abiu-e4", "abiu-z4")):
            with self.subTest(pair=(a, b)):
                self.assertEqual(admin_view.near_miss_tier(a, b), "code")

    def test_hyphen_collisions_still_rank_first(self):
        self.assertEqual(
            admin_view.near_miss_tier("almond-self-pollinating-paper-shell",
                                      "almond-self-pollinating-papershell"),
            "hyphen")

    def test_a_hyphen_collision_more_than_one_edit_apart_is_still_found(self):
        """The deletion index that finds the one-edit pairs cannot reach this,
        and the tier it belongs to is the one with no judgement in it. Live pair
        as of 2026-08-17."""
        pairs = admin_view.near_miss_pairs(["peach-flor-da-prince",
                                            "peach-flordaprince"])
        self.assertEqual(pairs, [{"a": "peach-flor-da-prince",
                                  "b": "peach-flordaprince", "tier": "hyphen"}])

    def test_insertions_deletions_and_substitutions_all_count_as_one_edit(self):
        self.assertEqual(admin_view.one_edit_apart("plum-satsuma",
                                                   "plum-satsumas"), "s")
        self.assertEqual(admin_view.one_edit_apart("apple-jonathan",
                                                   "apple-johnathan"), "h")
        self.assertEqual(admin_view.one_edit_apart("lemon-meyer",
                                                   "lemon-myer"), "e")
        # Two edits is not a near miss. `mango-choc-anan` and `mango-chok-anon`
        # are both in the live index and pairing them would be a guess.
        self.assertEqual(admin_view.one_edit_apart("mango-choc-anan",
                                                   "mango-chok-anon"), "")
        self.assertEqual(admin_view.one_edit_apart("apple-gala", "apple-gala"), "")

    def test_unrelated_slugs_are_not_pairs(self):
        self.assertEqual(admin_view.near_miss_tier("apple-gala", "pear-gala"), "")
        self.assertEqual(admin_view.near_miss_tier("fig-black-genoa",
                                                   "fig-white-genoa"), "")

    def test_a_dismissed_pair_does_not_come_back(self):
        """The property that makes the queue finite. Hosui and Kosui are both
        real nashi cultivars, one letter apart, and a reviewer must only have to
        say so once."""
        slugs = ["pear-nashi-hosui", "pear-nashi-kosui", "mango-bambaroo",
                 "mango-bamberoo"]
        self.assertEqual(len(admin_view.near_miss_pairs(slugs)), 2)
        dismissed = {ad.sibling_key("pear-nashi-kosui", "pear-nashi-hosui")}
        left = admin_view.near_miss_pairs(slugs, dismissed)
        self.assertEqual([(p["a"], p["b"]) for p in left],
                         [("mango-bambaroo", "mango-bamberoo")])

    def test_the_backwards_direction_is_flagged(self):
        """Both directions carried their nursery counts and that was not enough:
        `apple-2way-gala-red-delicious (3) -> apple-2-way-gala-red-delicious (1)`
        got picked, retiring a page with three nurseries and 150 live days for
        one with one nursery and 49."""
        facts = {"apple-2way-gala-red-delicious": {"nurseries": 3},
                 "apple-2-way-gala-red-delicious": {"nurseries": 1}}
        backwards = admin_view._fold_option("apple-2way-gala-red-delicious",
                                            "apple-2-way-gala-red-delicious", facts)
        forwards = admin_view._fold_option("apple-2-way-gala-red-delicious",
                                           "apple-2way-gala-red-delicious", facts)
        self.assertIn('data-warn="1"', backwards)
        self.assertNotIn("data-warn", forwards)

    def test_the_warning_is_not_text_inside_the_option(self):
        """A <select> is sized by its widest option. Spelling the warning out
        inline widened every dropdown by 25 characters, which squeezed the pair
        column until slugs wrapped one hyphen at a time and pushed the last
        column off the screen."""
        facts = {"a-long-slug-here": {"nurseries": 3}, "b": {"nurseries": 1}}
        opt = admin_view._fold_option("a-long-slug-here", "b", facts)
        label = opt.split(">", 1)[1]
        self.assertNotIn("retires", label)
        self.assertIn("a-long-slug-here (3)", label)

    def test_no_css_escape_was_eaten_by_python(self):
        """`content:"\\25B8"` in a plain Python string is an OCTAL escape, not a
        CSS one: Python turns \\25 into \\x15 and leaves "B8", so the disclosure
        triangle shipped as a control character followed by the letters B8. CSS
        escapes in these blocks need doubling, which the older rules in the same
        file already do. A control character is invisible in a diff and in a
        code review, so it is asserted here instead."""
        for name in ("REVIEW_CSS", "INVENTORY_CSS"):
            css = getattr(admin_view, name)
            bad = [c for c in css if ord(c) < 32 and c not in "\n\t"]
            self.assertEqual(bad, [], f"{name} has control characters: "
                                      f"{[hex(ord(c)) for c in bad]}")

    def test_every_risk_warning_has_a_plural(self):
        """"2 rows differs from its base" reached the confirm dialog because the
        warning was one string written for the singular. The sentence a reviewer
        reads before committing 62 rows is the wrong place to be approximately
        right, so each caller supplies [singular, plural] and this fails if one
        goes back to a bare string."""
        js = admin_view.REVIEW_JS
        # Lookbehind skips `function submit(action, rows, risky, why)` itself.
        calls = re.findall(
            r"(?<!function )submit\(\s*(?:'[a-z-]+'|action)\s*,\s*rows\s*,"
            r"\s*risky\s*,\s*(.)", js)
        self.assertTrue(calls, "no risky submit() calls found; did they move?")
        for opener in calls:
            self.assertEqual(opener, "[",
                             "a `why` must be [singular, plural], not a string")
        self.assertIn("why || ['needs a second look'", js)

    def test_an_even_fold_is_not_flagged(self):
        """One nursery each way is a real choice, not a mistake, and warning on
        it would train the reader past the warning that matters."""
        facts = {"a": {"nurseries": 1}, "b": {"nurseries": 1}}
        self.assertNotIn("data-warn", admin_view._fold_option("a", "b", facts))

    def test_pairs_from_different_species_are_never_compared(self):
        """The bucketing is an optimisation and must not change the answer: an
        edit inside the species half would have to survive canonicalisation to
        reach a slug at all."""
        self.assertEqual(admin_view.near_miss_pairs(["mango-alphonso",
                                                     "mango-alphonzo"]),
                         [{"a": "mango-alphonso", "b": "mango-alphonzo",
                           "tier": "letter"}])


class QueuedRowRenderingTests(WriteHarness):
    """A row whose fold is already queued must not re-offer the question.

    Benedict folded `mango-bamberoo`, it landed in `curation_pending`, and the
    row came back from the reload with its select reset to "leave", both
    directions still on offer, and a small pill as the only difference. "I
    folded it but it doesn't look like it's been folded" is a correct reading of
    that markup: the only durable feedback was in a section several screens up.
    """

    def render(self, q=""):
        inv = admin_view.load_variety_inventory(self.data)
        # Both members must be live pages in the ledger or the section renders
        # no fold options at all. One queued alias should resolve this row and
        # the sibling row below it, because it is one decision.
        pairs = [{"a": "avocado-hass", "b": "avocado-hass-potted",
                  "tier": "letter"}]
        return admin_view.render_variety_review_html({
            "varieties": {"index_size": 4, "near_misses": pairs,
                          "near_miss_tiers": {"letter": 1},
                          "siblings": [{"base": "avocado-hass", "base_watchers": 0,
                                        "tier": "judgement",
                                        "siblings": [{"slug": "avocado-hass-potted",
                                                      "watchers": 0,
                                                      "tier": "noise"}]}],
                          "tiers": {"noise": 1}, "overrides": {"deny": [], "alias": {}}},
            "inventory": inv,
            "decisions": self.store(),
            "csrf": "x",
            "q": q,
        })

    def test_every_section_collapses_and_is_a_jump_target(self):
        """The redirect table is 205 rows and 109KB and sits above everything
        with a verb on it, so working the queues meant scrolling past every
        tombstone on the site. _collapsible is a regex over markup the builders
        produce; a section that stops matching would pass through expanded and
        silently undo this, so the wrapping is asserted rather than assumed."""
        html = self.render()
        sections = re.findall(r'<section([^>]*)>(.{0,80})', html, re.S)
        self.assertTrue(sections)
        for attrs, head in sections:
            self.assertIn("id=", attrs, f"section with no id: {head!r}")
            self.assertIn("<details class=\"panel\"", head,
                          f"section not collapsible: {attrs!r}")
        for sid in ("pending", "redirects", "nearmiss", "siblings"):
            self.assertIn(f'href="#{sid}"', html, f"{sid} missing from the nav")

    def test_only_the_pending_queue_starts_open(self):
        """Everything else is long, and which one matters changes by the day."""
        html = self.render()
        opened = re.findall(r'<section id="([^"]+)"><details class="panel" open>',
                            html)
        self.assertEqual(opened, ["pending"])

    def test_a_filter_opens_what_it_matched(self):
        """Typing a slug into the filter is asking to see those rows, not to be
        handed six collapsed headings."""
        html = self.render(q="avocado")
        opened = set(re.findall(
            r'<section id="([^"]+)"><details class="panel" open>', html))
        self.assertIn("redirects", opened)
        self.assertIn("siblings", opened)

    def test_an_unfolded_sibling_row_offers_both_answers(self):
        html = self.render()
        self.assertIn('class="fold"', html)
        self.assertIn('class="dis"', html)

    def test_a_folded_sibling_row_states_the_decision_instead(self):
        self.apply("alias", [{"slug": "avocado-hass-potted",
                              "target": "avocado-hass"}])
        html = self.render()
        self.assertIn("folded into", html)
        self.assertIn('data-action="undo-alias"', html)
        # The controls are gone, not merely decorated. Leaving them rendered is
        # what made a landed decision look like an untouched row.
        self.assertNotIn('class="fold"', html)
        self.assertNotIn('class="dis"', html)

    def test_a_committed_alias_still_reads_as_answered(self):
        """Between promote_curation.py and the 00:00 build the queue is empty
        and the slug is still in the canonical index, so the row used to come
        back as an unanswered question with "leave" selected. Folding it again
        there is a no-op the promoter skips, which is how rows got stranded."""
        html = admin_view.render_variety_review_html({
            "varieties": {"index_size": 4,
                          "near_misses": [{"a": "avocado-hass",
                                           "b": "avocado-hass-potted",
                                           "tier": "letter"}],
                          "near_miss_tiers": {"letter": 1}, "siblings": [],
                          "tiers": {},
                          "overrides": {"deny": [],
                                        "alias": {"avocado-hass-potted":
                                                  "avocado-hass"}}},
            "inventory": admin_view.load_variety_inventory(self.data),
            "decisions": self.store(), "csrf": "x"})
        self.assertIn("aliased to", html)
        self.assertIn("applies at the next build", html)
        self.assertNotIn('class="nm"', html)
        # No Cancel: it is in git, and a button that cannot do what it says is
        # worse than no button.
        self.assertNotIn("undo-alias", html)

    def test_a_folded_near_miss_row_drops_its_select(self):
        self.apply("alias", [{"slug": "avocado-hass-potted",
                              "target": "avocado-hass"}])
        html = self.render()
        self.assertIn("folded into", html)
        self.assertNotIn('class="nm"', html)
        self.assertNotIn('class="nmd"', html)

    def test_the_cancel_button_targets_the_slug_that_was_folded(self):
        """Not the pair, and not the target. `unqueue` drops by `from`."""
        self.apply("alias", [{"slug": "avocado-hass-potted",
                              "target": "avocado-hass"}])
        html = self.render()
        self.assertIn('data-action="undo-alias" data-slug="avocado-hass-potted"',
                      html)


SUGGEST_PAGES = {
    # The real shape, from live data. `banana-tree-musa-nathan` carries the
    # noise token `tree`, so clean_twin computes `banana-musa-nathan`, which is
    # not live, so the field came up blank. The page it should point at is
    # `banana-nathan`, which is live and which no queue on the page names.
    "banana-tree-musa-nathan": entry(
        species="Banana", species_slug="banana",
        rows=[{"nursery_key": "daleys", "available": True}]),
    "banana-nathan": entry(species="Banana", species_slug="banana",
                           rows=[{"nursery_key": "exotica", "available": True}]),
    # The other half of the queue: noise strips cleanly to a page that IS live,
    # so the target arrives pre-filled. That is the row Benedict was surprised by.
    "banana-tree-cavendish": entry(species="Banana", species_slug="banana",
                                   rows=[{"nursery_key": "daleys",
                                          "available": True}]),
    "banana-cavendish": entry(species="Banana", species_slug="banana"),
    "banana-old": entry(species="Banana", species_slug="banana",
                        state="tombstone"),
    "banana-moved": entry(species="Banana", species_slug="banana",
                          state="redirect", redirect_to="banana-nathan"),
    "mango-bambaroo": entry(species="Mango", species_slug="mango"),
    "mango-bamberoo": entry(species="Mango", species_slug="mango"),
}


class TargetSuggestionTests(unittest.TestCase):
    """What a target field may legitimately name, offered rather than recalled.

    Two of the four verbs take a slug typed by hand over a namespace of 2,562
    live pages. Typing is not the cost; knowing what is there is. 58 of the 120
    noisy rows have no clean twin to pre-fill, and `banana-tree-musa-nathan` is
    one of them: the right answer is `banana-nathan`, one of 42 live Banana
    slugs, and nothing on the page said so.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        led = self.data / "page-ledger"
        led.mkdir()
        (led / "variety.json").write_text(json.dumps(
            {"schema": 1, "family": "variety", "updated": "2026-08-17",
             "pages": SUGGEST_PAGES}))
        self.inv = admin_view.load_variety_inventory(self.data)

    def tearDown(self):
        self.tmp.cleanup()

    def lists(self, store=None, committed=None):
        return admin_view._target_lists(self.inv, store or {}, committed or {})

    def options(self, html, sid):
        got = re.search(r'<datalist id="%s"[^>]*>(.*?)</datalist>' % sid, html,
                        re.S)
        return re.findall(r"<option>([^<]+)", got.group(1)) if got else None

    def test_one_list_per_species_of_that_species_live_slugs(self):
        html, ids = self.lists()
        self.assertEqual(ids, {"Banana": "dl-banana", "Mango": "dl-mango"})
        self.assertEqual(self.options(html, "dl-banana"),
                         ["banana-cavendish", "banana-nathan",
                          "banana-tree-cavendish", "banana-tree-musa-nathan"])
        self.assertEqual(self.options(html, "dl-mango"),
                         ["mango-bambaroo", "mango-bamberoo"])

    def test_only_live_pages_are_offered(self):
        """A target that is a tombstone or another redirect serves a 404 or a
        hop. The endpoint refuses both, so the list must not contain them."""
        html, _ = self.lists()
        for slug in ("banana-old", "banana-moved"):
            self.assertNotIn(slug, html)

    def test_a_slug_already_folding_is_not_offered_from_either_source(self):
        """Both are guaranteed refusals: an alias applies once with no chain
        resolution, so pointing at one strands the products. Queued and
        committed are the same hazard, and the queued one is the likelier
        mistake, because it is the row you just filled in above."""
        html, _ = self.lists(
            store={"curation_pending": [{"kind": "alias", "from": "banana-nathan",
                                         "to": "banana-cavendish"}]},
            committed={"mango-bamberoo": "mango-bambaroo"})
        self.assertEqual(self.options(html, "dl-banana"),
                         ["banana-cavendish", "banana-tree-cavendish",
                          "banana-tree-musa-nathan"])
        self.assertEqual(self.options(html, "dl-mango"), ["mango-bambaroo"])

    def test_the_compact_option_form_is_used(self):
        """`<option>slug` with the end tag omitted, which HTML5 allows and every
        browser reads as the option's value. Measured on the live ledger, the
        attribute form renders the same 112 lists for 125KB instead of 79KB."""
        html, _ = self.lists()
        self.assertIn("<option>banana-nathan", html)
        self.assertNotIn('<option value=', html)
        self.assertNotIn("</option>", html)

    def test_both_target_fields_point_at_their_own_species_list(self):
        html = self.render()
        # The alias row, which is the one that had nothing to offer.
        self.assertRegex(html, r'class="al"[^>]*list="dl-banana"')
        self.assertIn('data-species="Banana"', html)
        # And the redirect row, which takes a target too.
        self.assertRegex(html, r'class="rt"[^>]*list="dl-banana"')

    def test_a_species_with_no_list_still_renders_a_plain_field(self):
        """`_target_attrs` returns "" rather than list="", which would point the
        input at no element and, in some browsers, at nothing at all."""
        self.assertEqual(admin_view._target_attrs("Durian", {"Banana": "dl-x"}),
                         "")
        self.assertEqual(admin_view._target_attrs("", {}), "")

    def render(self, store=None, committed=None):
        return admin_view.render_variety_review_html({
            "varieties": {"index_size": 7, "near_misses": [], "siblings": [],
                          "near_miss_tiers": {}, "tiers": {},
                          "overrides": {"deny": [], "alias": committed or {}}},
            "inventory": self.inv,
            "decisions": store or {},
            "csrf": "x",
        })

    def test_the_page_ships_the_folding_map_so_a_chain_can_be_named(self):
        """Without it the check can only say "not a live page" about a slug that
        is live, which is the kind of wrong that gets a page ignored."""
        html = self.render(
            store={"curation_pending": [{"kind": "alias", "from": "banana-nathan",
                                         "to": "banana-cavendish"}]},
            committed={"mango-bamberoo": "mango-bambaroo"})
        got = re.search(r"window\.FOLDING=(\{.*?\});", html)
        self.assertIsNotNone(got, "FOLDING missing; the chain message cannot work")
        self.assertEqual(json.loads(got.group(1)),
                         {"banana-nathan": "banana-cavendish",
                          "mango-bamberoo": "mango-bambaroo"})

    def test_the_datalists_come_after_the_sections(self):
        """79KB the browser parses before the first heading is 79KB in front of
        everything the page is for. A datalist is referenced by id and never
        rendered, so its position is free."""
        html = self.render()
        self.assertLess(html.rindex("</section>"), html.index("<datalist"))

    def test_a_refused_target_is_named_before_the_batch_is_sent(self):
        """The batch is all-or-nothing, so one typo takes the other sixty with
        it, and a 409 arrives after the confirm dialog has been read and agreed
        to. Four verdicts, and only three of them stop the batch: a target in
        another species is legal and occasionally right."""
        js = admin_view.REVIEW_JS
        for phrase in ("points at itself", "not a live variety page",
                       "already folding into", "rather than chaining"):
            self.assertIn(phrase, js, f"{phrase!r} missing from the check")
        # Cross-species warns, never blocks.
        self.assertRegex(js, r"return \['warn', 'a ' \+ LIVE\[v\]")
        # Both sections gate on it.
        self.assertIn("badTargets(tickedA(), '.al')", js)
        self.assertIn("badTargets(chosen, '.rt')", js)
        # Converting to a tombstone clears the target, so a stale box is not a
        # reason to stop.
        self.assertIn("action === 'retarget' || action === 'redirect'", js)

    def test_a_suggested_target_arrives_ticked_off_not_ticked(self):
        """Benedict typed one target and the button offered to queue five.

        `clean_twin` is recomputed from the slug on every render and stored
        nowhere, so a pre-filled target is this page guessing. It was rendered
        into the same field, painted the same green as a value somebody typed,
        and counted by the same "N rows filled" label, so there was no way to
        tell a suggestion from a decision. The tick is the decision now.
        """
        html = self.render()
        row = re.search(r'<tr data-slug="banana-tree-musa-nathan".*?</tr>', html,
                        re.S).group(0)
        self.assertIn('type="checkbox" class="sel"', row)
        self.assertNotIn("data-suggested", row)   # no live twin, nothing filled
        # banana-tree-cavendish strips to a page that IS live, so it is
        # pre-filled AND must say that it is only a suggestion.
        twin = re.search(r'<tr data-slug="banana-tree-cavendish".*?</tr>', html,
                         re.S).group(0)
        self.assertIn('value="banana-cavendish"', twin)
        self.assertIn('data-suggested="1"', twin)
        self.assertIn("suggested, not ticked", twin)
        # And every filled row says which it is in words, because the field is
        # green when you changed it and green when a suggestion is accepted.
        self.assertIn("'typed, not ticked'", admin_view.REVIEW_JS)

    def test_the_tick_and_not_the_filled_field_is_what_submits(self):
        js = admin_view.REVIEW_JS
        self.assertIn("box.checked && input.value.trim()", js)
        # Typing still ticks the row, so the single-row case stays one gesture.
        self.assertIn("if (changed) box.checked = true;", js)
        # And `dirty` goes back to meaning "you changed this", as it does in the
        # redirect table: a green box on a guess is what made it look decided.
        self.assertIn("input.classList.toggle('dirty', changed);", js)
        self.assertNotIn("input.classList.toggle('dirty', !!input.value.trim())",
                         js)

    def test_the_bulk_path_costs_one_click_not_sixty_two(self):
        """Refusing to act on untouched suggestions would be correct and
        useless: 62 of the 120 rows have one, and working them down is the
        actual job. So there is a button that ticks them all, and it stops
        there, leaving the confirm dialog to be read."""
        html = self.render()
        self.assertRegex(html, r'data-action="tick-suggested">Tick all \d+ '
                               r'suggestions<')
        self.assertIn("queued until you press Queue aliases",
                      admin_view.REVIEW_JS)

    def test_nothing_ticked_says_what_a_prefilled_target_is(self):
        self.assertIn("A pre-filled target is a suggestion",
                      admin_view.REVIEW_JS)

    def test_a_folded_row_has_no_tick_to_offer(self):
        """It renders its decision and a Cancel button, so a checkbox beside it
        would be a control with nothing to do."""
        store = {"curation_pending": [{"kind": "alias",
                                       "from": "banana-tree-musa-nathan",
                                       "to": "banana-nathan"}]}
        html = self.render(store=store)
        row = re.search(r'<tr data-slug="banana-tree-musa-nathan".*?</tr>', html,
                        re.S).group(0)
        self.assertIn("folded into", row)
        self.assertNotIn('class="sel"', row)
        self.assertNotIn('class="al"', row)

    def test_the_check_reads_the_datalists_rather_than_a_second_copy(self):
        """Two lists of live slugs on one page is two lists that can disagree,
        and the one the browser suggests from would not be the one the check
        validates against."""
        js = admin_view.REVIEW_JS
        self.assertIn("querySelectorAll('datalist[data-species]')", js)


class NightlyApplicationTests(unittest.TestCase):
    """The other end of the contract. A click that never becomes a page is
    worse than no button: the reviewer believes the job is done.

    `run-all-scrapers.sh` has to pass `--decisions` for any of this to happen,
    which is the same trap `--seed-reviewed` was in, so that is asserted too.
    """

    def setUp(self):
        import build_variety_pages
        from stocklib.page_ledger import FAMILY_VARIETY, PageLedger
        self.bvp = build_variety_pages
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.path = ad.decisions_path(self.data)
        self.ledger = PageLedger(FAMILY_VARIETY, pages={
            k: dict(v) for k, v in PAGES.items()})

    def tearDown(self):
        self.tmp.cleanup()

    def queue(self, slug, action, target=""):
        store = ad.load_decisions(self.path)
        ad.record_redirect(store, slug, action, target=target, by="b@bjnoel.com")
        ad.save_decisions(self.path, store)

    def test_a_queued_retarget_becomes_a_redirect_in_the_ledger(self):
        self.queue("avocado-hass-type-a", ad.RETARGET, "avocado-hass")
        applied, skipped = self.bvp.apply_decided_redirects(
            self.ledger, self.path, "2026-08-18", {"avocado-hass"})
        self.assertEqual((applied, skipped), (1, []))
        entry = self.ledger.pages["avocado-hass-type-a"]
        self.assertEqual(entry["state"], "redirect")
        self.assertEqual(entry["redirect_to"], "avocado-hass")
        self.assertEqual(entry["since"], "2026-08-18")

    def test_a_decision_applies_once_and_is_then_consumed(self):
        """Leaving it queued would mean tonight's intent silently reverting a
        correction someone makes next week."""
        self.queue("avocado-hass-type-a", ad.TO_TOMBSTONE)
        self.bvp.apply_decided_redirects(self.ledger, self.path, "2026-08-18",
                                         {"avocado-hass"})
        self.assertEqual(ad.load_decisions(self.path)["redirects"], {})
        applied, _ = self.bvp.apply_decided_redirects(
            self.ledger, self.path, "2026-08-19", {"avocado-hass"})
        self.assertEqual(applied, 0)

    def test_a_slug_that_came_back_to_life_beats_the_decision(self):
        """A generated slug always wins. A reviewer's week-old opinion must not
        tombstone a page that is serving products tonight."""
        self.queue("avocado-hass-type-a", ad.TO_TOMBSTONE)
        applied, skipped = self.bvp.apply_decided_redirects(
            self.ledger, self.path, "2026-08-18",
            {"avocado-hass", "avocado-hass-type-a"})
        self.assertEqual(applied, 0)
        self.assertIn("live again", skipped[0])
        self.assertEqual(self.ledger.pages["avocado-hass-type-a"]["state"],
                         "redirect")

    def test_a_target_that_is_not_a_page_tonight_keeps_the_decision_for_tomorrow(self):
        """Dropping it would lose a good decision over one bad night; applying it
        would point a live URL at a 404. Waiting is the only correct answer."""
        self.queue("avocado-gone", ad.TO_REDIRECT, "avocado-hass")
        applied, skipped = self.bvp.apply_decided_redirects(
            self.ledger, self.path, "2026-08-18", set())
        self.assertEqual(applied, 0)
        self.assertIn("not a page tonight", skipped[0])
        self.assertIn("avocado-gone", ad.load_decisions(self.path)["redirects"])

    def test_a_decision_queued_while_the_build_ran_survives(self):
        """The nightly re-reads before writing and removes only what it
        consumed. Otherwise a click at 00:00:30 is silently swallowed."""
        self.queue("avocado-hass-type-a", ad.TO_TOMBSTONE)
        real_load = ad.load_decisions
        state = {"n": 0}

        def racing_load(path):
            data = real_load(path)
            state["n"] += 1
            if state["n"] == 1:      # the build's initial read
                later = real_load(path)
                ad.record_redirect(later, "avocado-left", ad.TO_TOMBSTONE, by="x")
                ad.save_decisions(path, later)
            return data

        ad.load_decisions = racing_load
        try:
            self.bvp.apply_decided_redirects(self.ledger, self.path, "2026-08-18",
                                             {"avocado-hass"})
        finally:
            ad.load_decisions = real_load
        left = ad.load_decisions(self.path)["redirects"]
        self.assertNotIn("avocado-hass-type-a", left)   # consumed
        self.assertIn("avocado-left", left)             # queued mid-build, kept

    def test_the_nightly_actually_passes_the_flag(self):
        """--seed-reviewed was the same trap: the code worked and the shell
        script did not call it, so every approval reached nothing."""
        sh = (SCRAPERS / "run-all-scrapers.sh").read_text()
        build = sh[sh.index("build_variety_pages.py"):]
        self.assertIn("--decisions", build[:600])
        self.assertIn("variety-decisions.json", build[:600])

    def test_the_promoter_wrapper_actually_promotes(self):
        """Third instance of the same trap, after --seed-reviewed and
        --decisions: a wrapper that runs promote_curation.py without --execute
        dry-runs forever, printing what it would do to a log nobody reads,
        while the review UI shows the fold as queued and it never lands."""
        sh = (REPO_ROOT / "tools" / "autonomous" / "promote-curation.sh").read_text()
        # Comments stripped first. The header explains what promote_curation.py
        # does, so matching the first mention of it tests the prose.
        code = "\n".join(ln for ln in sh.splitlines()
                         if not ln.lstrip().startswith("#"))
        call = code[code.index("promote_curation.py"):]
        self.assertIn("--execute", call[:400])
        self.assertIn("--push", call[:400])
        # It must deploy too: the build reads the rsynced copy under
        # /opt/dale/scrapers, not the commit in /opt/dale/repo.
        self.assertIn("deploy.sh", sh)

    def test_the_promoter_wrapper_is_deployed_executable(self):
        """It lands via deploy.sh's rsync like every other autonomous script,
        and cron cannot run what is not +x."""
        deploy = (REPO_ROOT / "tools" / "deploy.sh").read_text()
        self.assertIn("chmod +x /opt/dale/autonomous/promote-curation.sh", deploy)

    def test_the_flag_exists_on_the_builder(self):
        self.assertIn("--decisions",
                      (SCRAPERS / "build_variety_pages.py").read_text())


class DecisionStoreTests(unittest.TestCase):
    def test_a_corrupt_file_reads_as_no_decisions(self):
        """The nightly reads this. Dying on a malformed file would take the
        whole variety build down over a stray byte in an admin queue."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "variety-decisions.json"
            p.write_text("{ truncated")
            data = ad.load_decisions(p)
        self.assertEqual(data["redirects"], {})
        self.assertEqual(data["curation_pending"], [])

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "d.json"
            store = ad.empty()
            ad.record_redirect(store, "a", ad.RETARGET, target="b", by="x")
            ad.dismiss_sibling(store, "c", "c-d", by="x")
            ad.queue_curation(store, ad.ALIAS, "e", target="f", by="x")
            ad.save_decisions(p, store)
            back = ad.load_decisions(p)
        self.assertEqual(back["redirects"]["a"]["target"], "b")
        self.assertEqual(len(back["siblings"]), 1)
        self.assertEqual(back["curation_pending"][0]["to"], "f")

    def test_a_retarget_without_a_target_is_a_programming_error(self):
        for action in (ad.RETARGET, ad.TO_REDIRECT):
            with self.subTest(action=action):
                with self.assertRaises(ValueError):
                    ad.record_redirect(ad.empty(), "a", action)


if __name__ == "__main__":
    unittest.main()
