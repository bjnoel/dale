"""
Tests for the combo (species+state) page lifecycle.

Two failures live here, and they are opposites. The one this fixes is a page
that never dies: build_species_state_pages.py only ever wrote, so a combo that
fell below its threshold served a frozen in-stock table forever. Ten pages were
in that state on 2026-08-16, feijoa WA (889 impressions a year) and tamarillo WA
(676) among them. The one this must not introduce is a page that dies while it
still has stock to show, which is why retention and creation are separate
thresholds.

The DEC-294 guard is here too, at the page level rather than the fragment level:
a combo tombstone must contain no form, no email input and no /api/ call.
Species-level watches were removed deliberately, and the banner that prompted
that decision POSTed an action the server never had.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from stocklib.page_ledger import (  # noqa: E402
    FAMILY_SPECIES_STATE, LIVE, TOMBSTONE, PageLedger, decide_night,
)


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bss = _load(SCRAPERS / "build_species_state_pages.py")

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")


def product(price=30.0, nursery="daleys", title="Feijoa - Unique"):
    return {"nursery_key": nursery, "nursery_name": "Daleys", "title": title,
            "price": price, "available": True, "url": "https://d/p",
            "species": {"common_name": "Feijoa", "latin_name": "Acca sellowiana",
                        "description": "A feijoa."}}


def combo_entry(state_code="WA", species_slug="feijoa", **over):
    # `state_code` is the state; `state` is the lifecycle state. Keeping the
    # test helper honest about that is the point: conflating the two is a real
    # bug this suite caught in the builder.
    entry = {
        "state": LIVE, "state_code": state_code, "species_slug": species_slug,
        "species": "Feijoa", "variety": "",
        "title": f"Feijoa trees in {bss.STATE_FULL_NAMES[state_code]}",
        "first_seen": days_ago(200), "last_seen": days_ago(1),
        "live_days": 180, "in_stock_days": 150, "last_in_stock": days_ago(20),
        "since": days_ago(200), "seeded": True,
        "rows": [{"nursery_key": "daleys", "nursery_name": "Daleys",
                  "title": "Feijoa - Unique", "price": 30.0, "available": True,
                  "url": "https://d/p"}],
        "rows_as_of": days_ago(20), "redirect_to": None, "retired_reason": None,
        "see_also": [], "absent_nights": 1,
    }
    entry.update(over)
    return entry


class RetentionThresholdTest(unittest.TestCase):
    """MIN_PRODUCTS creates a page. RETAIN_MIN_PRODUCTS keeps one. Conflating
    them is what made a page's existence depend on re-earning its threshold
    every single night."""

    def _combos(self, count):
        return {"WA": {"feijoa": [product() for _ in range(count)]},
                "QLD": {}, "NSW": {}, "VIC": {}}

    def test_a_new_combo_still_needs_min_products(self):
        selected = bss.select_combos(self._combos(bss.MIN_PRODUCTS - 1))
        self.assertEqual(selected["WA"], [])

    def test_an_existing_combo_is_retained_on_one_product(self):
        selected = bss.select_combos(self._combos(1), retained={("WA", "feijoa")})
        self.assertEqual([slug for slug, _ in selected["WA"]], ["feijoa"])

    def test_an_existing_combo_with_no_stock_is_not_retained(self):
        """Nothing to render means the tombstone path, not a thin live page."""
        selected = bss.select_combos(
            {"WA": {}, "QLD": {}, "NSW": {}, "VIC": {}},
            retained={("WA", "feijoa")})
        self.assertEqual(selected["WA"], [])

    def test_a_retained_page_does_not_consume_a_cap_slot(self):
        """Otherwise a retained thin page pushes a healthier combo out, and next
        night that one is retained and pushes another out."""
        combos = {"WA": {}, "NSW": {}, "QLD": {}, "VIC": {}}
        for i in range(bss.MAX_COMBOS_PER_STATE + 5):
            combos["NSW"][f"species-{i:02d}"] = [
                product(title=f"S{i} - V") for _ in range(20 - i % 10)]
        combos["NSW"]["thin-retained"] = [product()]

        without = bss.select_combos(combos)
        with_retained = bss.select_combos(
            combos, retained={("NSW", "thin-retained")})

        kept = {slug for slug, _ in without["NSW"]}
        kept_now = {slug for slug, _ in with_retained["NSW"]}
        self.assertNotIn("thin-retained", kept)
        self.assertIn("thin-retained", kept_now)
        self.assertTrue(
            kept.issubset(kept_now),
            "retaining a thin page must not evict a page that was already in")

    def test_retention_keeps_the_list_in_stock_order(self):
        """The index page reads this order."""
        combos = {"WA": {"a": [product() for _ in range(3)],
                         "b": [product() for _ in range(9)]},
                  "QLD": {}, "NSW": {}, "VIC": {}}
        selected = bss.select_combos(combos, retained={("WA", "a"), ("WA", "b")})
        counts = [len(prods) for _, prods in selected["WA"]]
        self.assertEqual(counts, sorted(counts, reverse=True))


class ComboTombstoneTest(unittest.TestCase):
    def setUp(self):
        self.html = bss.build_combo_tombstone(combo_entry(state_code="WA"))

    def test_it_says_what_is_true_instead_of_freezing_old_stock(self):
        self.assertIn("No nursery we track is currently listing", self.html)
        self.assertNotIn("In-stock Feijoa trees", self.html)

    def test_it_keeps_the_heading_and_the_growing_context(self):
        self.assertIn("Buy Feijoa Trees in Western Australia", self.html)
        h1 = self.html.index("<h1")
        callout = self.html.index("No nursery we track is currently listing")
        self.assertLess(h1, callout, "must not lead with the absence")

    def test_it_declares_itself_a_tombstone(self):
        self.assertIn('content="tombstone"', self.html)

    def test_it_drops_the_in_stock_summary_line(self):
        self.assertNotIn("in stock across", self.html)

    def test_dec_294_no_email_capture_anywhere_on_the_page(self):
        """Species-level watches were removed deliberately. The banner that
        prompted DEC-294 POSTed an action the server never had, enrolling
        people in the digest while telling them they were watching a species."""
        self.assertNotIn("<form", self.html)
        self.assertNotIn('type="email"', self.html)
        self.assertNotIn("/api/", self.html)

    def test_it_offers_somewhere_to_go(self):
        self.assertIn("/species/feijoa.html", self.html)
        self.assertIn("buy-feijoa-trees-queensland.html", self.html)

    def test_it_does_not_point_at_stock_that_cannot_ship_there(self):
        """A combo tombstones precisely because nothing ships that species to
        that state, so any variety listed would be one the reader cannot buy.
        Same mistake as a "Ships to WA" badge."""
        self.assertNotIn("varieties in stock now", self.html)

    def test_no_em_dashes(self):
        self.assertNotIn("—", self.html)

    def test_it_survives_a_thin_entry(self):
        html = bss.build_combo_tombstone(
            {"state_code": "VIC", "species_slug": "feijoa", "species": "Feijoa",
             "title": "Feijoa trees in Victoria", "rows": []})
        self.assertIn("No nursery we track is currently listing", html)


class ComboLifecycleDecisionTest(unittest.TestCase):
    """The combo family has no rename and no retired branch: its key comes from
    taxonomy plus a state code, so it cannot move and cannot leave."""

    def _ledger(self, extra=None):
        led = PageLedger(FAMILY_SPECIES_STATE)
        for i in range(30):
            led.seed(f"buy-species{i:02d}-trees-victoria", today=days_ago(1),
                     **combo_entry(state_code="VIC",
                                   species_slug=f"species{i:02d}",
                                   absent_nights=0))
        for key, entry in (extra or {}).items():
            led.pages[key] = entry
        return led

    def _tonight(self, led):
        return [k for k in led.pages if k.startswith("buy-species")]

    def test_zero_stock_tombstones_after_the_exit_guard(self):
        led = self._ledger({"buy-feijoa-trees-western-australia": combo_entry()})
        tonight = self._tonight(led)
        plan = decide_night(led, tonight, today=TODAY)
        self.assertEqual(plan.tombstoned, ["buy-feijoa-trees-western-australia"])
        self.assertEqual(
            led.pages["buy-feijoa-trees-western-australia"]["state"], TOMBSTONE)

    def test_a_combo_back_in_stock_returns_to_live(self):
        led = self._ledger({
            "buy-feijoa-trees-western-australia": combo_entry(state=TOMBSTONE)})
        led.observe("buy-feijoa-trees-western-australia", today=TODAY,
                    rows=[{"nursery_key": "daleys", "available": True}])
        self.assertEqual(
            led.pages["buy-feijoa-trees-western-australia"]["state"], LIVE)

    def test_a_combo_is_never_retired(self):
        """No retired_check is passed for this family, so the only outcomes are
        tombstone, hold, or the entry-guard delete."""
        led = self._ledger({"buy-feijoa-trees-western-australia": combo_entry()})
        plan = decide_night(led, self._tonight(led), today=TODAY,
                            allow_delete=True)
        self.assertEqual(plan.retired, [])


class SeedFromDiskTest(unittest.TestCase):
    """The 10 orphans are on disk and in no snapshot, so seeding has to read the
    filesystem. They are exactly the pages that need an entry most."""

    def test_it_finds_combo_pages_and_ignores_everything_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for name in ("buy-feijoa-trees-western-australia.html",
                         "buy-tamarillo-trees-western-australia.html",
                         "buy-fruit-trees-wa.html",
                         "buy-fruit-trees-by-species-state.html",
                         "index.html"):
                (out / name).write_text("<html></html>")
            led = PageLedger(FAMILY_SPECIES_STATE)
            count = bss.seed_from_disk(led, out, TODAY)
            self.assertEqual(count, 2)
            self.assertEqual(sorted(led.pages), [
                "buy-feijoa-trees-western-australia",
                "buy-tamarillo-trees-western-australia"])
            entry = led.pages["buy-feijoa-trees-western-australia"]
            self.assertEqual(entry["state_code"], "WA")
            self.assertEqual(entry["species_slug"], "feijoa")
            self.assertTrue(entry["seeded"])

    def test_the_lifecycle_state_is_not_clobbered_by_the_state_code(self):
        """`state` is the lifecycle field. A seeded combo writing its state code
        there would have set state="WA", which is not a lifecycle state."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "buy-feijoa-trees-victoria.html").write_text("<html></html>")
            led = PageLedger(FAMILY_SPECIES_STATE)
            bss.seed_from_disk(led, out, TODAY)
            self.assertEqual(led.pages["buy-feijoa-trees-victoria"]["state"],
                             LIVE)

    def test_it_does_not_re_seed_a_page_the_ledger_knows(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "buy-feijoa-trees-western-australia.html").write_text("x")
            led = PageLedger(FAMILY_SPECIES_STATE)
            led.pages["buy-feijoa-trees-western-australia"] = combo_entry()
            self.assertEqual(bss.seed_from_disk(led, out, TODAY), 0)


class ComboKeyTest(unittest.TestCase):
    def test_the_key_is_the_url_identity(self):
        self.assertEqual(bss.combo_key("feijoa", "WA"),
                         "buy-feijoa-trees-western-australia")


if __name__ == "__main__":
    unittest.main()
