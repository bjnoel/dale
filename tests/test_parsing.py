"""
Tests for the parsing helpers used by treestock.com.au page builders and
alert scripts. These functions are pure (str -> str / str -> tuple) and
appear in multiple places, so this test module also pins the cross-file
implementations to the same behaviour.

Run from repo root with:
    python3 -m unittest discover tests/

Touch any of:
- tools/scrapers/build_variety_pages.py     (parse_cultivar, slugify)
- tools/scrapers/build_species_pages.py     (_variety_slug)
- tools/scrapers/send_variety_alerts.py     (parse_cultivar, slugify, product_variety_slug)
- tools/scrapers/send_species_alerts.py     (match_title)
...and re-run these tests before committing.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"

# The script files import sibling modules (shipping, treestock_layout) by
# bare name, so the scrapers dir has to be on sys.path before they load.
sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    """Import a script file as a module without executing its main()."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bvp = _load(SCRAPERS / "build_variety_pages.py")
bsp = _load(SCRAPERS / "build_species_pages.py")
sva = _load(SCRAPERS / "send_variety_alerts.py")
ssa = _load(SCRAPERS / "send_species_alerts.py")


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------

SLUGIFY_CASES = [
    # (input, expected)
    ("Avocado - Hass",                "avocado-hass"),
    ("Mango - R2E2",                  "mango-r2e2"),
    ("Sapodilla Grafted - Krasuey",   "sapodilla-grafted-krasuey"),
    ("Fig \u2013 Violette De Bordeaux",   "fig-violette-de-bordeaux"),       # en dash
    ("Fig \u2014 Violette De Bordeaux",   "fig-violette-de-bordeaux"),       # em dash
    ("Pomegranate \u00ae Wonderful",      "pomegranate-wonderful"),          # registered mark
    ("Mandarin (Imperial)",           "mandarin-imperial"),                  # parens stripped
    ("Apple - Anna 90mm",             "apple-anna-90mm"),
    ("MIXED   Case  -  Variety",      "mixed-case-variety"),                 # collapse whitespace
    ("Hyphen---Madness",              "hyphen-madness"),                     # collapse repeats
    ("  Trim Me - Edges  ",           "trim-me-edges"),                      # outer trim
]


class SlugifyConsistency(unittest.TestCase):
    """slugify is duplicated in build_variety_pages.py and send_variety_alerts.py.
    They MUST produce identical output or variety alert URLs won't match the
    pages built for them."""

    def test_cases(self):
        for inp, expected in SLUGIFY_CASES:
            with self.subTest(input=inp):
                self.assertEqual(bvp.slugify(inp), expected, "build_variety_pages.slugify")
                self.assertEqual(sva.slugify(inp), expected, "send_variety_alerts.slugify")


# ---------------------------------------------------------------------------
# parse_cultivar
# ---------------------------------------------------------------------------

PARSE_CULTIVAR_CASES = [
    # (input, expected_tuple_or_None)
    ("Avocado - Hass",                ("Avocado", "Hass")),
    ("Mango - R2E2",                  ("Mango", "R2E2")),
    ("Fig - Violette De Bordeaux",    ("Fig", "Violette De Bordeaux")),
    ("Fig \u2013 Violette",               ("Fig", "Violette")),
    ("Fig \u2014 Violette",               ("Fig", "Violette")),
    ("Sapodilla Grafted - Krasuey",   ("Sapodilla Grafted", "Krasuey")),  # known limitation: doesn't canonicalise
    # Filtered out
    ("Sapodilla - Seedling",          None),                              # size word
    ("Mango - Grafted",               None),
    ("Apple - 90mm",                  None),
    ("Avocado - A",                   None),                              # single-letter variety (pollination type)
    ("1L Mango - Bowen",              None),                              # leading digit
    ("Sapodilla",                     None),                              # no separator
    ("Sapodilla / Chicku",            None),                              # slash, not dash
    ("Plain title with no separator", None),
]


class ParseCultivarConsistency(unittest.TestCase):
    """parse_cultivar is duplicated in build_variety_pages.py and
    send_variety_alerts.py. Behaviour must stay identical or the alert
    script will email about variety slugs the page builder didn't generate."""

    def test_cases(self):
        for inp, expected in PARSE_CULTIVAR_CASES:
            with self.subTest(input=inp):
                self.assertEqual(bvp.parse_cultivar(inp), expected, "build_variety_pages.parse_cultivar")
                self.assertEqual(sva.parse_cultivar(inp), expected, "send_variety_alerts.parse_cultivar")


# ---------------------------------------------------------------------------
# variety slug end-to-end (parse_cultivar + slugify, as actually used)
# ---------------------------------------------------------------------------

VARIETY_SLUG_CASES = [
    ("Avocado - Hass",               "avocado-hass"),
    ("Mango - R2E2",                 "mango-r2e2"),
    ("Sapodilla Grafted - Krasuey",  "sapodilla-grafted-krasuey"),
    ("Fig - Violette De Bordeaux",   "fig-violette-de-bordeaux"),
    ("Sapodilla - Seedling",         None),                                 # filtered
    ("Sapodilla",                    None),                                 # no separator
    ("Mandarin (Imperial) - Late",   "mandarin-imperial-late"),
]


class VarietySlugConsistency(unittest.TestCase):
    """The species page builder has its own inlined _variety_slug helper to
    decide whether to render a "Alerts" link next to a product. Its output
    MUST equal product_variety_slug() in the alert script and the slug the
    variety page is actually built at -- otherwise the link 404s."""

    def test_send_variety_alerts_matches_inline(self):
        for title, expected in VARIETY_SLUG_CASES:
            with self.subTest(title=title):
                self.assertEqual(sva.product_variety_slug(title), expected,
                                 "send_variety_alerts.product_variety_slug")
                self.assertEqual(bsp._variety_slug(title), expected,
                                 "build_species_pages._variety_slug")


# ---------------------------------------------------------------------------
# match_title (species lookup) -- the lookup is built in code, but the
# matching algorithm has its own quirks (greedy left-prefix up to 5 words)
# ---------------------------------------------------------------------------

class MatchTitle(unittest.TestCase):
    def setUp(self):
        # Minimal fake species lookup mirroring fruit_species.json shape
        self.lookup = {
            "mango":          {"slug": "mango",          "common_name": "Mango"},
            "kensington":     {"slug": "mango",          "common_name": "Mango"},   # synonym
            "black sapote":   {"slug": "black-sapote",   "common_name": "Black Sapote"},
            "fig":            {"slug": "fig",            "common_name": "Fig"},
            "ice cream bean": {"slug": "ice-cream-bean", "common_name": "Ice Cream Bean"},
        }

    def test_basic(self):
        self.assertEqual(ssa.match_title("Mango - Bowen", self.lookup)["slug"], "mango")

    def test_multi_word(self):
        self.assertEqual(ssa.match_title("Black Sapote - Maher", self.lookup)["slug"], "black-sapote")

    def test_three_word_species(self):
        self.assertEqual(ssa.match_title("Ice Cream Bean - Long Pod", self.lookup)["slug"], "ice-cream-bean")

    def test_synonym(self):
        self.assertEqual(ssa.match_title("Kensington Pride seedling", self.lookup)["slug"], "mango")

    def test_no_match(self):
        self.assertIsNone(ssa.match_title("Sapodilla - Krasuey", self.lookup))

    def test_dash_separators(self):
        # Words can be separated by dashes too, not just spaces
        self.assertEqual(ssa.match_title("ice-cream-bean-pod", self.lookup)["slug"], "ice-cream-bean")


# ---------------------------------------------------------------------------
# Unsubscribe token (HMAC determinism + case-insensitive email + secret-bound)
# ---------------------------------------------------------------------------

class UnsubscribeToken(unittest.TestCase):
    def test_deterministic_and_case_insensitive(self):
        a = sva.make_unsubscribe_token("User@Example.COM", "secret")
        b = sva.make_unsubscribe_token("user@example.com", "secret")
        self.assertEqual(a, b)

    def test_secret_bound(self):
        a = sva.make_unsubscribe_token("user@example.com", "secret-1")
        b = sva.make_unsubscribe_token("user@example.com", "secret-2")
        self.assertNotEqual(a, b)

    def test_length(self):
        # Truncated to 32 hex chars in the implementation -- nail down to catch silent change
        self.assertEqual(len(sva.make_unsubscribe_token("user@example.com", "secret")), 32)


if __name__ == "__main__":
    unittest.main()
