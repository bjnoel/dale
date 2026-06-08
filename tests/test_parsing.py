"""
Tests for tools/scrapers/cultivar_parsing.py -- the shared helpers that
turn nursery product titles into (species, variety) tuples and variety
slugs. Used by build_variety_pages, build_species_pages, and
send_variety_alerts.

Run from repo root with:
    python3 -m unittest discover tests/

Rule of thumb: every bug we fix in cultivar_parsing.py gets a test case
here (the title that produced the wrong output, mapped to the expected
output). See feedback_regression_tests_on_bugfix memory.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))  # so cultivar_parsing's sibling imports resolve


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cp = _load(SCRAPERS / "cultivar_parsing.py")
# Also load the three callers to make sure they still import cleanly (catches
# accidental leftover references to removed helpers).
_load(SCRAPERS / "build_variety_pages.py")
_load(SCRAPERS / "build_species_pages.py")
_load(SCRAPERS / "send_variety_alerts.py")


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------

class Slugify(unittest.TestCase):
    CASES = [
        ("Avocado - Hass",                "avocado-hass"),
        ("Mango - R2E2",                  "mango-r2e2"),
        ("Sapodilla Grafted - Krasuey",   "sapodilla-grafted-krasuey"),
        ("Fig \u2013 Violette De Bordeaux",   "fig-violette-de-bordeaux"),
        ("Fig \u2014 Violette De Bordeaux",   "fig-violette-de-bordeaux"),
        ("Pomegranate \u00ae Wonderful",      "pomegranate-wonderful"),
        ("Mandarin (Imperial)",           "mandarin-imperial"),
        ("Apple - Anna 90mm",             "apple-anna-90mm"),
        ("MIXED   Case  -  Variety",      "mixed-case-variety"),
        ("Hyphen---Madness",              "hyphen-madness"),
        ("  Trim Me - Edges  ",           "trim-me-edges"),
    ]

    def test_cases(self):
        for inp, expected in self.CASES:
            with self.subTest(input=inp):
                self.assertEqual(cp.slugify(inp), expected)


# ---------------------------------------------------------------------------
# parse_cultivar
# ---------------------------------------------------------------------------

class ParseCultivar(unittest.TestCase):
    CASES = [
        # Dash separator, classic case
        ("Avocado - Hass",                      ("Avocado", "Hass")),
        ("Mango - R2E2",                        ("Mango", "R2E2")),
        ("Fig - Violette De Bordeaux",          ("Fig", "Violette De Bordeaux")),
        ("Fig \u2013 Violette",                     ("Fig", "Violette")),
        ("Fig \u2014 Violette",                     ("Fig", "Violette")),
        ("Sapodilla Grafted - Krasuey",         ("Sapodilla", "Krasuey")),  # 2026-06-08: "Grafted" is propagation, strip from species so it groups with "Sapodilla - Krasuey"
        # Quoted variety (Tamarillo bug, 2026-04-19)
        ("Tamarillo 'Red'",                     ("Tamarillo", "Red")),
        ("Tamarillo 'Red' (Advanced) PICK UP ONLY", ("Tamarillo", "Red")),
        ('Tamarillo "Red"',                     ("Tamarillo", "Red")),
        ("Tamarillo \u2018Yellow\u2019 (Solanum betaceum)", ("Tamarillo", "Yellow")),
        # Pipe separator, only when left side is a known species (2026-04-19)
        ("Tamarillo | Red Tamarillo",           ("Tamarillo", "Red")),   # also strips repeat of species
        ("Apple | Red Fuji",                    ("Apple", "Red Fuji")),
        ("Fruit Tree Cottage | Tamarillo",      None),                   # left side not a species -> skip pipe
        # No-separator titles, matched against species taxonomy (2026-04-19)
        ("Tamarillo Red",                       ("Tamarillo", "Red")),
        ("Black Sapote Maher",                  ("Black Sapote", "Maher")),
        # Trailing size words stripped (2026-04-19)
        ("Tamarillo - Red Advanced",            ("Tamarillo", "Red")),
        ("Mango - Kensington Grafted",          ("Mango", "Kensington")),
        # Listing noise stripped so size/rootstock variants group (2026-06-08)
        ("Black Sapote Mossman 5l",             ("Black Sapote", "Mossman")),
        ("Black Sapote - Mossman (grafted)",    ("Black Sapote", "Mossman")),
        ("Apple – Dorsett Golden – Super Dwarf", ("Apple", "Dorsett Golden")),
        ("Apple – Dorsett Golden Super Dwarf – Bare Root", ("Apple", "Dorsett Golden")),
        ("Dwarf Apple - Dorsett Golden",        ("Apple", "Dorsett Golden")),  # "Dwarf" on species side
        ("Banana - Blue Java: RESTRICTED TO S.E. QLD", ("Banana", "Blue Java")),
        ("Banana - Horn Plantain QLD ONLY",     ("Banana", "Horn Plantain")),
        ("Blueberry - Biloxi 140 mm",           ("Blueberry", "Biloxi")),
        ("Apple - Anna 2l",                     ("Apple", "Anna")),
        ("Plum - Santa Rosa (Bear Rooted)",     ("Plum", "Santa Rosa")),  # "bear" typo for "bare"
        # Banana keeps "Dwarf": Dwarf Cavendish is a real cultivar, not a size
        ("Banana - Dwarf Cavendish",            ("Banana", "Dwarf Cavendish")),
        # Size/container/propagation noise, batch 2 (2026-06-08, real live titles)
        ("Apple Pink Lady 25cm dwarf",          ("Apple", "Pink Lady")),     # cm + dwarf
        ("Feijoa Mammoth 20 cm pot",            ("Feijoa", "Mammoth")),      # "20 cm" + pot; keep "Mammoth"
        ("Loquat Heards Mammoth 25cm",          ("Loquat", "Heards Mammoth")),  # keep "Mammoth" (cultivar)
        ("Avocado - Bacon (Small)",             ("Avocado", "Bacon")),       # (Small)
        ("Banana - Cavendish Tube Stock",       ("Banana", "Cavendish")),    # spaced "Tube Stock"
        ("Banana - Goldfinger SOUTH EAST QLD ONLY", ("Banana", "Goldfinger")),  # SE QLD ONLY (no "restricted to")
        ("Apple - Anna (Low Chill) Pot",        ("Apple", "Anna")),          # low chill + pot
        ("Black Sapote - Seedling 140ml",       ("Black Sapote", "Seedling")),  # 140ml stripped
        # Filters
        ("Sapodilla - Seedling",                None),
        ("Mango - Grafted",                     None),
        ("Apple - 90mm",                        None),
        ("Apple - 90mm pots",                   None),
        ("Mango - Bare Root",                   None),
        ("Red Tamarillo Trees \u2013 90mm pots",    None),
        ("Avocado - A",                         None),
        ("1L Mango - Bowen",                    None),
        ("Sapodilla",                           None),     # known species, no variety
        ("Tamarillo",                           None),
        ("Black Sapote",                        None),
        ("Sapodilla / Chicku",                  None),     # slash should not match pipe/dash
        ("Plain title with no separator",       None),
    ]

    def test_cases(self):
        for inp, expected in self.CASES:
            with self.subTest(input=inp):
                self.assertEqual(cp.parse_cultivar(inp), expected)


# ---------------------------------------------------------------------------
# product_variety_slug -- parse + slugify end to end
# ---------------------------------------------------------------------------

class ProductVarietySlug(unittest.TestCase):
    CASES = [
        ("Avocado - Hass",                        "avocado-hass"),
        ("Mango - R2E2",                          "mango-r2e2"),
        ("Sapodilla Grafted - Krasuey",           "sapodilla-krasuey"),  # 2026-06-08: groups with "Sapodilla - Krasuey"
        ("Fig - Violette De Bordeaux",            "fig-violette-de-bordeaux"),
        ("Sapodilla - Seedling",                  None),
        ("Sapodilla",                             None),
        ("Mandarin (Imperial) - Late",            "mandarin-imperial-late"),
        # Tamarillo bugs end-to-end
        ("Tamarillo 'Red'",                       "tamarillo-red"),
        ("Tamarillo 'Red' (Advanced)",            "tamarillo-red"),
        ("Red Tamarillo Trees \u2013 90mm pots",      None),
        ("Tamarillo | Red Tamarillo",             "tamarillo-red"),
        ("Tamarillo Red",                         "tamarillo-red"),
        ("Tamarillo - Red Advanced",              "tamarillo-red"),
    ]

    def test_cases(self):
        for inp, expected in self.CASES:
            with self.subTest(input=inp):
                self.assertEqual(cp.product_variety_slug(inp), expected)

    def test_messy_variants_collapse_to_one_slug(self):
        # The core bug: size/rootstock/pot/shipping noise must not fragment one
        # cultivar across multiple variety pages (2026-06-08).
        mossman = [
            "Black Sapote Mossman 5l",
            "Black Sapote - Mossman (grafted)",
            "Black Sapote - Mossman",
        ]
        self.assertEqual(
            {cp.product_variety_slug(t) for t in mossman}, {"black-sapote-mossman"}
        )
        dorsett = [
            "Apple – Dorsett Golden – Super Dwarf",
            "Apple – Dorsett Golden Super Dwarf – Bare Root",
            "Apple – Dorsett Golden",
            "Dwarf Apple - Dorsett Golden",
        ]
        self.assertEqual(
            {cp.product_variety_slug(t) for t in dorsett}, {"apple-dorsett-golden"}
        )
        # Banana keeps "Dwarf" -- Dwarf Cavendish stays distinct from Cavendish.
        self.assertNotEqual(
            cp.product_variety_slug("Banana - Dwarf Cavendish"),
            cp.product_variety_slug("Banana - Cavendish"),
        )
        # cm / litre / plain all collapse to one (the live data had ~150 cm fragments).
        feijoa = ["Feijoa - Mammoth", "Feijoa Mammoth 20 cm pot", "Feijoa - Mammoth 5l"]
        self.assertEqual(
            {cp.product_variety_slug(t) for t in feijoa}, {"feijoa-mammoth"}
        )


# ---------------------------------------------------------------------------
# Relaxed pass -- titles the strict parser rejects but which still express a
# cultivar once listing noise is stripped, plus multigraft and leading-quote
# shapes. Added 2026-05-30 to widen variety-page coverage for OOS search rows.
# These run through the same public parse_cultivar entry point.
# ---------------------------------------------------------------------------

class RelaxedParse(unittest.TestCase):
    # Titles that should now parse via the relaxed pass.
    PARSE = [
        # Parenthetical / size / "tree" / bare-rooted noise stripped, then
        # the strict species-first or variety-first shape is recovered.
        ("Apricot Castlebrite (Bare rooted)",        ("Apricot", "Castlebrite")),
        ("Albatross Peach tree (Bare-Rooted)",       ("Peach", "Albatross")),
        ("Angelina Burdett Plum (Bare-Rooted)",      ("Plum", "Angelina Burdett")),
        ("Alison Red Mango Tree",                    ("Mango", "Alison Red")),
        ("Bendigo Beauty Peach",                     ("Peach", "Bendigo Beauty")),
        # Variety-first with a cultivar synonym in the species lookup: must take
        # the canonical species and keep the leading word as the variety.
        ("Bacon Avocado",                            ("Avocado", "Bacon")),
        ("Hass Avocado",                             ("Avocado", "Hass")),
        # Leading-quote variety, fruit species following.
        ('"Alstonville" Finger Lime 90mm Pots (Cutting Grown)',
                                                     ("Finger Lime", "Alstonville")),
        # Multigraft: one combo variety, components sorted so order collapses.
        ("2-Way Apple 'Fuji + Pink Lady'",           ("Apple", "2way fuji pink lady")),
        ("2-Way Apple 'Pink Lady + Fuji'",           ("Apple", "2way fuji pink lady")),
    ]

    # Titles that must REMAIN None: aromatic/foliage confusables, lookalikes,
    # and structural-boundary cases the strict parser also rejects.
    NONE = [
        "Lemon Myrtle (Backhousia citriodora)",   # Backhousia, not Lemon
        "Lemon Grass (Cymbopogon citratus)",
        "Native Mulberry (Pipturus argenteus)",
        "Fiddle Leaf Fig 200mm Pot",              # Ficus lyrata, foliage
        "Bay Leaf Tree",
        "Aloe Vera",
        "Brazilian Cherry",                       # Grumichama lookalike qualifier
        "Cedar Bay Cherry",
        "Sapodilla / Chicku",                     # synonym, not a variety
        "Fruit Tree Cottage | Tamarillo",         # left side not a species
        "Sapodilla - Seedling",                   # size/seedling only
        "Mango - Grafted",
        "Apple - 90mm",
        "Avocado - A",                            # single-letter pollination type
    ]

    def test_parse(self):
        for inp, expected in self.PARSE:
            with self.subTest(input=inp):
                self.assertEqual(cp.parse_cultivar(inp), expected)

    def test_none(self):
        for inp in self.NONE:
            with self.subTest(input=inp):
                self.assertIsNone(cp.parse_cultivar(inp))

    def test_multigraft_order_collapses_to_one_slug(self):
        a = cp.product_variety_slug("2-Way Apple 'Fuji + Pink Lady'")
        b = cp.product_variety_slug("2-Way Apple 'Pink Lady + Fuji'")
        self.assertEqual(a, b)
        self.assertEqual(a, "apple-2way-fuji-pink-lady")

    def test_relaxed_never_overrides_strict(self):
        # A title the strict parser handles must return the strict result
        # unchanged (relaxed only runs on strict None).
        self.assertEqual(cp.parse_cultivar("Avocado - Hass"), ("Avocado", "Hass"))
