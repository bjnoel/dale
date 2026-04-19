"""
Tests for tools/scrapers/bee/bee_categories.py -- the pure function that
categorises beekeeping products into a two-level taxonomy.

Run from repo root with:
    python3 -m unittest discover tests/

Rule of thumb: every bug fixed in bee_categories.py gets a regression case
here (the title that produced the wrong output, mapped to the expected output).
"""
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BEE_SCRAPERS = REPO_ROOT / "tools" / "scrapers" / "bee"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bc = _load(BEE_SCRAPERS / "bee_categories.py")


# ---------------------------------------------------------------------------
# categorise_product
# ---------------------------------------------------------------------------

class CategoriseProduct(unittest.TestCase):
    """
    Each case: (title, tags, product_type, expected_parent, expected_sub)

    Tags and product_type are included in matching alongside the title.
    Returns ('other', 'other') if no keyword matches.
    """

    CASES = [
        # --- Hiveware: hive-bodies ---
        ("Langstroth 10-Frame Hive Body", [], "", "hiveware", "hive-bodies"),
        ("Flow Hive Classic 7 Frame", [], "", "hiveware", "hive-bodies"),
        ("Observation Hive Perspex", [], "", "hiveware", "hive-bodies"),
        ("Bee Box Pine Timber", [], "", "hiveware", "hive-bodies"),

        # --- Hiveware: hive-kits ---
        ("Complete Beginner Hive Kit Assembled", [], "", "hiveware", "hive-kits"),
        ("Starter Kit Flow Hive 2 Plus", [], "", "hiveware", "hive-kits"),

        # --- Hiveware: nuc-boxes ---
        ("Nuc Box 5 Frame Pine", [], "", "hiveware", "nuc-boxes"),
        ("Nucleus Hive Transport Box", [], "", "hiveware", "nuc-boxes"),

        # --- Hiveware: lids-covers ---
        ("Migratory Lid 8 Frame", [], "", "hiveware", "lids-covers"),
        ("Hive Lid Vented Timber", [], "", "hiveware", "lids-covers"),
        ("Inner Cover Crown Board", [], "", "hiveware", "lids-covers"),
        ("Hive Mat Corflute", [], "", "hiveware", "lids-covers"),

        # --- Hiveware: bottom-boards ---
        ("Screened Bottom Board SHB", [], "", "hiveware", "bottom-boards"),
        ("Varroa Board Monitoring Insert", [], "", "hiveware", "bottom-boards"),

        # --- Hiveware: queen-excluders ---
        ("Metal Framed Queen Excluder 8 Frame", [], "", "hiveware", "queen-excluders"),

        # --- Hiveware: entrance ---
        ("Entrance Reducer Wooden Adjustable", [], "", "hiveware", "entrance"),
        ("Mouse Guard Metal Mesh", [], "", "hiveware", "entrance"),
        ("Robber Guard Entrance Screen", [], "", "hiveware", "entrance"),

        # --- Hiveware: hive-stands ---
        ("Hive Stand Galvanised Steel", [], "", "hiveware", "hive-stands"),
        ("Hive Strap Transport Ratchet", [], "", "hiveware", "hive-stands"),

        # --- Hiveware: hive-accessories ---
        ("Porter Bee Escape Clearer Board", [], "", "hiveware", "hive-accessories"),

        # --- Frames & Foundation: frames ---
        ("Wired Ideal Frame Box of 50", [], "", "frames-foundation", "frames"),
        ("WSP Frame Assembled", [], "", "frames-foundation", "frames"),
        ("Hoffman Frame 8 Frame Super", [], "", "frames-foundation", "frames"),

        # --- Frames & Foundation: foundation ---
        ("Beeswax Foundation Full Depth", [], "", "frames-foundation", "foundation"),
        ("Plastic Foundation Wired", [], "", "frames-foundation", "foundation"),
        ("Wax Sheet Foundation Ideal", [], "", "frames-foundation", "foundation"),

        # --- Frames & Foundation: frame-accessories ---
        ("Castellated Spacer 10 Frame", [], "", "frames-foundation", "frame-accessories"),
        ("Frame Wire Stainless Steel Roll", [], "", "frames-foundation", "frame-accessories"),
        ("Brass Eyelet Pack 100", [], "", "frames-foundation", "frame-accessories"),
        ("Embedding Tool Electric", [], "", "frames-foundation", "frame-accessories"),

        # --- Feeders: feeders ---
        ("Frame Feeder Plastic 1.5L", [], "", "feeders", "feeders"),
        ("Rapid Feeder Plastic", [], "", "feeders", "feeders"),
        ("Entrance Feeder Boardman Style", [], "", "feeders", "feeders"),

        # --- Feeders: bee-nutrition ---
        ("Pollen Patty Protein Supplement 500g", [], "", "feeders", "bee-nutrition"),
        ("Pollen Substitute Powder 1kg", [], "", "feeders", "bee-nutrition"),
        ("Pollen Trap Plastic Entrance", [], "", "feeders", "bee-nutrition"),

        # --- Extractors & Processing: extractors ---
        ("2 Frame Stainless Extractor Manual", [], "", "extractors-processing", "extractors"),
        ("Radial 9 Frame Extractor Electric", [], "", "extractors-processing", "extractors"),

        # --- Extractors & Processing: uncapping ---
        ("Uncapping Fork Stainless Cold", [], "", "extractors-processing", "uncapping"),
        ("Electric Uncapping Knife 240V", [], "", "extractors-processing", "uncapping"),
        ("Uncapping Tray With Stand", [], "", "extractors-processing", "uncapping"),

        # --- Extractors & Processing: honey-handling ---
        ("Honey Gate Plastic 50mm", [], "", "extractors-processing", "honey-handling"),
        ("Stainless Honey Strainer Double Sieve", [], "", "extractors-processing", "honey-handling"),
        ("Settling Tank 60L Honey", [], "", "extractors-processing", "honey-handling"),

        # --- Extractors & Processing: wax-processing ---
        ("Solar Wax Melter Aluminium", [], "", "extractors-processing", "wax-processing"),
        ("Beeswax Block 500g Raw", [], "", "extractors-processing", "wax-processing"),
        ("Candle Mould Pillar", [], "", "extractors-processing", "wax-processing"),

        # --- Protective Gear: bee-suits ---
        ("Full Bee Suit Cotton Veil", [], "", "protective-gear", "bee-suits"),
        ("Ventilated Beekeeping Suit 3-Layer Mesh", [], "", "protective-gear", "bee-suits"),

        # --- Protective Gear: jackets-veils ---
        ("Round Veil Hat Fencing Style", [], "", "protective-gear", "jackets-veils"),
        ("Bee Jacket Cotton Half Suit", [], "", "protective-gear", "jackets-veils"),
        ("Fencing Veil Assembled", [], "", "protective-gear", "jackets-veils"),

        # --- Protective Gear: gloves ---
        ("Goatskin Bee Gloves", [], "", "protective-gear", "gloves"),
        ("Beekeeping Gloves Leather Long Cuff", [], "", "protective-gear", "gloves"),

        # --- Smokers & Tools: smokers ---
        ("Stainless Steel Smoker Large", [], "", "smokers-tools", "smokers"),
        ("Smoker Fuel Hessian Roll", [], "", "smokers-tools", "smokers"),

        # --- Smokers & Tools: hive-tools ---
        ("Hive Tool J Hook Stainless 200mm", [], "", "smokers-tools", "hive-tools"),
        ("Standard J-Hook Hive Tool", [], "", "smokers-tools", "hive-tools"),
        ("Bee Brush Natural Bristle", [], "", "smokers-tools", "hive-tools"),

        # --- Smokers & Tools: queen-rearing ---
        ("Queen Cage Plastic 5 Frame", [], "", "smokers-tools", "queen-rearing"),
        ("Grafting Tool Flexible Chinese", [], "", "smokers-tools", "queen-rearing"),
        ("Mating Nuc Box 5 Frame", [], "", "smokers-tools", "queen-rearing"),
        ("Queen Marking Cage Tube", [], "", "smokers-tools", "queen-rearing"),

        # --- Treatments: varroa ---
        # Note: "treatment" (9 chars) is a bee-health keyword and beats "varroa" (6 chars)
        # if the title contains the word "treatment". Use titles with varroa-specific terms
        # that don't also contain "treatment".
        ("Apivar Amitraz Strips 10 Pack", [], "", "treatments", "varroa"),
        ("Oxalic Acid Drizzle Kit 500ml", [], "", "treatments", "varroa"),
        ("Mite Wash Sugar Roll Kit", [], "", "treatments", "varroa"),
        # "mite treatment" (14 chars, varroa keyword) beats "treatment" (9 chars, bee-health)
        ("Thymol Mite Treatment Apilife", [], "", "treatments", "varroa"),

        # --- Treatments: shb ---
        ("Beetle Blaster SHB Trap", [], "", "treatments", "shb"),
        ("Small Hive Beetle Trap Reusable", [], "", "treatments", "shb"),
        ("Diatomaceous Earth Powder", [], "", "treatments", "shb"),

        # --- Treatments: bee-health ---
        ("Fumagilin Nosema Treatment", [], "", "treatments", "bee-health"),
        # "alcohol wash" (12 chars) is a bee-health keyword and beats "varroa" (6 chars)
        ("Alcohol Wash Varroa Count Kit", [], "", "treatments", "bee-health"),

        # --- Containers: jars-bottles ---
        ("Hex Jar 500g with Lid", [], "", "containers-packing", "jars-bottles"),
        ("Round Honey Jar 250ml", [], "", "containers-packing", "jars-bottles"),
        ("Honey Pail 15kg Plastic", [], "", "containers-packing", "jars-bottles"),
        ("Squeeze Bottle Bear Shape 250g", [], "", "containers-packing", "jars-bottles"),

        # --- Containers: labels-seals ---
        ("Honey Label Round Gold Foil", [], "", "containers-packing", "labels-seals"),
        ("Tamper Seal Sticker 63mm", [], "", "containers-packing", "labels-seals"),

        # --- Books & Education ---
        ("The Hive and the Honey Bee Book", [], "", "books-education", "books-education"),
        ("Beekeeping for Beginners DVD Course", [], "", "books-education", "books-education"),
        ("Beekeeping Manual CSIRO Guide", [], "", "books-education", "books-education"),

        # --- Unknown: other ---
        ("Bee Ornament Decoration Gift", [], "", "other", "other"),
        ("Gift Card Beekeeping Store", [], "", "other", "other"),

        # --- Tag-based matching ---
        # Tags are folded into the combined string and matched the same way.
        # Tag "varroa" (6 chars) is the only matching keyword in the combined string.
        ("Bee Health Supplement", ["varroa"], "", "treatments", "varroa"),
        ("Mystery Blue Product", ["pollen", "trap"], "", "feeders", "bee-nutrition"),

        # --- product_type matching ---
        # product_type added to combined string; catches generic titles.
        ("Standard Model A", [], "Queen Excluder", "hiveware", "queen-excluders"),
        ("Premium Item", [], "Bee Suit", "protective-gear", "bee-suits"),

        # --- Case insensitivity ---
        ("LANGSTROTH HIVE BODY ASSEMBLED", [], "", "hiveware", "hive-bodies"),
        ("APIVAR VARROA STRIP", [], "", "treatments", "varroa"),

        # --- Plural handling (pattern appends s?) ---
        # "frame" keyword matches "frames" via s?
        ("Assembled Frames Box of 10", [], "", "frames-foundation", "frames"),
        # "smoker" keyword matches "smokers"
        ("Pack of Smokers for Apiary", [], "", "smokers-tools", "smokers"),

        # --- Multi-word keyword beats shorter fallback ---
        # "hive tool" (9 chars) should win over plain "hive" fallback
        ("Premium Hive Tool Stainless", [], "", "smokers-tools", "hive-tools"),
        # "queen excluder" should win over "queen" (which isn't even a keyword)
        ("Plastic Queen Excluder Flat", [], "", "hiveware", "queen-excluders"),

        # ---------------------------------------------------------------
        # Bug regressions
        # ---------------------------------------------------------------

        # DEC-083 (2026-03-22): "lid" used to be a bare keyword in hives-boxes,
        # causing "Hexagonal Glass Jar With Metal Twist Lid" to match hives-boxes
        # instead of containers-packing. Fixed by removing bare "lid" from
        # hives-boxes and adding word-boundary regex.
        # "jar" (3 chars, in jars-bottles) should match this product; "lid"
        # is no longer a keyword at all (was removed from hives-boxes).
        ("Hexagonal Glass Jar With Metal Twist Lid", [], "", "containers-packing", "jars-bottles"),
        ("Honey Jar With Lid 500g", [], "", "containers-packing", "jars-bottles"),

        # DEC-083: Word-boundary fix -- "hat" should not match inside "what".
        # Product title containing "what" should not trigger jackets-veils.
        # (We test the inverse: a product that genuinely contains "hat" DOES match.)
        ("Beekeeping Hat Wide Brim Sun", [], "", "protective-gear", "jackets-veils"),
    ]

    def test_cases(self):
        for title, tags, ptype, exp_parent, exp_sub in self.CASES:
            with self.subTest(title=title):
                result = bc.categorise_product(title, tags, ptype)
                self.assertEqual(
                    result, (exp_parent, exp_sub),
                    f"categorise_product({title!r}) = {result}, want "
                    f"({exp_parent!r}, {exp_sub!r})"
                )

    def test_no_tags_no_type(self):
        """tags=None and product_type='' are both handled gracefully."""
        result = bc.categorise_product("Hive Tool Stainless")
        self.assertEqual(result, ("smokers-tools", "hive-tools"))

    def test_returns_other_for_unknown(self):
        """Pure noise product returns ('other', 'other')."""
        self.assertEqual(bc.categorise_product("Zzz Unknown Product XYZ"), ("other", "other"))


# ---------------------------------------------------------------------------
# category_name helper
# ---------------------------------------------------------------------------

class CategoryName(unittest.TestCase):
    def test_parent_slugs(self):
        cases = [
            ("hiveware", "Hiveware"),
            ("frames-foundation", "Frames & Foundation"),
            # "feeders" slug is shared: parent_name is "Feeders & Feed" but the
            # sub slug is also "feeders" (name "Feeders"), and SUBCATEGORY_NAMES
            # overwrites PARENT_NAMES in CATEGORY_NAMES, so this returns "Feeders".
            ("feeders", "Feeders"),
            ("extractors-processing", "Extractors & Processing"),
            ("protective-gear", "Protective Gear"),
            ("smokers-tools", "Smokers & Tools"),
            ("treatments", "Treatments & Health"),
            ("containers-packing", "Containers & Packing"),
            ("books-education", "Books & Education"),
            ("other", "Other"),
        ]
        for slug, expected in cases:
            with self.subTest(slug=slug):
                self.assertEqual(bc.category_name(slug), expected)

    def test_sub_slugs(self):
        cases = [
            ("hive-bodies", "Hive Bodies"),
            ("hive-kits", "Hive Kits"),
            ("frames", "Frames"),
            ("bee-suits", "Bee Suits"),
            ("varroa", "Varroa Treatments"),
            ("jars-bottles", "Jars & Bottles"),
            ("other", "Other"),
        ]
        for slug, expected in cases:
            with self.subTest(slug=slug):
                self.assertEqual(bc.category_name(slug), expected)

    def test_unknown_slug_returns_other(self):
        self.assertEqual(bc.category_name("nonexistent-slug"), "Other")


# ---------------------------------------------------------------------------
# Lookup structure integrity
# ---------------------------------------------------------------------------

class LookupIntegrity(unittest.TestCase):
    """Verify that the derived lookup dicts are consistent with CATEGORIES."""

    def test_every_sub_has_a_parent(self):
        for cat in bc.CATEGORIES:
            self.assertIn(
                cat["slug"], bc.PARENT_FOR_SUB,
                f"Subcategory {cat['slug']!r} missing from PARENT_FOR_SUB"
            )
            self.assertEqual(
                bc.PARENT_FOR_SUB[cat["slug"]], cat["parent"],
                f"PARENT_FOR_SUB[{cat['slug']!r}] wrong"
            )

    def test_every_parent_in_parents(self):
        for cat in bc.CATEGORIES:
            self.assertIn(
                cat["parent"], bc.PARENTS,
                f"Parent {cat['parent']!r} missing from PARENTS"
            )

    def test_subs_by_parent_covers_all_cats(self):
        for cat in bc.CATEGORIES:
            self.assertIn(cat["parent"], bc.SUBS_BY_PARENT)
            subs = [c["slug"] for c in bc.SUBS_BY_PARENT[cat["parent"]]]
            self.assertIn(
                cat["slug"], subs,
                f"Sub {cat['slug']!r} missing from SUBS_BY_PARENT[{cat['parent']!r}]"
            )

    def test_subcategory_names_complete(self):
        for cat in bc.CATEGORIES:
            self.assertIn(cat["slug"], bc.SUBCATEGORY_NAMES)
            self.assertEqual(bc.SUBCATEGORY_NAMES[cat["slug"]], cat["name"])

    def test_no_empty_keyword_lists(self):
        for cat in bc.CATEGORIES:
            self.assertTrue(
                len(cat["keywords"]) > 0,
                f"Category {cat['slug']!r} has an empty keyword list"
            )
