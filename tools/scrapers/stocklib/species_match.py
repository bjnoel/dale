"""
Shared product-title -> species matcher (the dashboard's matcher, extracted).

Moved verbatim from build-dashboard.py so nursery pages (and any future
surface that groups products by species) count EXACTLY like the dashboard.
build_nursery_pages.py previously had its own cruder fork: substring-anywhere
plus genus-anywhere matching, and it read a nonexistent "aliases" key instead
of "synonyms". That fork counted "Peach ... (Prunus persica)" as Plum (genus
hit) and inflated species counts, so the "In Stock" drill-down links pointed
at dashboard views showing different numbers than the table said.

The 2026-07-23 de-fork audit then found five MORE `match_title` variants
(compare/species/state/trends pages and species alerts), some without prefix
stripping or the variety-first fallback, so "Dwarf Apple Pink Lady" counted on
one page and not another. They all now import from here:

  - match_title(title, lookup): THE matching algorithm, agnostic to what the
    lookup values are (full species records or compressed entries). Use this
    when you just need "which species is this?".
  - match_species(title, lookup): same algorithm on the compressed-entry
    lookup from load_species_lookup(), plus best-effort cultivar extraction
    into result["cv"]. This is what build-dashboard.py / build_nursery_pages
    use.
  - build_species_lookup(species_list): lowercase common_name/synonym -> the
    FULL species record. For builders that need slug/region/etc. off the
    record directly.
  - load_species_lookup(): the dashboard's compressed-entry lookup
    ({"cn","ln","sl","r","g"}), for match_species.

Matching strategy: strip size/form prefixes, longest leading-word-sequence
match first (so "finger lime" wins over "lime"), then a bounded any-position
fallback for "Variety Species" titles (e.g. "Akane Apple (medium)").

Distinct from cultivar_parsing.parse_cultivar (the variety-slug parser pinned
by tests/test_parsing.py): that one answers "which /variety/ page is this?",
this one answers "which species bucket does this product count under?". They
have different tolerances; do not merge them casually.
"""
import re

from stocklib.taxonomy import enabled_species

# Size/form prefixes that precede the actual species name.
_PREFIXES = ["dwarf ", "semi-dwarf ", "semi dwarf ", "miniature ", "standard ",
             "grafted ", "advanced ", "bare root ", "bare-root "]


# Zero-width and BOM-class characters. A nursery's CMS occasionally leaves one
# at the front of a title, where it is invisible to everyone except the word
# splitter: primal-fruits' "\u200bAchachairu (Garcinia humilis)" starts with a
# zero-width space, so _leading_candidate saw "\u200bachachairu" as the first
# word and the product matched nothing at all. One live title on 2026-08-20,
# but stripping them is a normalisation rather than a guess: the character is
# invisible and means nothing in a product title.
_INVISIBLE_RE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff\xa0]")

# Trademark marks glued to the last word. "Angel Peach\u2122" split into "peach\u2122",
# which is no lookup key, so 11 PlantNet titles (and a few from Daleys and
# Heritage) matched no species on 2026-10-18 while cultivar_parsing, which
# already strips these, gave the same titles /variety/ pages. Removed rather
# than spaced: "Trixzie\u00ae Pixzee" stays two words either way.
_TRADEMARK_RE = re.compile(r"[\u2122\u00ae\u00a9]")


def _strip_invisible(title: str) -> str:
    return _TRADEMARK_RE.sub("", _INVISIBLE_RE.sub(" ", title)).strip()


def _cleaned(title: str) -> tuple[str, str]:
    """(lowercase, original-case) title with the first matching prefix stripped."""
    title_lower = title.lower()
    for prefix in _PREFIXES:
        if title_lower.startswith(prefix):
            return title_lower[len(prefix):], title[len(prefix):]
    return title_lower, title


# Punctuation that ends the leading name. "Burdekin plum, Aussie native" and
# "Kaffir Lime: QLD ONLY" used to fail the leading match because the comma or
# colon rode along on the last word ("plum," is not a key), so the title fell
# through to the any-position fallback, which found "plum" and filed a
# Pleiogynium as Prunus domestica. "Peach/Nectarine Multi Graft" is the same
# shape with a slash. The name stops at the first of these.
_LEADING_STOP_RE = re.compile(r"[,:;/]")


def _leading_words(t_lower: str) -> list[str]:
    """Words of the leading name: split on spaces/dashes, cut at punctuation."""
    words = []
    for w in re.split(r'[\s\-–—]+', t_lower):
        m = _LEADING_STOP_RE.search(w)
        if m:
            if m.start():
                words.append(w[:m.start()])
            break
        words.append(w)
    return words


def _leading_candidate(t_lower: str, lookup: dict) -> str | None:
    """Longest leading word sequence that is a lookup key."""
    words = _leading_words(t_lower)
    for n in range(len(words), 0, -1):
        candidate = " ".join(words[:n])
        if candidate in lookup:
            return candidate
    return None


def _fallback_candidate(t_lower: str, lookup: dict) -> str | None:
    """Any-position match for "Variety Species (size)" titles (e.g. Heritage
    Fruit Trees' "Akane Apple (medium)"). Position 0 was already tried."""
    words = re.split(r'[\s\-–—(]+', t_lower)
    words = [w.rstrip(").,") for w in words if w]
    for start in range(1, len(words)):
        for n in range(min(len(words) - start, 3), 0, -1):
            candidate = " ".join(words[start:start + n])
            if candidate in lookup:
                return candidate
    return None


# --- Ornamental relatives (1.6a) ----------------------------------------
#
# match_title happily matches a species name mid-title, so the ornamental
# cousins of our fruit species were being filed as the fruit itself. Live on
# 2026-08-20 that was ~60 products: 26 "Flowering Cherry/Peach/Plum/Apricot/
# Almond/Quince/Nectarine", 15 "Ornamental Pear/Grape/Plum", 3 crabapples,
# and 5 more where the qualifier trails the species name.
#
# This is not a new policy call. /variety/ already keeps them apart:
# cultivar_parsing.parse_cultivar reads "Ornamental Pear - Bradford" as the
# species "Ornamental Pear", which the DEC-195 taxonomy gate then rejects
# because no such record exists. species_match was the only consumer
# collapsing them into Pear, so the two disagreed. This aligns them.
#
# Deliberately NOT reusing cultivar_parsing._ORNAMENTAL_WORDS: that vocabulary
# names ornamental GENERA (hibiscus, grevillea) to stop the relaxed parser
# reading a fruit-as-colour word as the species. This is a different failure,
# ornamental FORMS of the fruit genus itself, and the two lists should not be
# merged casually for the same reason the two parsers are not.

# Unambiguous in any position. Verified against all 14,751 live titles: every
# title carrying one of these is a true ornamental, including the five where
# the word trails the species ("Grape - Ornamental", "Pomegranate - Ornamental",
# "Pineapple - Mini Ornamental", "Olive | Bambalina Dwarf Ornamental",
# "Weeping Mulberry - Ornamental - Chaparral").
_ORNAMENTAL_ANYWHERE = ("ornamental", "crab apple", "crabapple")

# Only ornamental when it QUALIFIES the species, i.e. appears before it.
# "Flowering Cherry - Mt Fuji" is an ornamental Prunus; "Strawberry - Red
# Flowering" is a strawberry that happens to have red flowers, and it is the
# single live counter-example that makes the position test necessary.
_ORNAMENTAL_QUALIFIER = ("flowering",)

# "weeping" is deliberately absent. It is genuinely mixed on live data:
# "Weeping Cherry Cheals", "Weeping Pear pendula" and "Weeping Fig (Ficus
# benjamina)" are ornamentals, but "Star apple Weeping Grafted",
# "Mulberry - Weeping" and "Weeping Mulberry 'White'" are fruiting trees.
# There is no positional or vocabulary rule that separates them, so excluding
# it would cost real fruit. Left alone until someone has better evidence.


def _is_ornamental_relative(t_lower: str, candidate: str) -> bool:
    """True if the title names an ornamental relative rather than the fruit."""
    for word in _ORNAMENTAL_ANYWHERE:
        if re.search(r"(?<!\w)" + re.escape(word) + r"s?(?!\w)", t_lower):
            return True
    species_idx = t_lower.find(candidate)
    if species_idx < 0:
        return False
    for word in _ORNAMENTAL_QUALIFIER:
        m = re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", t_lower)
        if m and m.start() < species_idx:
            return True
    return False


# --- Other plants named after a fruit (1.7) -----------------------------
#
# The any-position fallback reads "Variety Species" titles ("Black Genoa Fig"),
# and it cannot tell a variety name from a common-name qualifier. So on
# 2026-10-15 "Illawarra Plum Pine" showed as Prunus domestica, "Mock Orange"
# as Citrus sinensis, "Fiddle Leaf Fig" as Ficus carica and "Lemon Drop
# Mangosteen" as a lemon. Each of these names is a different plant that
# happens to contain a fruit word.
#
# _NOT_THE_FRUIT is masked out of the title BEFORE matching, so the fruit word
# inside it is invisible and the search carries on past it: "Cox's Orange
# Pippin Apple" still finds Apple, "Tropical - Hog Plum aka Ambarella" still
# finds Ambarella, "Mock Orange" finds nothing. A closed list of names read off
# live titles, not a rule, because no rule separates "Illawarra Plum" (another
# plant) from "Narrabeen Plum" (a plum).
#
# A phrase that is a registry name would mask its own match, so it belongs
# here only while no record claims it. tests/test_species_match.py enforces
# that. Edible fruits on this list (Natal Plum, Malay Apple, Cape Gooseberry,
# ...) are candidates for their own records; until then they are listed
# without a species, which beats being counted as the wrong one.
_NOT_THE_FRUIT = (
    # plum
    "hog plum", "jambolan plum", "java plum",
    "kaffir plum", "wild plum",
    "purple leaf plum",
    # apple
    "apple cactus", "smooth-barked apple",
    "apple gum", "apple blossom",
    # fig
    "fiddle leaf fig", "fiddle-leaf fig", "sacred fig", "weeping fig",
    "climbing fig", "creeping fig", "strangler fig", "moreton bay fig",
    "port jackson fig", "rubber fig",
    # grape
    "oregon grape", "burmese grape", "grape ivy", "tree grape",
    # orange
    "mock orange", "mexican orange", "wild orange", "orange jasmin",
    "orange jasmine", "orange jessamine", "osage orange", "orange trumpet",
    # lemon / lime
    "lemon scented", "lemon-scented", "lemon grass", "lemongrass",
    "lemon balm", "lemon verbena", "lemon thyme", "lemon savory",
    "lemon bergamot", "lemon ball", "lemon button",
    "native lemon", "small leaf lime", "large leaf lime", "spanish lime",
    # cherry
    "beach cherry", "brush cherry", "bush cherry",
    "capulin cherry", "nanking cherry", "native cherry", "cornelian cherry",
    # gooseberry
    "ceylon gooseberry",
    # chestnut
    "malabar chestnut", "guiana chestnut", "cape chestnut", "water chestnut",
    "horse chestnut", "moreton bay chestnut",
    # tamarind
    "native tamarind", "small leaf tamarind", "large leaf tamarind",
    "small-leaf tamarind", "small-leaved tamarind", "large-leaved tamarind",
    "small leaved tamarind", "large leaved tamarind", "fern leaved tamarind",
    "fern-leaved tamarind", "spanish tamarind", "manila tamarind",
    # olive, mulberry, currant, guava, pawpaw, almond, peach
    "native olive", "sweet olive", "red olive", "indian olive", "russian olive",
    "native currant", "wild currant", "native guava",
    "indian almond", "beach almond", "tropical almond",
    "african peach", "peach palm",
    # mangosteen (Garcinia relatives sold under the name)
    "african mangosteen", "native mangosteen",
    "mundu mangosteen", "button mangosteen", "seashore mangosteen",
    # everything else
    "pineapple lily", "pineapple sage", "blueberry ash", "blueberry lily",
    "strawberry tree", "hairy walnut", "eumundi quandong",
    "hard quandong", "box elder", "weeping pear", "string of bananas",
)

_NOT_THE_FRUIT_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(p) for p in sorted(_NOT_THE_FRUIT, key=len, reverse=True))
    + r")(?:e?s)?(?!\w)"
    # "Lemon-scented Myrtle" is a Lemon Myrtle synonym, while "Lemon-scented
    # Gum" and "Tea Tree - Lemon Scented" are not lemons. Nothing on the list
    # names a plant when "myrtle" follows it.
    r"(?![ -]myrtle)")

# Non-fruit plants that borrow a fruit name as a COLOUR or FLAVOUR, usually
# leading the title: "Grevillea - Orange Marmalade", "Sage - Pineapple",
# "Turmeric - Orange", "Azalea indica Orange Chimes". The genus or plant word
# anywhere in the title means it is not the fruit. Distinct from
# cultivar_parsing._ORNAMENTAL_WORDS (see the 1.6a note): that list carries
# "myrtle" and "fern", which would cost Lemon Myrtle and Cinnamon Myrtle here.
_NOT_FRUIT_WORDS = frozenset({
    "agapanthus", "allamanda", "azalea", "begonia", "bougainvillea",
    "cactus", "camellia", "canna", "chlorophytum", "clivia", "eucomis", "frangipani",
    "ginkgo", "grevillea", "heuchera", "hibiscus", "leucadendron", "mangave",
    "murraya", "nephrolepis", "oleander", "osmanthus", "philodendron",
    "russelia", "sage", "turmeric",
})


def _mask_not_the_fruit(t_lower: str) -> str:
    """Blank out other plants' names, keeping string positions aligned."""
    return _NOT_THE_FRUIT_RE.sub(lambda m: "~" * len(m.group()), t_lower)


def _names_another_plant(t_lower: str) -> bool:
    """Read on the UNMASKED title: masking "apple cactus" also hid "cactus"."""
    return bool(set(re.findall(r"[a-z]+", t_lower)) & _NOT_FRUIT_WORDS)


# --- The title's own binomial (1.8) -------------------------------------
#
# Many nurseries put the botanical name in brackets, and it is a free ground
# truth: "Illawarra Plum Pine (Podocarpus elatus)" cannot be a Prunus, and
# "Lemon-scented Gum (Corymbia citriodora)" cannot be a Citrus. When the
# bracketed genus disagrees with the record we matched, the match is dropped.
# On 2026-10-15 that removed 119 wrong matches, from Mock Orange (Murraya) to
# Pineapple Lily (Eucomis), and no right ones.
#
# Genus only, never the species epithet: "Black Walnut (Juglans nigra)" is a
# walnut even though the Walnut record says Juglans regia.
#
# A title genus has to look like one. "(Bare rooted)", "(Qld only)" and
# "(New variety)" are capitalised word pairs too, so the second word must
# carry a Latin ending and the first must not be a known English word.
_TITLE_BINOMIAL_RE = re.compile(r"\(\s*([A-Z][a-z]{2,})\s+(?:[x×]\s*)?([a-z][a-z\-]{2,})")
_LATIN_EPITHET_RE = re.compile(
    r"(?:a|ae|i|ii|o|um|us|is|ensis|oides|ex|ix|on|ans|ens|or|ys|os|es)$")
_NOT_A_GENUS = frozenset({
    "advanced", "bare", "dwarf", "fruit", "grafted", "new", "nut", "organic",
    "pick", "pickup", "qld", "queen", "seedling", "tropical", "velvick",
})
_NOT_AN_EPITHET = frozenset({"trees", "species", "rootstock", "only", "plants"})

# Botanists move species between genera, and nursery labels lag by decades:
# feijoa is still sold as "Feijoa sellowiana" (now Acca), jaboticaba as
# "Myrciaria cauliflora" (now Plinia), finger lime as "Citrus australasica".
# Genera in one group are the same genus for this check. Acmena and
# Waterhousia are here because both were sunk into Syzygium, which keeps the
# Lilly Pilly record's Acmena smithii hedging plants.
_GENUS_GROUPS = (
    {"acca", "feijoa"},
    {"plinia", "myrciaria"},
    {"syzygium", "eugenia", "acmena", "waterhousia"},
    {"selenicereus", "hylocereus"},
    {"annona", "rollinia"},
    {"citrus", "microcitrus", "eremocitrus", "fortunella", "poncirus"},
    {"vasconcellea", "carica"},
    {"solanum", "cyphomandra"},
    {"synsepalum", "richadella"},
    {"manilkara", "achras"},
    {"ziziphus", "zizyphus"},
    {"pouteria", "lucuma"},
    {"tasmannia", "drimys"},
    {"dimocarpus", "euphoria"},
    {"prunus", "amygdalus", "armeniaca", "cerasus", "persica"},
)


def _same_genus(a: str, b: str) -> bool:
    a, b = a.lower(), b.lower()
    return a == b or any(a in g and b in g for g in _GENUS_GROUPS)


def title_binomial(title: str) -> tuple[str, str] | None:
    """(genus, epithet) of a bracketed botanical name in the title, or None."""
    for m in _TITLE_BINOMIAL_RE.finditer(title):
        genus, epithet = m.group(1), m.group(2)
        if genus.lower() in _NOT_A_GENUS or epithet in _NOT_AN_EPITHET:
            continue
        if not _LATIN_EPITHET_RE.search(epithet):
            continue
        return genus, epithet
    return None


def title_genus(title: str) -> str | None:
    """The genus of a bracketed botanical name in the title, or None."""
    b = title_binomial(title)
    return b[0] if b else None


def latin_disagrees(title: str, latin: str) -> str | None:
    """The title's own binomial when it names a different SPECIES from the
    latin name we show, else None. The genus can no longer disagree (1.8
    drops those matches), so what this finds is a lumped record whose name
    is too narrow: "Black Walnut (Juglans nigra)" shown as Juglans regia.
    The nightly /admin report lists them so the next one is found by a
    machine rather than by Benedict reading the homepage."""
    b = title_binomial(title)
    if not b or not latin:
        return None
    words = latin.lower().replace("×", " ").replace("/", " ").split()
    if "spp." in words or b[1].lower() in words:
        return None
    return f"{b[0]} {b[1]}"


def _record_genus(value: dict) -> str:
    """Genus of a lookup value: a full species record or a compressed entry."""
    latin = value.get("latin_name") or value.get("ln") or ""
    return latin.split()[0] if latin else ""


def _contradicts_title(title: str, value: dict) -> bool:
    b, ours = title_binomial(title), _record_genus(value)
    # A lookup built without latin names (the /admin category matcher) has
    # nothing to contradict.
    if not (b and ours):
        return False
    if not _same_genus(b[0], ours):
        return True
    # "epithet_strict" records are one species in a genus full of ornamentals:
    # every fig sold as fruit is Ficus carica, while "'Midnight Petite' Fig
    # (Ficus benjamina)" and Ficus microcarpa are houseplants and hedges.
    if value.get("epithet_strict") or value.get("es"):
        latin = (value.get("latin_name") or value.get("ln") or "").split()
        return len(latin) > 1 and b[1].lower() != latin[1].lower()
    return False


def _rejected(title: str, t_lower: str, candidate: str, value: dict) -> bool:
    """Every reason a found candidate is still not the product's species."""
    return (_is_ornamental_relative(t_lower, candidate)
            or _names_another_plant(title.lower())
            or _contradicts_title(title, value))


# --- Derived lookup keys (1.6b) -----------------------------------------
#
# match_title only ever matched a registry name written exactly as the
# registry writes it, so two ordinary title spellings missed entirely:
#
#   Biloxi Blueberry     -> Blueberry      matches
#   Biloxi Blueberries   -> None           the PLURAL alone
#   Finger Lime <cv>     -> Finger Lime    matches in any position
#   Fingerlime           -> None           the one-word COMPOUND
#
# Both are fixed by adding explicit extra keys derived from the registry's own
# common names and synonyms. That keeps the vocabulary a closed set someone can
# read and grep, which is the point.
#
# Deliberately NOT a stemmer. A blanket stemmer would also make
# "Crab Apples Charlottae" match Apple, which is the ornamental crabapple that
# survives today only because "apples" is not a lookup key. That is luck, and
# 1.6a spent its whole existence replacing it with an actual guard BEFORE this
# ran. The ordering is the safety property; do not reverse it.
#
# Derived keys never overwrite a canonical one. Verified against the live
# registry (339 names, 537 derived keys): zero collisions.


def _plural(name: str) -> str:
    """English plural of a registry name. Deliberately dumb and explicit."""
    if name.endswith("y") and not name.endswith(("ay", "ey", "oy", "uy")):
        return name[:-1] + "ies"
    if name.endswith(("s", "x", "ch", "sh")):
        return name + "es"
    return name + "s"


def _derived_keys(name: str) -> list[str]:
    """Extra lookup spellings for one registry name: its plural, and for
    multi-word names the closed-up compound and that compound's plural."""
    nl = name.lower()
    keys = [_plural(nl)]
    if " " in nl:
        compound = nl.replace(" ", "")
        keys.append(compound)
        keys.append(_plural(compound))
    return keys


def _add_derived(lookup: dict, names_to_value: list) -> None:
    """Second pass over a built lookup, adding derived spellings. Canonical
    keys are already in place and always win."""
    for name, value in names_to_value:
        for key in _derived_keys(name):
            lookup.setdefault(key, value)


def _match_names(record: dict) -> list[str]:
    """A record's synonyms plus its "match_synonyms".

    match_synonyms are names this matcher should recognise but the variety
    parser (cultivar_parsing) must not: adding "Cherry Guava" as a plain
    synonym rewrote the live /variety/cherry-guava-red page's slug to
    guava-cherry-red. Variety slugs carry watches and inbound links, so a
    name that only fixes the species bucket goes here instead."""
    return list(record.get("synonyms", [])) + list(record.get("match_synonyms", []))


def build_species_lookup(species_list: list[dict] | None = None) -> dict:
    """Lowercase common_name/synonym -> the FULL species record."""
    if species_list is None:
        species_list = enabled_species()
    lookup = {}
    derived: list = []
    for s in species_list:
        lookup[s["common_name"].lower()] = s
        derived.append((s["common_name"], s))
        for syn in _match_names(s):
            if syn:
                lookup[syn.lower()] = s
                derived.append((syn, s))
    _add_derived(lookup, derived)
    return lookup


def load_species_lookup() -> dict:
    """Load fruit species data and build a title-matching lookup.

    A record may carry "synonym_latin": {synonym: latin}, for records that
    lump several species under one bucket. Custard Apple holds atemoya,
    cherimoya and bullock's heart, three species with three names; the record's
    single latin_name was printed beside all of them. The synonym's own entry
    carries the override as "pln" (product latin name). "ln" stays the
    record's name, because per-species tables (nursery pages) read it."""
    species = enabled_species()

    lookup = {}
    derived: list = []
    for s in species:
        common = s["common_name"].lower()
        entry = {
            "cn": s["common_name"],
            "ln": s["latin_name"],
            "sl": s["slug"],
            "r": s["region"],
        }
        # Parse genus/species from latin_name
        parts = s["latin_name"].split()
        if len(parts) >= 2:
            entry["g"] = parts[0]  # genus
        if s.get("epithet_strict"):
            entry["es"] = True  # see _contradicts_title

        overrides = {k.lower(): v for k, v in (s.get("synonym_latin") or {}).items()}
        lookup[common] = entry
        derived.append((s["common_name"], entry))
        for syn in _match_names(s):
            if syn:
                value = entry
                if syn.lower() in overrides:
                    value = dict(entry, pln=overrides[syn.lower()])
                lookup[syn.lower()] = value
                derived.append((syn, value))

    _add_derived(lookup, derived)
    return lookup


# --- Fruit sold under a parent fruit's name (2026-10-18) -----------------
#
# Nurseries file some citrus under the fruit a buyer already knows: yuzu
# (Citrus junos) as "Lemon 'Yuzu'", "Lemon - Yuzu" and "Citron | Yuzu",
# sudachi as "Lime - Sudachi". The leading-word rule reads the parent, so 13
# nurseries' yuzu landed in three different buckets. When the matched record
# is one of the listed parents and the title also names the fruit as a whole
# word, the fruit wins. A closed list, like _NOT_THE_FRUIT: the parent word is
# usually right ("Lemon - Eureka" is a lemon), so this is per-fruit evidence,
# not a rule. cultivar_parsing reads it too, so these titles stop building
# /variety/lemon-yuzu as if Yuzu were a lemon cultivar.
SOLD_UNDER_PARENT = {
    "yuzu": ("lemon", "citron", "lime"),
    "sudachi": ("lime", "lemon"),
    "chinotto": ("kumquat",),
    # Garcinia intermedia, sold as "Mangosteen 'Lemon Drop'" (2026-10-18)
    "lemon drop": ("mangosteen",),
    # Rubus probus, the native raspberry: "Raspberry - Atherton" (2026-10-18)
    "atherton": ("raspberry",),
}


def _sold_under(title_lower: str, candidate: str, lookup: dict) -> str | None:
    """The lookup key of a fruit the title names while its leading word
    matched a parent fruit, or None."""
    parent = lookup[candidate].get("slug") or lookup[candidate].get("sl")
    for name, parents in SOLD_UNDER_PARENT.items():
        if (parent in parents and name in lookup
                and re.search(r"(?<![a-z])" + name + r"(?![a-z])", title_lower)):
            return name
    return None


def _find(title: str, lookup: dict):
    """(candidate, t_lower, t_orig, leading) for the species named in a title,
    or None. A candidate that is found but rejected is None too: the title
    named a fruit word and it was the wrong plant, so nothing else in the
    title is trusted to be the species either."""
    title = _strip_invisible(title)
    pairs = [(title.lower(), title), _cleaned(title)]
    pairs = [(_mask_not_the_fruit(tl), to) for tl, to in pairs]

    # Leading: the raw title and the prefix-stripped one can both match, and
    # the one reaching further into the title wins. "Dwarf Plum Pine" matched
    # the Plum synonym "Dwarf Plum" before the stripped "Plum Pine" (Illawarra
    # Plum) was ever tried. On a tie the raw title wins, as it always did.
    best = None
    for t_lower, t_orig in pairs:
        candidate = _leading_candidate(t_lower, lookup)
        if candidate:
            end = len(title) - len(t_orig) + len(candidate)
            if best is None or end > best[0]:
                best = (end, candidate, t_lower, t_orig)
    if best:
        _, candidate, t_lower, t_orig = best
        if _rejected(title, t_lower, candidate, lookup[candidate]):
            return None
        fruit = _sold_under(t_lower, candidate, lookup)
        if fruit:
            # leading=None: the words around the fruit are its parent's name,
            # not a cultivar, so match_species extracts none.
            return fruit, t_lower, t_orig, None
        return candidate, t_lower, t_orig, True

    for t_lower, t_orig in pairs:
        candidate = _fallback_candidate(t_lower, lookup)
        if candidate:
            if _rejected(title, t_lower, candidate, lookup[candidate]):
                return None
            fruit = _sold_under(t_lower, candidate, lookup)
            if fruit:
                return fruit, t_lower, t_orig, None
            return candidate, t_lower, t_orig, False
    return None


def match_title(title: str, lookup: dict):
    """Match a product title to a lookup entry (values returned as-is)."""
    found = _find(title, lookup)
    return lookup[found[0]] if found else None


# --- Multi-graft trees (2026-10-18) -------------------------------------
#
# A product files under ONE species, the first named: "Peach + Nectarine +
# Plum + Peachcot" is a peach, so the plum page never showed it. Benedict's
# call: list multi-grafts on the other species' pages too, in a separate,
# lower section, and leave hybrids alone ("Nectarine x Plum - Spicezee" is
# one fruit, not two trees). Only the leading name is read: after a spaced
# dash come cultivar names, and "Plum Multi Graft - Satsuma/Santa Rosa" is
# two plums, not a plum and a mandarin. Quoted text is a cultivar for the
# same reason ("Guava 'Red Cherry/Strawberry'").
_QUOTED_RE = re.compile(r"(?:^|(?<=\s))['‘\"“][^'’\"”]*['’\"”]")
_GRAFT_SPLIT_RE = re.compile(r"\s*(?:\+|&|/)\s*|\s+and\s+")
_HYBRID_RE = re.compile(r"(?<![a-z])(?:x|×|hybrid)(?![a-z])")


def multigraft_species(title: str, lookup: dict) -> list[str]:
    """Slugs of every species a multi-graft title names, in title order, or
    [] when the title is not a multi-graft of 2+ species."""
    t = _strip_invisible(title)
    t = _QUOTED_RE.sub(" ", t)
    t = re.sub(r"\([^)]*\)", " ", t)
    t = re.split(r"\s[-–—]\s", t)[0]
    if _HYBRID_RE.search(t.lower()):
        return []
    found = []
    for part in _GRAFT_SPLIT_RE.split(t):
        value = match_title(part, lookup) if part.strip() else None
        slug = value and (value.get("slug") or value.get("sl"))
        if slug and slug not in [s for s, _ in found]:
            found.append((slug, _record_genus(value)))
    # The slash also writes a second name: "DAVIDSON PLUM / MULLUMBIMBI PLUM
    # (Davidsonia Jerseyana)" is one tree. When the bracketed genus is one of
    # the named species', a species of another genus is a fall-through, not a
    # graft. Case-insensitive on purpose: title_binomial wants a lowercase
    # epithet, and this nursery capitalises it.
    bracket = re.search(r"\(\s*([A-Za-z]{3,})\s+[A-Za-z]{3,}", title)
    if bracket and any(g and _same_genus(bracket.group(1), g) for _, g in found):
        found = [(s, g) for s, g in found if g and _same_genus(bracket.group(1), g)]
    slugs = [s for s, _ in found]
    return slugs if len(slugs) > 1 else []


def _match_span(t_orig: str, name: str) -> tuple[int, int]:
    """(index, length) of name in the original title, or (-1, 0)."""
    idx = t_orig.lower().find(name)
    return (idx, len(name)) if idx >= 0 else (-1, 0)


def match_species(title: str, lookup: dict) -> dict | None:
    """match_title on the compressed-entry lookup, plus cultivar extraction."""
    found = _find(title, lookup)
    if not found:
        return None
    candidate, _, t_orig, leading = found
    result = dict(lookup[candidate])
    cn = result["cn"].lower()

    if leading is None:
        return result
    if leading:
        # Whichever of the matched name and the common name ENDS later. A
        # synonym match ("Cherimoya - Sofia" on the Custard Apple record) has
        # no common name in it, and looking only for that lost the variety;
        # "Pluot Plum - Black Adder" has both, and the variety follows "Plum".
        spans = [_match_span(t_orig, name) for name in (candidate, cn)]
        spans = [sp for sp in spans if sp[0] >= 0]
        match_idx, match_len = max(spans, key=lambda sp: sp[0] + sp[1]) if spans else (-1, 0)
        # Extract cultivar: everything after the matched name
        if match_idx >= 0:
            remainder = t_orig[match_idx + match_len:].strip(" -–—'\",:;")
        else:
            remainder = ""
        if remainder and not remainder.startswith("("):
            # Check for quoted cultivar name: "Apple 'Granny Smith'"
            cv_match = re.match(r"['\"]([^'\"]+)['\"]", remainder)
            if cv_match:
                result["cv"] = cv_match.group(1)
            else:
                cv = remainder.split(" - ")[0].split(" (")[0].strip()
                # Don't treat size/pot info as cultivar
                if cv and not re.match(r'\d+mm|\d+cm|\d+ltr|pot|pack|pick\s*up|(?:tree|plant)s?$', cv.lower()):
                    result["cv"] = cv
        return result

    # Cultivar is the part BEFORE the species name
    match_idx, _ = _match_span(t_orig, cn)
    if match_idx > 0:
        cv = t_orig[:match_idx].strip(" -–—'\"()")
        # Remove trailing size info like (dwarf), (medium), (semi-dwarf)
        cv = re.sub(r'\s*\(?(dwarf|semi-dwarf|standard|medium|large|small|miniature)\)?$', '', cv, flags=re.I).strip()
        if cv and not re.match(r'\d+mm|\d+cm|\d+ltr|pot|pack', cv.lower()):
            result["cv"] = cv
    return result
