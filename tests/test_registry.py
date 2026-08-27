"""
Tests for stocklib.registry -- the nursery registry that replaced shipping.py's
three parallel dicts.

The EXPECTED_* values below are a verbatim copy of the pre-refactor shipping.py
dict literals. They are the oracle: the registry's derived dicts must equal them
exactly, so the dataclass restructuring cannot have changed any nursery's
shipping states, name, or local-delivery. Also checks shipping.py still
re-exports the same objects.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from stocklib import registry

# --- Oracle: verbatim copies of the pre-refactor shipping.py literals ---

EXPECTED_SHIPPING = {
    "daleys": ["NSW", "VIC", "QLD", "SA", "WA", "ACT"],
    "ross-creek": ["NSW", "VIC", "QLD", "SA", "ACT"],
    "ladybird": ["NSW", "VIC", "QLD", "ACT"],
    "fruitopia": ["NSW", "VIC", "QLD", "SA", "ACT"],
    "primal-fruits": ["WA"],
    "guildford": ["WA"],
    "fruit-salad-trees": ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "ACT"],
    "diggers": ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"],
    "all-season-plants-wa": ["WA"],
    "ausnurseries": ["NSW", "VIC", "QLD", "SA", "ACT"],
    "fruit-tree-cottage": ["NSW", "VIC", "QLD", "SA", "ACT"],
    "heritage-fruit-trees": ["NSW", "VIC", "QLD", "SA", "ACT"],
    "perth-mobile-nursery": ["WA"],
    "yalca-fruit-trees": ["NSW", "VIC", "QLD", "ACT"],
    "forever-seeds": ["NSW", "VIC", "QLD", "SA", "NT", "ACT"],
    "garden-express": ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"],
    "plantnet": ["NSW", "VIC", "QLD", "ACT"],
    "fruit-tree-lane": ["NSW", "VIC", "QLD", "SA", "ACT"],
    "engalls": ["NSW", "VIC", "QLD", "ACT"],
    "rayners": ["VIC"],
    "garden-world": ["VIC"],
    "diacos": ["VIC"],
    "wild-garden-organics": ["QLD", "NSW", "VIC", "SA", "ACT"],
    "st-clements-citrus": ["WA"],
    "the-heritage-nursery": ["ACT"],
    "all-rare-herbs": ["QLD", "NSW", "VIC", "SA", "ACT"],
    # Added after the refactor, so not part of the original oracle. Kept in the
    # same dict because the test's job is now twofold: prove the refactor
    # changed nothing, and make any later edit to an existing nursery's states
    # a deliberate two-file change rather than a one-line slip.
    "perrys": ["SA"],
}

EXPECTED_NAMES = {
    "daleys": "Daleys Fruit Trees",
    "ross-creek": "Ross Creek Tropicals",
    "ladybird": "Ladybird Nursery",
    "fruitopia": "Fruitopia",
    "primal-fruits": "Primal Fruits Perth",
    "guildford": "Guildford Garden Centre",
    "fruit-salad-trees": "Fruit Salad Trees",
    "diggers": "The Diggers Club",
    "all-season-plants-wa": "All Season Plants WA",
    "ausnurseries": "Aus Nurseries",
    "fruit-tree-cottage": "Fruit Tree Cottage",
    "heritage-fruit-trees": "Heritage Fruit Trees",
    "perth-mobile-nursery": "Perth Mobile Nursery",
    "yalca-fruit-trees": "Yalca Fruit Trees",
    "forever-seeds": "Forever Seeds",
    "garden-express": "Garden Express",
    "plantnet": "PlantNet",
    "fruit-tree-lane": "Fruit Tree Lane",
    "engalls": "Engall's Nursery",
    "rayners": "Rayners Orchard",
    "garden-world": "Garden World",
    "diacos": "Diaco's Garden Nursery",
    "wild-garden-organics": "Wild Garden Organics",
    "st-clements-citrus": "St Clements Citrus",
    "the-heritage-nursery": "The Heritage Nursery",
    "all-rare-herbs": "All Rare Herbs",
    "perrys": "Perry's Fruit & Nut Nursery",
}

EXPECTED_LOCAL = {
    "primal-fruits": {"area": "Perth metro", "state": "WA"},
    "guildford": {"area": "Perth metro", "state": "WA"},
    "all-season-plants-wa": {"area": "Perth (pickup)", "state": "WA"},
    "perth-mobile-nursery": {"area": "Perth metro", "state": "WA"},
    "rayners": {"area": "Victoria", "state": "VIC"},
    "garden-world": {"area": "Melbourne metro", "state": "VIC"},
    "diacos": {"area": "Melbourne metro", "state": "VIC"},
    "st-clements-citrus": {"area": "WA", "state": "WA"},
    "the-heritage-nursery": {"area": "ACT + Queanbeyan", "state": "ACT"},
    "perrys": {"area": "Adelaide (pickup)", "state": "SA"},
}


class DerivedDictsMatchOracleTest(unittest.TestCase):
    def test_shipping_map(self):
        self.assertEqual(registry.SHIPPING_MAP, EXPECTED_SHIPPING)

    def test_nursery_names(self):
        self.assertEqual(registry.NURSERY_NAMES, EXPECTED_NAMES)

    def test_local_delivery(self):
        self.assertEqual(registry.LOCAL_DELIVERY, EXPECTED_LOCAL)

    def test_every_nursery_has_name_and_shipping(self):
        for n in registry.NURSERIES:
            self.assertTrue(n.name, f"{n.key} missing name")
            self.assertTrue(n.ships_to, f"{n.key} missing ships_to")


class HelpersTest(unittest.TestCase):
    def test_restriction_warning(self):
        self.assertEqual(registry.restriction_warning("ross-creek"), "No WA/NT/TAS")
        self.assertEqual(registry.restriction_warning("daleys"), "No NT/TAS")  # ships WA, not NT/TAS
        self.assertEqual(registry.restriction_warning("diggers"), "")          # ships everywhere
        self.assertEqual(registry.restriction_warning("unknown"), "No WA/NT/TAS")

    def test_delivery_label(self):
        self.assertEqual(registry.delivery_label("primal-fruits"), "Perth metro only")
        self.assertEqual(registry.delivery_label("all-season-plants-wa"), "Perth (pickup) only")
        self.assertEqual(registry.delivery_label("daleys"), "")

    def test_nursery_ships_to(self):
        self.assertTrue(registry.nursery_ships_to("daleys", "WA"))
        self.assertFalse(registry.nursery_ships_to("ross-creek", "WA"))


class ShippingShimTest(unittest.TestCase):
    def test_shim_reexports_registry_objects(self):
        import shipping
        self.assertEqual(shipping.SHIPPING_MAP, EXPECTED_SHIPPING)
        self.assertEqual(shipping.NURSERY_NAMES, EXPECTED_NAMES)
        self.assertIs(shipping.restriction_warning, registry.restriction_warning)
        self.assertIs(shipping.SHIPPING_MAP, registry.SHIPPING_MAP)


class NurseryLocationTests(unittest.TestCase):
    """Location is a fact about the nursery, not about its shop software.

    Before 2026-08-24 it was a per-scraper config key. The WooCommerce, Ecwid
    and Wix scrapers wrote it into their snapshots; the Shopify one carried the
    string but never emitted it, and the Daleys CSV feed had no such key. So
    /nursery/daleys.html and /nursery/ross-creek.html both showed "Australia"
    while /nursery/guildford.html showed "Guildford, WA".
    """

    def test_every_tracked_nursery_has_a_location(self):
        missing = [n.key for n in registry.NURSERIES if not n.location]
        self.assertEqual(missing, [], "a nursery with no location renders as "
                                      "the generic 'Australia' fallback")

    def test_the_two_the_scraper_configs_never_carried(self):
        # Sourced 2026-08-24: daleysfruit.com.au/contact.html gives
        # "36 Daley's Lane, Geneva via Kyogle NSW 2474"; Heritage Fruit Trees
        # is 297 Back Raglan Road, Beaufort VIC 3373.
        self.assertEqual(registry.nursery_location("daleys"), "Kyogle, NSW")
        self.assertEqual(registry.nursery_location("heritage-fruit-trees"), "Beaufort, VIC")

    def test_the_shopify_nurseries_that_used_to_read_australia(self):
        self.assertEqual(registry.nursery_location("ross-creek"), "Gympie, QLD")
        self.assertEqual(registry.nursery_location("all-season-plants-wa"), "Perth, WA")

    def test_an_unknown_key_falls_back_rather_than_raising(self):
        self.assertEqual(registry.nursery_location("no-such-nursery"), "Australia")
        self.assertEqual(registry.nursery_location("no-such-nursery", "Unknown"), "Unknown")

    def test_all_rare_herbs_stays_australia_because_they_asked(self):
        """The nursery asked to be listed as 'Australia' (2026-07-27) after
        changing hands and moving from Mapleton QLD. Not a missing value."""
        self.assertEqual(registry.nursery_location("all-rare-herbs"), "Australia")

    def test_no_location_claims_a_suburb_the_note_contradicts(self):
        """'pickup only, Ellenbrook' was hand-written into build_location_pages
        in March 2026 with no source, and every other record said Perth."""
        self.assertNotIn("Ellenbrook", "".join(n.location for n in registry.NURSERIES))


if __name__ == "__main__":
    unittest.main()
