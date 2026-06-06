"""
Tests for the AI-crawler exposure files: the static robots.txt content signals
and the build_llms.py llms.txt generator.

The chosen stance (DEC: "Invite AI answers"): welcome search + AI answers
(search=yes, ai-input=yes) but not model training (ai-train=no, training bots
blocked). See tools/scrapers/static/robots.txt.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import build_llms

ROBOTS = (SCRAPERS / "static" / "robots.txt").read_text()
DASH = ("—", "–")  # em dash, en dash (CLAUDE.md copy rule)


class RobotsTest(unittest.TestCase):
    def test_content_signal_invites_ai_answers(self):
        self.assertIn("Content-Signal: search=yes, ai-input=yes, ai-train=no", ROBOTS)

    def test_sitemap_referenced(self):
        self.assertIn("Sitemap: https://treestock.com.au/sitemap.xml", ROBOTS)

    def test_wildcard_group_allows(self):
        self.assertIn("User-agent: *", ROBOTS)
        self.assertIn("Allow: /", ROBOTS)

    def test_training_bots_blocked(self):
        for bot in ("GPTBot", "CCBot", "ClaudeBot", "Google-Extended", "Bytespider",
                    "Amazonbot", "Applebot-Extended", "meta-externalagent"):
            self.assertIn(f"User-agent: {bot}", ROBOTS, f"{bot} should have a block group")

    def test_answer_bots_not_blocked(self):
        # The citation/answer crawlers must NOT have their own Disallow group, so
        # the wildcard Allow applies to them.
        for bot in ("OAI-SearchBot", "ChatGPT-User", "PerplexityBot",
                    "Perplexity-User", "Claude-User"):
            self.assertNotIn(f"User-agent: {bot}", ROBOTS,
                             f"{bot} must stay allowed (no block group)")

    def test_no_dashes(self):
        for d in DASH:
            self.assertNotIn(d, ROBOTS)


class LlmsTest(unittest.TestCase):
    SAMPLE = [{"slug": "mango", "common_name": "Mango"},
              {"slug": "fig", "common_name": "Fig"}]

    def test_structure(self):
        out = build_llms.build_llms_txt(self.SAMPLE)
        self.assertTrue(out.startswith("# treestock.com.au"))
        self.assertIn("\n> ", out)
        for h in ("## Guides", "## Browse", "## Species guides"):
            self.assertIn(h, out)

    def test_species_links_absolute_and_sorted(self):
        out = build_llms.build_llms_txt(self.SAMPLE)
        self.assertIn("https://treestock.com.au/species/mango.html", out)
        self.assertIn("https://treestock.com.au/species/fig.html", out)
        # sorted by common_name -> Fig before Mango
        self.assertLess(out.index("/species/fig.html"), out.index("/species/mango.html"))

    def test_all_links_are_absolute_https(self):
        out = build_llms.build_llms_txt(self.SAMPLE)
        for url in re.findall(r"\]\((.*?)\)", out):
            self.assertTrue(url.startswith("https://treestock.com.au/"), url)

    def test_no_dashes(self):
        out = build_llms.build_llms_txt(self.SAMPLE)
        for d in DASH:
            self.assertNotIn(d, out)

    def test_build_writes_file_for_real_species(self):
        with tempfile.TemporaryDirectory() as d:
            build_llms.build(d)
            txt = (Path(d) / "llms.txt").read_text()
            self.assertIn("## Species guides", txt)
            self.assertGreater(txt.count("/species/"), 10)


if __name__ == "__main__":
    unittest.main()
