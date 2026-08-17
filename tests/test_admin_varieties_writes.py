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

    def render(self):
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
        })

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
