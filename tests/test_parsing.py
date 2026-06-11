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
# accidental leftover references to removed helpers). bvp is kept bound so the
# per-row type-pill suppression helper (DEC-177) can be unit-tested directly;
# bsp so GroupByCultivar can assert both builders share one grouping.
bvp = _load(SCRAPERS / "build_variety_pages.py")
bsp = _load(SCRAPERS / "build_species_pages.py")
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
        ("Orange Washington Navel_17cm",        ("Orange", "Washington Navel")),  # underscore-joined size
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
# group_by_cultivar -- THE shared grouping for variety surfaces. The variety
# builder writes /variety/<slug>.html for every group; the species builder
# renders its chip cloud from the same groups, so a chip can never link to a
# page that was not generated. Both must use the cultivar_parsing copy.
# ---------------------------------------------------------------------------

class GroupByCultivar(unittest.TestCase):
    def test_builders_share_one_implementation(self):
        self.assertIs(bvp.group_by_cultivar, bsp.group_by_cultivar)
        self.assertEqual(bvp.group_by_cultivar.__module__, "cultivar_parsing")

    def test_grouping(self):
        products = [
            {"title": "Black Sapote Mossman 5l"},
            {"title": "Black Sapote - Mossman (grafted)"},
            {"title": "Avocado - Hass"},
            {"title": "Sapodilla"},        # species-only listing: no cultivar
            {"title": "Rose - Iceberg"},   # parses fine, but outside the fruit taxonomy
        ]
        groups = cp.group_by_cultivar(products)
        self.assertEqual(set(groups), {"black-sapote-mossman", "avocado-hass"})
        self.assertEqual(len(groups["black-sapote-mossman"]["products"]), 2)
        self.assertEqual(groups["black-sapote-mossman"]["variety"], "Mossman")
        self.assertEqual(groups["avocado-hass"]["species"], "Avocado")


# ---------------------------------------------------------------------------
# Taxonomy scope gate (DEC-195) -- /variety/ pages and variety alerts only
# cover the fruit/nut/berry taxonomy. Ornamentals and veg parse fine
# ("Rose - Iceberg") but must not get pages or alerts.
# ---------------------------------------------------------------------------

class SpeciesInScope(unittest.TestCase):
    IN = [
        "Apple",                       # canonical
        "apple",                       # case-insensitive
        "Grapes",                      # synonym
        "Cumquat",                     # synonym of a DEC-195 addition
        "Persimmon",                   # DEC-195 addition
        "Davidson’s Plum",        # curly-apostrophe synonym
        "Apple Multi Graft",           # known species leads the text
        "Avocado Pollinating Duo",
        "Cherry Trixzie Multi Graft",
        "Jackfruit Marcott",
        "Papaya Bisexual",
        "Mandarin (Imperial)",         # parenthesized qualifier
        "Mandarin Imperial",           # cultivar word in the species slot
        "Persimmon Fuyu",
        "Guava Hawaiian",
        "Plum x Apricot",              # cross led by a known species
        "Peach x Nectarine",
    ]
    OUT = [
        "African Daisy",
        "Rose",
        "Kangaroo Paw",
        "Lavender",
        "Chilli",                      # edible but out of fruit/nut/berry scope
        "Tomato",
        "Flowering Cherry",            # ornamental prunus: species doesn't lead
        "Lemon Myrtle",                # borrows a fruit name, different plant
        "Apple Cactus",
        "Peanut Tree",
        "Heliconia bihai x caribaea",  # cross of unknown species
        "Exclusion Net",
        "",
    ]

    def test_in_scope(self):
        for s in self.IN:
            with self.subTest(species=s):
                self.assertTrue(cp.species_in_scope(s))

    def test_out_of_scope(self):
        for s in self.OUT:
            with self.subTest(species=s):
                self.assertFalse(cp.species_in_scope(s))

    def test_product_variety_slug_gates_non_fruit(self):
        # Parses cleanly, but no slug => no page, no alert
        self.assertIsNone(cp.product_variety_slug("Rose - Iceberg"))
        self.assertIsNone(cp.product_variety_slug("Kangaroo Paw - Bush Pearl"))
        # Fruit still works end-to-end
        self.assertEqual(cp.product_variety_slug("Persimmon - Fuyu"), "persimmon-fuyu")

    def test_title_catches_fruit_as_color_ornamentals(self):
        # The relaxed parser reads the COLOR word as the species here; only the
        # raw title reveals the real (ornamental) genus.
        leaks = [
            "Hibiscus Petite Orange",
            "Bougainvillea Bengal Orange (Bougainvillea glabra)",
            "Heuchera Sugar Plum (Heuchera)",
            "Frangipani Apricot (Plumeria rubra)",
            "Rose Showpiece Orange (Rosa)",        # genus only in the parens
            "Lemon Myrtle",
            "Strawberry Begonia Hanging plants",
        ]
        for t in leaks:
            with self.subTest(title=t):
                self.assertIsNone(cp.product_variety_slug(t))

    def test_title_check_spares_real_fruit(self):
        # 'rosa' is paren-only: Santa Rosa is a plum, not a rose.
        self.assertEqual(cp.product_variety_slug("Plum - Santa Rosa"), "plum-santa-rosa")
        self.assertEqual(
            cp.product_variety_slug("Nectarine - Arctic Rose"), "nectarine-arctic-rose"
        )
        self.assertEqual(
            cp.product_variety_slug("Blueberry Magnolia 15cm"), "blueberry-magnolia"
        )

    def test_grandfathered_watched_slugs_stay_alive(self):
        # Active watches from before the gate (DEC-195). The species is out of
        # scope but the exact watched slug keeps its page and alerts.
        self.assertFalse(cp.species_in_scope("Mandevilla"))
        self.assertTrue(cp.cultivar_in_scope("Mandevilla", "mandevilla-peach-sunrise"))
        self.assertEqual(
            cp.product_variety_slug("Mandevilla - Peach Sunrise"),
            "mandevilla-peach-sunrise",
        )
        self.assertIsNone(cp.product_variety_slug("Mandevilla - White Fantasy"))


# ---------------------------------------------------------------------------
# Canonicalisation (DEC-196) -- respellings and synonym spellings of one
# species must converge on one canonical name and ONE slug, so the variety
# index doesn't show "Jakfruit" and "Jackfruit" as separate species.
# ---------------------------------------------------------------------------

class CanonicalCultivar(unittest.TestCase):
    def test_respellings_merge(self):
        self.assertEqual(cp.product_variety_slug("Jakfruit - Black Gold"), "jackfruit-black-gold")
        self.assertEqual(cp.product_variety_slug("Jackfruit - Black Gold"), "jackfruit-black-gold")
        self.assertEqual(cp.product_variety_slug("Jackfruit Marcott - Black Gold"), "jackfruit-black-gold")
        self.assertEqual(cp.product_variety_slug("Cumquat - Meiwa"), "kumquat-meiwa")
        self.assertEqual(cp.product_variety_slug("Grapes - Menindee Seedless"), "grape-menindee-seedless")
        self.assertEqual(cp.product_variety_slug("Dragonfruit - Pink Panther"), "dragon-fruit-pink-panther")

    def test_davidsons_plum_spellings_merge(self):
        titles = [
            "Davidson Plum - Smooth",
            "Davidson’s Plum ‘Smooth’",
            "Davidsonia jerseyana - Smooth",
        ]
        self.assertEqual(
            {cp.product_variety_slug(t) for t in titles}, {"davidson-s-plum-smooth"}
        )

    def test_species_only_listing_gets_no_page(self):
        # "Annona squamosa - Sugar apple" is a sugar apple tree, not a cultivar
        self.assertIsNone(cp.product_variety_slug("Annona squamosa - Sugar apple"))
        # ...but a real sugar apple cultivar gets its own species' slug
        self.assertEqual(
            cp.product_variety_slug("Sugar apple - Kampong Mauve"),
            "sugar-apple-kampong-mauve",
        )

    def test_canonicalize_species(self):
        self.assertEqual(cp.canonicalize_species("Meyer Lemon"), ("Lemon", "Meyer"))
        self.assertEqual(cp.canonicalize_species("Carambola Starfruit"), ("Starfruit", ""))
        self.assertEqual(
            cp.canonicalize_species("Jaboticaba White Plinia phitrantha"),
            ("Jaboticaba", "White"),
        )
        self.assertEqual(cp.canonicalize_species("Mandarin Imperial"), ("Mandarin", "Imperial"))
        self.assertIsNone(cp.canonicalize_species("Kangaroo Paw"))


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


# ---------------------------------------------------------------------------
# extract_type_label -- the per-row "type" pill on variety pages (DEC-177).
# DEC-176 strips form/rootstock/propagation noise from the cultivar NAME so the
# rows group onto one page; this brings that info back as a per-row label so
# shoppers can tell otherwise-identical nursery rows apart. Standard / grafted /
# pot sizes are the default -> no label. Uses the SAME regexes the cleaner
# strips with, so strip and label can never drift.
# ---------------------------------------------------------------------------

class ExtractTypeLabel(unittest.TestCase):
    CASES = [
        ("Apple - Gala Dwarf",                  "Dwarf"),
        ("Apple Gala (Bare Rooted)",            "Bare rooted"),
        ("Apple - Gala",                        ""),
        ("Sapodilla Grafted - Krasuey",         ""),     # grafted is the default form
        ("Apple - Gala Standard",               ""),     # standard is the default form
        ("Apple - Dorsett Golden Super Dwarf - Bare Root", "Super Dwarf, Bare rooted"),
        ("Banana - Cavendish Tube Stock",       "Tubestock"),
        ('"Alstonville" Finger Lime 90mm Pots (Cutting Grown)', "Cutting grown"),
        ("Mango - Kensington Pride Advanced",   "Advanced"),
        # Canonicalisation of spelling / spacing / typo variants
        ("Apple - Gala Semi-Dwarf",             "Semi Dwarf"),
        ("Apple - Gala (Bear Rooted)",          "Bare rooted"),   # "bear" typo -> "Bare rooted"
        ("Banana - Cavendish Tubestock",        "Tubestock"),     # joined "tubestock"
        ("Plum - Santa Rosa (Bare-Rooted)",     "Bare rooted"),
        # "Super Dwarf" wins over "Dwarf" (longest match first, no duplicate pill)
        ("Apple - Dorsett Super Dwarf",         "Super Dwarf"),
        # Combine deduped + ordered: form, then propagation, then Advanced
        ("Plum - Santa Rosa Dwarf Bare Root Advanced", "Dwarf, Bare rooted, Advanced"),
        # Pot sizes are NOT type labels
        ("Apple - Gala 5L 200mm",               ""),
    ]

    def test_cases(self):
        for inp, expected in self.CASES:
            with self.subTest(input=inp):
                self.assertEqual(cp.extract_type_label(inp), expected)


class SuppressTypeLabel(unittest.TestCase):
    """build_variety_pages.visible_type_label drops a pill whose text already
    appears in the variety name, so the banana 'Dwarf Cavendish' page shows no
    redundant Dwarf pill (DEC-177)."""

    def test_suppress(self):
        self.assertEqual(bvp.visible_type_label("Dwarf", "Dwarf Cavendish"), "")
        self.assertEqual(bvp.visible_type_label("Dwarf", "Gala"), "Dwarf")
        self.assertEqual(bvp.visible_type_label("", "Gala"), "")
        # Per-part: keep the part not in the name, drop the one that is.
        self.assertEqual(
            bvp.visible_type_label("Super Dwarf, Bare rooted", "Dorsett Golden"),
            "Super Dwarf, Bare rooted",
        )
        self.assertEqual(
            bvp.visible_type_label("Dwarf, Bare rooted", "Dwarf Cavendish"),
            "Bare rooted",
        )
