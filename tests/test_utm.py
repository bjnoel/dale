"""Tests for stocklib.utm.outbound — the shared outbound-link UTM tagger."""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

from stocklib.utm import outbound, affiliate, AFFILIATE_REFS


class AffiliateTest(unittest.TestCase):
    """Referral refs are the only thing in this module that earns money, so the
    failure modes worth pinning are: a missed ref (silent lost commission) and a
    ref on a nursery we have no agreement with (billing someone for nothing)."""

    def test_primal_gets_ref(self):
        self.assertEqual(
            affiliate("https://primalfruits.com.au/products/queensland-bottle-tree"),
            "https://primalfruits.com.au/products/queensland-bottle-tree?ref=treestock")

    def test_non_affiliate_nursery_untouched(self):
        url = "https://www.daleysfruit.com.au/fruit/sapodilla.htm"
        self.assertEqual(affiliate(url), url)

    def test_existing_query_string_uses_ampersand(self):
        self.assertEqual(
            affiliate("https://primalfruits.com.au/products/fig?variant=42"),
            "https://primalfruits.com.au/products/fig?variant=42&ref=treestock")

    def test_idempotent(self):
        # build-dashboard.py tags before serialising and dashboard.js appends UTM
        # afterwards; a second pass must not produce ?ref=treestock&ref=treestock.
        once = affiliate("https://primalfruits.com.au/products/fig")
        self.assertEqual(affiliate(once), once)

    def test_empty_url_passthrough(self):
        self.assertEqual(affiliate(""), "")

    def test_www_prefix_still_matches(self):
        # NURSERY_META stores Primal with a www. prefix while scraped product
        # URLs omit it, so a startswith match would silently miss the nursery
        # homepage link on /nursery/primal-fruits.html.
        self.assertEqual(
            affiliate("https://www.primalfruits.com.au"),
            "https://www.primalfruits.com.au?ref=treestock")

    def test_outbound_applies_ref_before_utm(self):
        # GoAffPro issues links as ?ref=treestock; keep that leading position so
        # the emitted URL matches what the affiliate dashboard shows.
        self.assertEqual(
            outbound("https://primalfruits.com.au/products/fig", "referral"),
            "https://primalfruits.com.au/products/fig"
            "?ref=treestock&utm_source=treestock&utm_medium=referral")

    def test_only_declared_domains_are_affiliate(self):
        # Guards against a future edit that tags every nursery. Ranking and
        # commission must stay unrelated, and 26 of 27 nurseries earn us nothing.
        self.assertEqual(list(AFFILIATE_REFS), ["primalfruits.com.au"])


class OutboundTest(unittest.TestCase):
    def test_plain_url(self):
        self.assertEqual(
            outbound("https://x.com/p/fig", "nursery-page"),
            "https://x.com/p/fig?utm_source=treestock&utm_medium=nursery-page")

    def test_existing_query_string(self):
        self.assertEqual(
            outbound("https://x.com/p?id=3", "compare"),
            "https://x.com/p?id=3&utm_source=treestock&utm_medium=compare")

    def test_campaign(self):
        self.assertEqual(
            outbound("https://x.com/p", "email", campaign="variety-alert"),
            "https://x.com/p?utm_source=treestock&utm_medium=email&utm_campaign=variety-alert")

    def test_empty_url_passthrough(self):
        self.assertEqual(outbound("", "referral"), "")

    def test_matches_legacy_inline_format(self):
        # The de-forked callers must produce byte-identical URLs to the old
        # inline one-liners, or golden pages / email templates would churn.
        url = "https://daleys.com.au/plant/1"
        legacy = url + ("&" if "?" in url else "?") + "utm_source=treestock&utm_medium=referral"
        self.assertEqual(outbound(url, "referral"), legacy)


if __name__ == "__main__":
    unittest.main()
