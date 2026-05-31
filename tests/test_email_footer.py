"""
Tests for stocklib.email_footer -- the shared personalised email footer used by
send_digest.py (daily) and send_weekly_digest.py (weekly).

Previously each sender defined its own inject_footer; the copies produced the
same unsubscribe/preferences URLs but used different separators and could drift
(e.g. a compliance link changed in one but not the other). Now centralised in
stocklib.email_footer and pinned here.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from stocklib.email_footer import inject_footer, inject_text_footer, footer_urls


class FooterURLsTest(unittest.TestCase):
    def test_urls_use_compliant_paths(self):
        unsub, prefs = footer_urls("a@b.com", "tok123")
        self.assertEqual(
            unsub, "https://treestock.com.au/unsubscribe.html?email=a%40b.com&token=tok123"
        )
        self.assertEqual(
            prefs, "https://treestock.com.au/api/preferences?email=a%40b.com&token=tok123"
        )

    def test_email_is_url_encoded(self):
        unsub, prefs = footer_urls("a+tag@b.com", "t")
        self.assertIn("a%2Btag%40b.com", unsub)
        self.assertIn("a%2Btag%40b.com", prefs)

    def test_site_url_override(self):
        unsub, prefs = footer_urls("a@b.com", "t", site_url="https://beestock.com.au")
        self.assertTrue(unsub.startswith("https://beestock.com.au/unsubscribe.html"))
        self.assertTrue(prefs.startswith("https://beestock.com.au/api/preferences"))


class InjectFooterTest(unittest.TestCase):
    def test_inserts_before_body_close(self):
        html = "<html><body><p>hi</p></body></html>"
        out = inject_footer(html, "a@b.com", "tok", "ALL")
        self.assertTrue(out.endswith("</body></html>"))
        self.assertLess(out.index("Unsubscribe"), out.index("</body>"))

    def test_appends_when_no_body(self):
        out = inject_footer("<p>hi</p>", "a@b.com", "tok", "WA")
        self.assertIn("Unsubscribe", out)

    def test_contains_both_compliance_links(self):
        out = inject_footer("<body></body>", "a@b.com", "tok", "ALL")
        self.assertIn("/unsubscribe.html?email=a%40b.com&token=tok", out)
        self.assertIn("/api/preferences?email=a%40b.com&token=tok", out)
        self.assertIn(">Unsubscribe</a>", out)
        self.assertIn(">Manage your alerts</a>", out)

    def test_state_label(self):
        self.assertIn("Showing: all states", inject_footer("<body></body>", "a@b.com", "t", "ALL"))
        self.assertIn("Filtered to: WA", inject_footer("<body></body>", "a@b.com", "t", "WA"))

    def test_uses_html_entity_separator(self):
        # Standardised on &middot; (renders identically to a raw bullet but is
        # charset-safe in email). Guards against reintroducing a raw separator.
        out = inject_footer("<body></body>", "a@b.com", "t", "ALL")
        self.assertIn("&middot;", out)


class InjectTextFooterTest(unittest.TestCase):
    def test_contains_links_and_state(self):
        out = inject_text_footer("Body text", "a@b.com", "tok", "WA")
        self.assertIn("Body text", out)
        self.assertIn(
            "Manage your alerts: https://treestock.com.au/api/preferences?email=a%40b.com&token=tok",
            out,
        )
        self.assertIn(
            "Unsubscribe: https://treestock.com.au/unsubscribe.html?email=a%40b.com&token=tok",
            out,
        )
        self.assertIn("Filtered to: WA", out)


if __name__ == "__main__":
    unittest.main()
