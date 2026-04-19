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
        ("Sapodilla Grafted - Krasuey",         ("Sapodilla Grafted", "Krasuey")),
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
        ("Sapodilla Grafted - Krasuey",           "sapodilla-grafted-krasuey"),
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
