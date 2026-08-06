"""
Tests for tools/autonomous/linear_update.py.

Regression coverage for one bug (2026-04-27):
  An autonomous Dale session posted "Dale: -" comments to DAL-167,
  DAL-169, and DAL-171. cmd_comment had no validation, so the model
  could call `linear_update.py comment DAL-X "-"` and the script would
  prefix and post it as if real content. _is_meaningful_comment now
  rejects empty/punctuation-only bodies.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTONOMOUS = REPO_ROOT / "tools" / "autonomous"
sys.path.insert(0, str(AUTONOMOUS))

spec = importlib.util.spec_from_file_location(
    "linear_update", AUTONOMOUS / "linear_update.py"
)
linear_update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(linear_update)


class IsMeaningfulCommentTests(unittest.TestCase):
    def test_rejects_empty(self):
        self.assertFalse(linear_update._is_meaningful_comment(""))
        self.assertFalse(linear_update._is_meaningful_comment("   "))

    def test_rejects_dash_only(self):
        # The actual bug body
        self.assertFalse(linear_update._is_meaningful_comment("-"))
        self.assertFalse(linear_update._is_meaningful_comment("Dale: -"))
        self.assertFalse(linear_update._is_meaningful_comment("Dale:-"))

    def test_rejects_punctuation_only(self):
        self.assertFalse(linear_update._is_meaningful_comment("..."))
        self.assertFalse(linear_update._is_meaningful_comment("Dale: ..."))
        self.assertFalse(linear_update._is_meaningful_comment("???"))

    def test_rejects_prefix_with_only_whitespace(self):
        self.assertFalse(linear_update._is_meaningful_comment("Dale:   "))
        self.assertFalse(linear_update._is_meaningful_comment("Dale:"))

    def test_accepts_real_content(self):
        self.assertTrue(linear_update._is_meaningful_comment("Done."))
        self.assertTrue(
            linear_update._is_meaningful_comment("Dale: Finished, see commit abc123.")
        )
        # Mixed punctuation + words is fine
        self.assertTrue(linear_update._is_meaningful_comment("OK!"))
        # Even one alphanumeric character counts as meaningful
        self.assertTrue(linear_update._is_meaningful_comment("Dale: a"))


class BlocklistTests(unittest.TestCase):
    """Reads the committed state/ticket-blocklist.json, not a fixture."""

    def assertBlocked(self, title, description=""):
        hit = linear_update.check_blocklist(title, description)
        self.assertIsNotNone(hit, f"should be blocked: {title!r}")

    def assertAllowed(self, title, description=""):
        hit = linear_update.check_blocklist(title, description)
        self.assertIsNone(
            hit, f"should be allowed: {title!r} (matched {hit[0] if hit else None!r})"
        )

    def test_blocks_beestock(self):
        # DEC-230: beestock discontinued 2026-07-23
        self.assertBlocked("beestock: add subscribe CTA to compare pages")
        self.assertBlocked("Beestock price history charts")
        self.assertBlocked("Write a beginner beekeeping buying guide")
        self.assertBlocked("Re-enable the bee scraper cron")
        self.assertBlocked(
            "Audit archived sites", "Includes beestock.com.au category pages"
        )

    def test_blocks_existing_entries(self):
        self.assertBlocked("Tass1 Trees demo store")
        self.assertBlocked("Leeming Fruit Trees follow-up")
        self.assertBlocked("walkthrough: research 10 Perth SMB prospects")

    def test_no_bee_substring_false_positives(self):
        # "bee" as a bare pattern would match "been", "between", "beetle".
        # These are all legitimate treestock/Treesmith tickets.
        self.assertAllowed("treestock: species pages have been flat since June")
        self.assertAllowed("treestock: fix ordering between digest and species pages")
        self.assertAllowed("treestock: add fruit fly and beetle pest notes to guides")
        self.assertAllowed("Treesmith: App Store rating and review audit")
        self.assertAllowed(
            "treestock: bare-root season subscriber email",
            "Bare-root stock has been listed by 4 nurseries.",
        )


class DuplicateTitleTests(unittest.TestCase):
    """Regression coverage for the duplicate burst of 2026-07-27.

    A generation session created 13 tickets in three minutes. Three
    duplicated tickets Dale itself had created four days earlier. The
    prompt did tell it to read every backlog title first, but prompt text
    is not enforcement, so the check now runs in cmd_create as well.

    Root cause of the blind session is covered in tests/test_linear_poller.py.
    """

    # (identifier, title) pairs as cmd_create assembles them
    BACKLOG = [
        ("DAL-220", "treestock: Treesmith CTA on nursery pages (Daleys, Ladybird)"),
        ("DAL-173", "Treesmith: email treestock subscribers about app launch"),
        ("DAL-221", "treestock: build send_broadcast.py for one-time Treesmith email to all subscribers"),
        ("DAL-215", "Regenerate archive_links.json: 11 newly-enabled species have unused RFCA further-reading"),
        ("DAL-84", "treestock: Weekly Facebook content post from digest data"),
    ]

    def assertFlagged(self, title, expected_id):
        matches = linear_update.find_similar_titles(title, self.BACKLOG)
        self.assertTrue(matches, f"expected {title!r} to be flagged as a duplicate")
        self.assertEqual(matches[0][0], expected_id)

    def assertNotFlagged(self, title):
        matches = linear_update.find_similar_titles(title, self.BACKLOG)
        self.assertFalse(matches, f"{title!r} was wrongly flagged: {matches}")

    def test_catches_the_real_duplicates(self):
        # DAL-236, created 2026-07-27, duplicating DAL-220 from 2026-07-23
        self.assertFlagged(
            "Treestock: add Treesmith CTA to nursery pages (follow-up from DAL-218 audit)",
            "DAL-220",
        )
        # DAL-226, same session, duplicating DAL-173
        self.assertFlagged(
            "Treesmith: dedicated one-off email to treestock subscribers pitching the app",
            "DAL-173",
        )

    def test_allows_genuinely_distinct_tickets(self):
        self.assertNotFlagged("treestock: bare-root season subscriber email (July-August)")
        self.assertNotFlagged("Treesmith: verify Android Play Store listing is live and discoverable")
        self.assertNotFlagged("treestock: add app store badge images to /treesmith.html")
        self.assertNotFlagged("Treesmith: competitive pricing analysis vs plant tracker apps")

    def test_treestock_and_treesmith_are_not_interchangeable(self):
        # Both site names survive tokenisation, so a Treesmith ticket must not
        # collide with the treestock ticket it happens to share words with.
        score = linear_update.title_overlap(
            "Treesmith: weekly Facebook content post from digest data",
            "treestock: Weekly Facebook content post from digest data",
        )
        self.assertGreater(score, 0.7, "near-identical titles should still score high")
        self.assertLess(
            linear_update.title_overlap("treestock: nursery scraper health grid",
                                        "Treesmith: App Store rating and review audit"),
            0.3,
        )

    def test_short_titles_need_more_than_one_shared_word(self):
        # Two shared tokens out of two would otherwise score 1.0
        self.assertEqual(
            linear_update.title_overlap("treestock: fix sitemap", "treestock: fix robots"),
            0.0,
        )

    def test_empty_titles_score_zero(self):
        self.assertEqual(linear_update.title_overlap("", "treestock: anything"), 0.0)
        self.assertEqual(linear_update.title_overlap("the and for", "treestock: anything"), 0.0)

    def test_recurring_generated_tickets_are_flagged_by_design(self):
        # gsc_page_review.py passes --allow-duplicate precisely because these
        # fortnightly titles differ only by date and would otherwise be blocked.
        matches = linear_update.find_similar_titles(
            "treestock: GSC page review - 2026-07-15",
            [("DAL-190", "treestock: GSC page review - 2026-05-18")],
        )
        self.assertTrue(matches)


class TestTouchedByHuman(unittest.TestCase):
    """The 30-day backlog expiry sweep cancels untriaged proposals, but must
    never overrule one Benedict consciously parked. Any non-Dale actor on the
    ticket means he has seen it and chosen to leave it there."""

    def _issue(self, comment_authors=(), history_actors=()):
        return {
            "comments": {"nodes": [{"user": {"name": n}} for n in comment_authors]},
            "history": {"nodes": [{"actor": {"name": n}} for n in history_actors]},
        }

    def test_untouched_ticket_expires(self):
        self.assertFalse(linear_update._touched_by_human(self._issue()))

    def test_dale_only_activity_still_expires(self):
        """Dale creating and commenting on its own proposal is not triage."""
        issue = self._issue(comment_authors=["Dale"], history_actors=["Dale"])
        self.assertFalse(linear_update._touched_by_human(issue))

    def test_benedict_comment_spares_it(self):
        issue = self._issue(comment_authors=["Dale", "Benedict Noel"])
        self.assertTrue(linear_update._touched_by_human(issue))

    def test_benedict_history_event_spares_it(self):
        """Re-prioritising or re-labelling without commenting still counts."""
        issue = self._issue(history_actors=["Benedict Noel"])
        self.assertTrue(linear_update._touched_by_human(issue))

    def test_dale_name_match_is_case_insensitive(self):
        issue = self._issue(comment_authors=["dale", "DALE "])
        self.assertFalse(linear_update._touched_by_human(issue))

    def test_missing_actor_is_not_a_human(self):
        """Linear returns a null actor for some automated events."""
        issue = {"comments": {"nodes": [{"user": None}]},
                 "history": {"nodes": [{"actor": None}]}}
        self.assertFalse(linear_update._touched_by_human(issue))


if __name__ == "__main__":
    unittest.main()
