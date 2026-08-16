"""
Tests for stocklib.tombstone: the copy and markup for a page whose products
are gone.

Two kinds of test here. The sentence tests pin copy that has to stay factual
as the data thins out, because a tombstone whose only unique content is
generated from the ledger is the difference between a real page and a soft 404.
The guard tests pin the constraints that are defects rather than tradeoffs:
no email capture on a combo tombstone (DEC-294), no watch form on a redirect
stub, no noindex on either, and no em dashes anywhere.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "scrapers"))

from stocklib.page_ledger import (  # noqa: E402
    LIVE, REDIRECT, STATE_META_NAME, STATE_META_SCAN_BYTES, TOMBSTONE,
    page_state_meta, read_page_state,
)
from stocklib.tombstone import (  # noqa: E402
    MAX_COMBO_CTA_LINKS, combo_cta_html, format_date, format_price,
    last_stock_sentence, render_stub, render_tombstone, stub_head_extras,
    tombstone_head_extras, tracking_sentence,
)

ENTRY = {
    "state": TOMBSTONE,
    "first_seen": "2026-03-05", "last_seen": "2026-05-01",
    "live_days": 58, "in_stock_days": 44, "last_in_stock": "2026-05-01",
    "title": "Pecan - Mahan (B)", "species": "Pecan", "variety": "Mahan (B)",
    "rows": [{"nursery_key": "daleys", "nursery_name": "Daleys", "price": 49.0,
              "available": True, "url": "https://daleys/p", "states": "NSW, QLD"}],
}


class SentenceTest(unittest.TestCase):
    def test_the_plans_worked_example(self):
        self.assertEqual(
            last_stock_sentence(ENTRY),
            "It was last in stock on 1 May 2026 at Daleys for $49.00.")
        self.assertEqual(
            tracking_sentence(ENTRY),
            "We tracked it at 1 nursery between 5 March and 1 May 2026, "
            "in stock on 44 of those 58 days.")

    def test_plural_nurseries(self):
        entry = dict(ENTRY, rows=[
            {"nursery_key": "daleys", "nursery_name": "Daleys", "price": 49.0},
            {"nursery_key": "ladybird", "nursery_name": "Ladybird", "price": 39.0},
        ])
        self.assertIn("at 2 nurseries", tracking_sentence(entry))

    def test_never_seen_in_stock_says_nothing_about_stock(self):
        entry = dict(ENTRY, last_in_stock=None)
        self.assertEqual(last_stock_sentence(entry), "")

    def test_no_rows_still_gives_the_date(self):
        entry = dict(ENTRY, rows=[])
        self.assertEqual(last_stock_sentence(entry),
                         "It was last in stock on 1 May 2026.")

    def test_missing_price_drops_only_the_price_clause(self):
        entry = dict(ENTRY, rows=[{"nursery_key": "daleys",
                                   "nursery_name": "Daleys", "price": None}])
        self.assertEqual(last_stock_sentence(entry),
                         "It was last in stock on 1 May 2026 at Daleys.")

    def test_single_day_page_reads_as_one_date(self):
        entry = dict(ENTRY, first_seen="2026-05-01", last_seen="2026-05-01",
                     live_days=1, in_stock_days=1)
        self.assertIn("on 1 May 2026", tracking_sentence(entry))
        self.assertNotIn("between", tracking_sentence(entry))

    def test_unparseable_dates_yield_no_sentence_rather_than_a_broken_one(self):
        self.assertEqual(tracking_sentence({"first_seen": None}), "")
        self.assertEqual(last_stock_sentence({"last_in_stock": "not-a-date"}), "")
        self.assertEqual(format_date(None), "")
        self.assertEqual(format_price("x"), "")

    def test_no_leading_zero_in_the_day(self):
        self.assertEqual(format_date("2026-05-01"), "1 May 2026")


class TombstoneBlockTest(unittest.TestCase):
    def test_renders_the_callout_and_both_sentences(self):
        html = render_tombstone("Mahan (B) Pecan", ENTRY)
        self.assertIn("No nursery we track is currently listing "
                      "Mahan (B) Pecan.", html)
        self.assertIn("It was last in stock on 1 May 2026", html)
        self.assertIn("in stock on 44 of those 58 days", html)

    def test_scraped_names_are_escaped(self):
        html = render_tombstone('Fig & "Olive" <script>', ENTRY)
        self.assertNotIn("<script>", html)
        self.assertIn("&amp;", html)

    def test_thin_entry_renders_the_callout_alone(self):
        html = render_tombstone("Something", {"rows": []})
        self.assertIn("No nursery we track is currently listing Something.", html)
        self.assertNotIn("last in stock", html)
        self.assertNotIn("We tracked it", html)

    def test_no_em_dashes(self):
        html = render_tombstone("Mahan (B) Pecan", ENTRY,
                                cta_html=combo_cta_html("Pecan", species_href="/s"))
        self.assertNotIn("—", html)

    def test_cta_slot_is_rendered_as_markup(self):
        html = render_tombstone("Feijoa trees in Western Australia", ENTRY,
                                cta_html='<a href="/x">link</a>')
        self.assertIn('<a href="/x">link</a>', html)


class ComboCtaTest(unittest.TestCase):
    """DEC-294: a combo tombstone offers links, never a signup. The banner that
    prompted that decision POSTed an action the server never had, enrolling
    people in the digest while telling them they were watching a species."""

    def _cta(self, **kw):
        return combo_cta_html("Feijoa", **kw)

    def test_no_form_no_email_input_no_api_call(self):
        html = self._cta(
            variety_links=[{"href": "/variety/feijoa-unique.html",
                            "label": "Unique", "in_stock": True}],
            species_href="/species/feijoa.html",
            state_links=[{"href": "/buy-feijoa-trees-nsw.html", "label": "NSW"}],
            hub_href="/buy-fruit-trees-wa.html")
        self.assertNotIn("<form", html)
        self.assertNotIn("type=\"email\"", html)
        self.assertNotIn("/api/", html)
        self.assertNotIn("subscribe", html.lower())

    def test_in_stock_varieties_lead(self):
        html = self._cta(variety_links=[
            {"href": "/a", "label": "Zzz out", "in_stock": False},
            {"href": "/b", "label": "Aaa in", "in_stock": True},
        ])
        self.assertLess(html.index("Aaa in"), html.index("Zzz out"))

    def test_link_list_is_capped(self):
        html = self._cta(variety_links=[
            {"href": f"/v{i}", "label": f"Variety {i:03d}", "in_stock": True}
            for i in range(40)])
        self.assertEqual(html.count("<li>"), MAX_COMBO_CTA_LINKS)

    def test_empty_slot_falls_back_to_the_species_page(self):
        """feijoa WA tombstones precisely because there is no feijoa in WA."""
        html = self._cta(species_href="/species/feijoa.html")
        self.assertIn("/species/feijoa.html", html)
        self.assertNotIn("<li>", html)

    def test_with_nothing_at_all_it_falls_back_to_the_hub(self):
        html = self._cta(hub_href="/buy-fruit-trees-wa.html",
                         hub_label="Western Australia")
        self.assertIn("/buy-fruit-trees-wa.html", html)

    def test_never_renders_an_empty_box(self):
        self.assertEqual(self._cta().strip(), "")


class PageStateMetaTest(unittest.TestCase):
    def test_round_trips_through_a_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for state in (LIVE, TOMBSTONE, REDIRECT):
                path = Path(tmp) / f"{state}.html"
                path.write_text("<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
                                + page_state_meta(state) + "\n</head>")
                self.assertEqual(read_page_state(path), state)

    def test_a_page_without_the_tag_reads_as_live(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.html"
            path.write_text("<html><head><title>predates this</title></head>")
            self.assertEqual(read_page_state(path), LIVE)

    def test_a_tag_beyond_the_scan_window_is_not_found(self):
        """The scan is bounded, so the tag has to be in the head. This test
        exists so that a builder putting it in the body fails here rather than
        silently publishing a tombstone in the sitemap."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "late.html"
            path.write_text("<html>" + ("x" * (STATE_META_SCAN_BYTES + 1))
                            + page_state_meta(TOMBSTONE))
            self.assertEqual(read_page_state(path), LIVE)

    def test_the_window_clears_a_real_pages_head(self):
        """Measured rather than assumed: a variety page's <head> is about
        3,754 bytes, and render_head() appends extra_head last. A window that
        does not clear the head reads every tombstone as live."""
        golden = (Path(__file__).resolve().parent / "golden" / "expected"
                  / "variety" / "variety" / "apple-dorsett-golden.html")
        if golden.exists():
            head_end = golden.read_bytes().find(b"</head>")
            self.assertGreater(STATE_META_SCAN_BYTES, head_end)

    def test_missing_file_reads_as_the_default(self):
        self.assertEqual(read_page_state("/nonexistent/page.html"), LIVE)

    def test_unknown_state_is_refused(self):
        with self.assertRaises(ValueError):
            page_state_meta("deleted")

    def test_head_extras_carry_the_state(self):
        self.assertIn(STATE_META_NAME, tombstone_head_extras())
        self.assertIn(f'content="{TOMBSTONE}"', tombstone_head_extras())
        self.assertIn(f'content="{REDIRECT}"', stub_head_extras("https://x/y"))


class RedirectStubTest(unittest.TestCase):
    def _stub(self):
        return render_stub(
            head="<head>H</head>", header="<header>N</header>",
            footer="<footer>F</footer>",
            title="Dwarf Lychee Salathiel", target_title="Lychee Salathiel",
            target_href="/variety/lychee-salathiel.html")

    def test_carries_a_visible_link_not_only_a_refresh(self):
        """A stub returns 200, so a reader with meta refresh disabled sees only
        what is on the page."""
        html = self._stub()
        self.assertIn('href="/variety/lychee-salathiel.html"', html)
        self.assertIn("Lychee Salathiel", html)

    def test_refresh_is_instant_and_points_at_the_target(self):
        extras = stub_head_extras("https://treestock.com.au/variety/x.html")
        self.assertIn('http-equiv="refresh"', extras)
        self.assertIn('content="0; url=https://treestock.com.au/variety/x.html"',
                      extras)

    def test_no_watch_form_on_a_stub(self):
        """A watch on a slug that is no longer generated can never fire, so a
        form here is a control that looks like it works and does not."""
        html = self._stub()
        self.assertNotIn("<form", html)
        self.assertNotIn("watch", html.lower())
        self.assertNotIn("/api/", html)

    def test_no_noindex(self):
        """DEC-266 tested noindex on variety URLs and refuted it, and a page
        that noindexes while canonicalling elsewhere contradicts itself."""
        self.assertNotIn("noindex", (self._stub() + stub_head_extras("/x")).lower())

    def test_titles_are_escaped(self):
        html = render_stub(head="", header="", footer="",
                           title='<script>alert(1)</script>',
                           target_title="Safe", target_href="/x")
        self.assertNotIn("<script>alert", html)

    def test_no_em_dashes(self):
        self.assertNotIn("—", self._stub())


class NoEmDashInTemplatesTest(unittest.TestCase):
    """House rule, checked at the source rather than per-render."""

    def test_new_templates_are_clean(self):
        tpl = (Path(__file__).resolve().parent.parent / "tools" / "scrapers"
               / "stocklib" / "templates")
        for name in ("tombstone_block.html.j2", "combo_tombstone_cta.html.j2",
                     "redirect_stub.html.j2"):
            self.assertNotIn("—", (tpl / name).read_text(), name)


class NoProductJsonLdTest(unittest.TestCase):
    """Pinned rather than assumed. It is true by construction today, and it
    stops being true the moment someone feeds last-known prices into the row
    data: the page would advertise a purchasable product that cannot be
    bought."""

    def test_tombstone_block_carries_no_structured_data(self):
        html = render_tombstone("Mahan (B) Pecan", ENTRY)
        self.assertNotIn("application/ld+json", html)
        self.assertFalse(re.search(r'"@type"\s*:\s*"(Product|Offer)"', html))


if __name__ == "__main__":
    unittest.main()
