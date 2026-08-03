"""
Tests for the ticket description length cap in tools/autonomous/linear_update.py.

Benedict, 2026-08-03: "it's taking me longer to read tickets than come up with
tasks myself". Measured at the time: 48 open tickets holding 14,112 words, about
64 minutes of reading just to decide what was worth doing. Tickets written
before the Opus 5 switch (2026-07-30, commit 6f1b1cd) had a ~95-word median;
after it the median was ~320 and the longest hand-written one was 705.

The model was not freelancing. session-prompt.py asked every ticket to state
its thinking level, its expected metric, and why it would move that metric, and
Opus 5 complied more thoroughly than its predecessor. So the fix is a shorter
prompt AND a cap in code, because the duplicate-guard lesson (DEC-236) was that
prompt text is not an enforcement mechanism.

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

count = linear_update.count_description_words
CAP = linear_update.MAX_DESCRIPTION_WORDS


# The real DAL-270 description, which is close to the post-Opus-5 median (267
# words) rather than the worst case (DAL-245 at 705). If even the median-length
# ticket does not trip the cap, the cap is not doing anything.
DAL_270 = """Level 2 (Channel). Expected metric: treesmith_downloads -> revenue_monthly.

Finding (2026-07-31, DAL-234): July installs by storefront are US 30, AU 9,
IN 4, then singles. Australia is 18% of our installs. Both production purchases
are one AUD and one USD.

Every ASO measurement we have ever taken is on the AU App Store. DEC-247
re-measured 36 terms, all AU, and concluded the app NAME is the ranking field.
DAL-177's proposed rename and DAL-257's follow-up re-measure are both scored
against AU ranks. We have never once looked at where we rank in the storefront
that supplies most of our users.

Why this moves the metric: if we rank very differently in the US, the rename
decision on DAL-177 is being made on the wrong data, and the competitor set is
probably different too (Grove, Rootstock and FruitForest were all identified on
the AU store). At the DAL-234 point estimate of 4.1% install-to-purchase,
roughly 123 installs a month covers the entire A$162 operating cost, so where
the installs come from is now a revenue question rather than a vanity one.

Scope: re-run the same 36 terms against the US storefront via the iTunes Search
API country parameter (free, already scripted, see reference notes), diff US
rank against AU rank per term, and identify any term where we are materially
worse in the US. Also pull the US competitor set for the top niche-tracker
compounds. Read-only, no store changes, no cost.

Distinct from DAL-257, which re-measures AU terms on a 4-week timer to test the
name-field theory. This asks a different question: which storefront should we be
optimising for at all."""

# What that same ticket looks like as a decision card.
DAL_270_CARD = """Re-run our 36 App Store keyword ranks against the US storefront instead of AU.

**Why now:** 61% of July installs are US (30 of 49) but every rank we have ever
measured is AU, so DAL-177's rename is being scored on the wrong store.

**Cost:** $0, ~1hr · Dale autonomous, read-only.

`L2 · treesmith_downloads`"""


class TestLengthCap(unittest.TestCase):
    def test_real_bloated_ticket_is_rejected(self):
        self.assertGreater(count(DAL_270), CAP)

    def test_decision_card_version_passes(self):
        self.assertLessEqual(count(DAL_270_CARD), CAP)

    def test_card_keeps_the_decisive_number(self):
        """Compression must not cost Benedict the fact he decides on."""
        self.assertIn("61%", DAL_270_CARD)

    def test_cap_is_tight_enough_to_matter(self):
        """A 48-ticket backlog at the cap should be minutes, not an hour."""
        minutes_to_triage = (48 * CAP) / 220  # ~220 wpm
        self.assertLess(minutes_to_triage, 25)


class TestWordCount(unittest.TestCase):
    """Formatting is not prose and must not eat the budget."""

    def test_empty(self):
        self.assertEqual(count(""), 0)
        self.assertEqual(count(None), 0)

    def test_link_target_does_not_count_but_link_text_does(self):
        # A bare treestock URL is ~8 "words" of slug if counted naively.
        self.assertEqual(
            count("See [the shipping page](https://treestock.com.au/a/b/c/d.html)"),
            4,  # See, the, shipping, page
        )

    def test_bare_url_is_not_counted(self):
        self.assertEqual(count("Docs <https://linear.app/biomassive/issue/DAL-270>"), 1)

    def test_code_block_is_not_counted(self):
        self.assertEqual(
            count("Run this:\n```\npython3 tools/scrapers/run.py --all --verbose\n```"),
            2,
        )

    def test_inline_code_is_not_counted(self):
        self.assertEqual(count("The `L2 · treesmith_downloads` footer"), 2)

    def test_markdown_markers_are_not_counted(self):
        self.assertEqual(count("## Heading\n\n- one\n- two\n> quote"), 4)

    def test_plain_prose_counts_normally(self):
        self.assertEqual(count("one two three four five"), 5)


class TestGeneratedTicketsFitTheCap(unittest.TestCase):
    """gsc_page_review.py pasted 4,000 chars into --description every fortnight.

    That generator is the reason DAL-272 was 789 words. Now that the cap is
    enforced it would fail outright, so the card it builds has to fit.
    """

    def setUp(self):
        # The module pulls in the Google API client at import time for the GSC
        # fetch. build_review_card touches none of it, and requiring the
        # credentials stack to test a word count would mean this never runs
        # locally, so stub the imports out.
        import types

        def pkg(name):
            m = types.ModuleType(name)
            m.__path__ = []  # mark as a package so submodule imports resolve
            return m

        stubs = {
            "google": pkg("google"),
            "google.oauth2": pkg("google.oauth2"),
            "google.oauth2.service_account": types.ModuleType("service_account"),
            "google.auth": pkg("google.auth"),
            "google.auth.transport": pkg("google.auth.transport"),
            "google.auth.transport.requests": types.ModuleType("requests"),
            "googleapiclient": pkg("googleapiclient"),
            "googleapiclient.discovery": types.ModuleType("discovery"),
            "googleapiclient.errors": types.ModuleType("errors"),
        }
        stubs["google.oauth2.service_account"].Credentials = object
        stubs["google.auth.transport.requests"].Request = object
        stubs["googleapiclient.discovery"].build = lambda *a, **k: None
        stubs["googleapiclient.errors"].HttpError = type("HttpError", (Exception,), {})
        self._injected = [k for k in stubs if k not in sys.modules]
        sys.modules.update({k: v for k, v in stubs.items() if k in self._injected})
        self.addCleanup(lambda: [sys.modules.pop(k, None) for k in self._injected])

        spec = importlib.util.spec_from_file_location(
            "gsc_page_review", REPO_ROOT / "tools" / "scrapers" / "gsc_page_review.py"
        )
        self.gsc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.gsc)

    def _page(self, path, impressions, position, clicks=0, n_opps=3):
        return {
            "url": self.gsc.SITE_BASE + path,
            "opportunity_queries": [
                {"keys": [f"query {i}"], "impressions": impressions - i,
                 "clicks": clicks, "position": position}
                for i in range(n_opps)
            ],
        }

    def test_card_fits_the_cap(self):
        pages = [self._page(f"/page-{i}.html", 20 + i, 12.5) for i in range(5)]
        card = self.gsc.build_review_card(pages, "2026-08-01")
        self.assertLessEqual(count(card), CAP)

    def test_card_leads_with_the_biggest_opportunity(self):
        pages = [
            self._page("/small.html", 9, 14.0),
            self._page("/biggest.html", 99, 11.3),
        ]
        card = self.gsc.build_review_card(pages, "2026-08-01")
        self.assertIn("/biggest.html", card)
        self.assertNotIn("/small.html", card)

    def test_card_survives_a_review_with_no_opportunities(self):
        card = self.gsc.build_review_card([], "2026-08-01")
        self.assertLessEqual(count(card), CAP)
        self.assertIn("treestock_organic_visitors", card)


if __name__ == "__main__":
    unittest.main()
