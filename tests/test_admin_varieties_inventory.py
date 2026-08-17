"""
/admin/varieties as a ledger-backed inventory (DAL-283).

The page it replaced knew only slug strings, because the two files
`load_variety_curation` reads carry nothing else. These tests are about the
thing that changed: the page ledger has per-page state and history, and reading
it is where the value is.

What is deliberately pinned here:
  - the noise check does not fire on species names (Dragon Fruit is a species)
  - a redirect and a tombstone are counted as themselves, not as absences
  - the ledger being missing renders a page rather than raising
  - the payload stays compact, because the ledger is 3.1MB
  - nothing on this page writes anything (DAL-284 is the write phase)

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


def row(key="daleys", available=True, url=None):
    return {"nursery_key": key, "nursery_name": key.title(), "title": "x",
            "price": 30.0, "available": available,
            "url": url or f"https://{key}.example/p"}


# A miniature catalogue exercising every queue at once.
PAGES = {
    # Six nurseries, in stock. The healthy case.
    "avocado-hass": entry(rows=[row("daleys"), row("ladybird")]),
    # One product at one nursery, and it has never sold.
    "avocado-fuerte": entry(in_stock_days=0, last_in_stock=None,
                            rows=[row("daleys", available=False)]),
    # Sold before, nothing available today.
    "avocado-shepard": entry(rows=[row("daleys", available=False),
                                   row("ladybird", available=False)]),
    # Absent tonight: one more night and it tombstones.
    "avocado-wurtz": entry(absent_nights=1, rows=[row("daleys")]),
    # Listing noise, and it shadows avocado-hass which is live.
    "avocado-hass-potted": entry(rows=[row("exotica")]),
    # A redirect and a tombstone, which is the whole point of reading the ledger.
    "avocado-hass-type-a": entry(state="redirect", redirect_to="avocado-hass",
                                 since="2026-08-17"),
    "avocado-gone": entry(state="tombstone", since="2026-08-17",
                          rows=[row("daleys", available=False)]),
    # The only live page for its species.
    "durian-monthong": entry(species="Durian", rows=[row("ladybird")]),
    # Dragon Fruit is a SPECIES. "fruit" here is not listing noise.
    "dragon-fruit-asunta": entry(species="Dragon Fruit", rows=[row("daleys")]),
    # Banana keeps dwarf: Dwarf Cavendish is a cultivar, not a pot size.
    "banana-dwarf-cavendish": entry(species="Banana", rows=[row("daleys")]),
    "banana-ladyfinger": entry(species="Banana", rows=[row("daleys")]),
}


class NoiseDetectionTests(unittest.TestCase):
    """The check that most easily becomes wrong, because the species name and
    the noise vocabulary overlap."""

    def test_species_prefix_is_not_noise(self):
        self.assertEqual(
            admin_view.noisy_slug_tokens("dragon-fruit-asunta", "Dragon Fruit"), [])
        self.assertEqual(
            admin_view.noisy_slug_tokens("bunya-nut-pine", "Bunya Nut"), [])

    def test_the_same_token_after_the_species_is_noise(self):
        """grape-fruit-wheeny is species Grape, so `fruit` is the parser's miss.
        The identical token in dragon-fruit-* is half the species name."""
        self.assertEqual(
            admin_view.noisy_slug_tokens("grape-fruit-wheeny", "Grape"), ["fruit"])
        self.assertEqual(
            admin_view.noisy_slug_tokens("macadamia-nut-a16", "Macadamia"), ["nut"])

    def test_bananas_keep_dwarf(self):
        """_strip_listing_noise(keep_dwarf=True) makes this exception for the
        same reason: Dwarf Cavendish is the cultivar's name."""
        self.assertEqual(
            admin_view.noisy_slug_tokens("banana-dwarf-cavendish", "Banana"), [])
        self.assertEqual(
            admin_view.noisy_slug_tokens("nectarine-royal-gem-dwf", "Nectarine"),
            ["dwf"])

    def test_age_is_never_a_cultivar(self):
        self.assertIn(
            "<age>",
            admin_view.noisy_slug_tokens("jaboticaba-sabara-2-years-old", "Jaboticaba"))

    def test_a_clean_twin_is_only_reported_when_it_exists(self):
        live = {"avocado-hass"}
        self.assertEqual(
            admin_view.clean_twin("avocado-hass-potted", ["potted"], live),
            "avocado-hass")
        # Same noise, no such page: a badly named page, not a duplicate one.
        self.assertEqual(
            admin_view.clean_twin("avocado-nowhere-potted", ["potted"], live), "")


class InventoryModelTests(unittest.TestCase):
    def setUp(self):
        self.inv = admin_view.build_variety_inventory(
            PAGES, watch_counts={"avocado-hass": 2})
        self.q = {q["key"]: q["count"] for q in self.inv["attention"]}

    def test_states_are_counted_as_themselves_not_as_absences(self):
        self.assertEqual(self.inv["counts"],
                         {"live": 9, "redirect": 1, "tombstone": 1, "retired": 0})
        self.assertEqual(self.inv["total"], 11)

    def test_every_attention_queue_counts_the_right_pages(self):
        self.assertEqual(self.q["absent"], 1)     # avocado-wurtz
        self.assertEqual(self.q["never"], 1)      # avocado-fuerte
        self.assertEqual(self.q["oos"], 1)        # avocado-shepard
        self.assertEqual(self.q["noisy"], 1)      # avocado-hass-potted
        self.assertEqual(self.q["lonely"], 2)     # Durian and Dragon Fruit
        # One product at one nursery: fuerte, hass-potted, wurtz, durian,
        # dragon-fruit, banana-dwarf-cavendish, banana-ladyfinger.
        self.assertEqual(self.q["single"], 7)

    def test_a_tombstoned_page_is_in_no_queue(self):
        """Queues are work on live pages. A tombstone has already been decided,
        and counting it as `never in stock` would put settled pages in a queue
        that is supposed to shrink."""
        gone = next(f for f in self.inv["facts"] if f["slug"] == "avocado-gone")
        self.assertEqual([k for k, v in gone["flags"].items() if v], [])

    def test_a_noisy_page_names_the_clean_page_it_shadows(self):
        shadow = next(f for f in self.inv["facts"]
                      if f["slug"] == "avocado-hass-potted")
        self.assertEqual(shadow["clean_twin"], "avocado-hass")
        self.assertEqual(self.inv["shadowing"], 1)
        note = next(q["note"] for q in self.inv["attention"] if q["key"] == "noisy")
        self.assertIn("shadow a clean page", note)

    def test_species_rows_count_live_pages_and_show_the_other_states(self):
        rows = {r["name"]: r for r in self.inv["species"]}
        avo = rows["Avocado"]
        self.assertEqual(avo["varieties"], 5)   # the redirect and tombstone are not
        self.assertEqual(avo["redirect"], 1)
        self.assertEqual(avo["tombstone"], 1)
        self.assertEqual(avo["never"], 1)
        self.assertEqual(avo["noisy"], 1)
        self.assertEqual(self.inv["species_count"], 4)

    def test_species_rows_lead_with_the_biggest(self):
        self.assertEqual(self.inv["species"][0]["name"], "Avocado")

    def test_watch_counts_reach_the_facts(self):
        hass = next(f for f in self.inv["facts"] if f["slug"] == "avocado-hass")
        self.assertEqual(hass["watchers"], 2)

    def test_an_empty_ledger_is_a_model_not_a_crash(self):
        empty = admin_view.build_variety_inventory({})
        self.assertEqual(empty["total"], 0)
        self.assertEqual(empty["species"], [])
        self.assertEqual([q["count"] for q in empty["attention"]], [0] * 6)


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.inv = admin_view.build_variety_inventory(PAGES)
        self.payload = admin_view.build_varieties_payload(self.inv)

    def test_a_row_matches_the_declared_columns(self):
        self.assertEqual(len(self.payload["cols"]), len(self.payload["rows"][0]))

    def test_flag_bits_are_in_the_declared_order(self):
        """The browser reads a bitmask, so the order of `flags` is load-bearing.
        Reordering ATTENTION_QUEUES without this test would silently relabel
        every filter."""
        self.assertEqual(self.payload["flags"],
                         [k for k, _, _ in admin_view.ATTENTION_QUEUES])
        idx = self.payload["flags"].index("noisy")
        row = next(r for r in self.payload["rows"] if r[0] == "avocado-hass-potted")
        self.assertTrue(row[7] & (1 << idx))

    def test_a_redirect_carries_its_target(self):
        row = next(r for r in self.payload["rows"] if r[0] == "avocado-hass-type-a")
        self.assertEqual(self.payload["states"][row[2]], "redirect")
        self.assertEqual(row[8], "avocado-hass")

    def test_the_payload_is_not_the_ledger(self):
        """The one rule this page has. The ledger is 3.1MB and
        /variety/index.html is already 1.4MB; the compact form measured 148KB
        for 2,767 real pages, so a per-page budget of 100 bytes has headroom
        and still fails loudly if someone inlines the rows."""
        size = len(json.dumps(self.payload, separators=(",", ":")))
        self.assertLess(size / max(len(self.payload["rows"]), 1), 100)


class RenderTests(unittest.TestCase):
    def model(self, **over):
        inv = admin_view.build_variety_inventory(PAGES)
        inv.update({"present": True, "path": "/x", "error": "",
                    "updated": "2026-08-17", "skipped_nights": 0})
        inv.update(over)
        return {"inventory": inv, "varieties": {"index_size": 11}}

    def test_the_page_names_every_state_and_queue(self):
        html = admin_view.render_varieties_html(self.model())
        self.assertIn("redirect", html)
        self.assertIn("tombstone", html)
        for _, label, _ in admin_view.ATTENTION_QUEUES:
            with self.subTest(label=label):
                self.assertIn(label, html)

    def test_species_rows_render_without_javascript(self):
        """The counts are the part that has to survive a failed fetch, so they
        are in the HTML rather than built from the payload."""
        html = admin_view.render_varieties_html(self.model())
        self.assertIn('data-species="Avocado"', html)
        self.assertIn('data-species="Durian"', html)

    def test_the_catalogue_is_not_inlined(self):
        """2,767 slugs in the HTML is the failure this page was designed around.
        The fixture has 11 pages, so assert on the mechanism: the per-variety
        rows arrive from the payload URL, not from the document."""
        html = admin_view.render_varieties_html(self.model())
        self.assertIn("/admin/varieties.json", html)
        self.assertNotIn("avocado-hass-type-a", html)

    def test_a_missing_ledger_renders_an_explanation(self):
        html = admin_view.render_varieties_html(
            {"inventory": {"present": False, "path": "/opt/dale/data/x.json",
                           "error": "no pages object"},
             "varieties": {"index_size": 0}})
        self.assertIn("No page ledger", html)
        self.assertIn("/opt/dale/data/x.json", html)
        self.assertIn("no pages object", html)

    def test_a_stale_ledger_says_so(self):
        html = admin_view.render_varieties_html(self.model(updated="2020-01-01"))
        self.assertIn("2020-01-01", html)
        self.assertIn("has not run yet", html)

    def test_the_page_writes_nothing(self):
        """Phase 1 is read only and that is the reason it carries no new risk.
        A form or a POST here means the CSRF work in section 6 of
        docs/admin-varieties-plan.md was skipped rather than done."""
        html = admin_view.render_varieties_html(self.model())
        for token in ("<form", "method=\"post\"", "method='post'", "POST"):
            with self.subTest(token=token):
                self.assertNotIn(token, html)

    def test_the_json_route_is_registered_and_separate(self):
        self.assertIn("/admin/varieties.json", admin_view.ADMIN_JSON)
        self.assertNotIn("/admin/varieties.json", admin_view.ADMIN_RENDERERS)
        payload = admin_view.ADMIN_JSON["/admin/varieties.json"](self.model())
        self.assertEqual(len(payload["rows"]), len(PAGES))


class LoadFromDiskTests(unittest.TestCase):
    def test_reads_the_ledger_the_nightly_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            led = data / "page-ledger"
            led.mkdir()
            (led / "variety.json").write_text(json.dumps({
                "schema": 1, "family": "variety", "updated": "2026-08-17",
                "skipped_nights": 0, "review": [], "pages": PAGES}))
            inv = admin_view.load_variety_inventory(data)
        self.assertTrue(inv["present"])
        self.assertEqual(inv["updated"], "2026-08-17")
        self.assertEqual(inv["counts"]["live"], 9)

    def test_a_missing_ledger_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            inv = admin_view.load_variety_inventory(Path(tmp))
        self.assertFalse(inv["present"])
        self.assertEqual(inv["error"], "")
        self.assertIn("variety.json", inv["path"])

    def test_a_corrupt_ledger_is_reported_not_raised(self):
        """/admin is what you open when something is wrong, so it has to render
        when the file it wants is the thing that broke."""
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "page-ledger").mkdir()
            (data / "page-ledger" / "variety.json").write_text("{ truncated")
            inv = admin_view.load_variety_inventory(data)
        self.assertFalse(inv["present"])
        self.assertTrue(inv["error"])


if __name__ == "__main__":
    unittest.main()
