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
    "ross-creek": ["NSW", "VIC", "QLD", "ACT"],
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
    "yalca-fruit-trees": ["NSW", "VIC", "QLD", "SA", "ACT"],
    "forever-seeds": ["NSW", "VIC", "QLD", "SA", "ACT"],
    "garden-express": ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"],
    "plantnet": ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "ACT"],
    "fruit-tree-lane": ["NSW", "VIC", "QLD", "SA", "ACT"],
    "engalls": ["NSW", "VIC", "QLD", "SA", "ACT"],
    "rayners": ["VIC"],
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
}

EXPECTED_LOCAL = {
    "primal-fruits": {"area": "Perth metro", "state": "WA"},
    "guildford": {"area": "Perth metro", "state": "WA"},
    "all-season-plants-wa": {"area": "Perth (pickup)", "state": "WA"},
    "perth-mobile-nursery": {"area": "Perth metro", "state": "WA"},
    "rayners": {"area": "Victoria", "state": "VIC"},
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


if __name__ == "__main__":
    unittest.main()
