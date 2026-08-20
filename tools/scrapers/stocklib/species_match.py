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


def _cleaned(title: str) -> tuple[str, str]:
    """(lowercase, original-case) title with the first matching prefix stripped."""
    title_lower = title.lower()
    for prefix in _PREFIXES:
        if title_lower.startswith(prefix):
            return title_lower[len(prefix):], title[len(prefix):]
    return title_lower, title


def _leading_candidate(t_lower: str, lookup: dict) -> str | None:
    """Longest leading word sequence that is a lookup key."""
    words = re.split(r'[\s\-–—]+', t_lower)
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


def build_species_lookup(species_list: list[dict] | None = None) -> dict:
    """Lowercase common_name/synonym -> the FULL species record."""
    if species_list is None:
        species_list = enabled_species()
    lookup = {}
    derived: list = []
    for s in species_list:
        lookup[s["common_name"].lower()] = s
        derived.append((s["common_name"], s))
        for syn in s.get("synonyms", []):
            if syn:
                lookup[syn.lower()] = s
                derived.append((syn, s))
    _add_derived(lookup, derived)
    return lookup


def load_species_lookup() -> dict:
    """Load fruit species data and build a title-matching lookup."""
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

        lookup[common] = entry
        derived.append((s["common_name"], entry))
        for syn in s.get("synonyms", []):
            if syn:
                lookup[syn.lower()] = entry
                derived.append((syn, entry))

    _add_derived(lookup, derived)
    return lookup


def match_title(title: str, lookup: dict):
    """Match a product title to a lookup entry (values returned as-is)."""
    pairs = [(title.lower(), title), _cleaned(title)]
    for t_lower, _ in pairs:
        candidate = _leading_candidate(t_lower, lookup)
        if candidate:
            if _is_ornamental_relative(t_lower, candidate):
                return None
            return lookup[candidate]
    for t_lower, _ in pairs:
        candidate = _fallback_candidate(t_lower, lookup)
        if candidate:
            if _is_ornamental_relative(t_lower, candidate):
                return None
            return lookup[candidate]
    return None


def match_species(title: str, lookup: dict) -> dict | None:
    """match_title on the compressed-entry lookup, plus cultivar extraction."""
    pairs = [(title.lower(), title), _cleaned(title)]

    for t_lower, t_orig in pairs:
        candidate = _leading_candidate(t_lower, lookup)
        if candidate:
            if _is_ornamental_relative(t_lower, candidate):
                return None
            result = dict(lookup[candidate])
            # Extract cultivar: everything after the matched common name
            matched = lookup[candidate]["cn"]
            # Find where the match ends in the original title
            match_idx = t_orig.lower().find(matched.lower())
            if match_idx >= 0:
                remainder = t_orig[match_idx + len(matched):].strip(" -–—'\"")
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
                    if cv and not re.match(r'\d+mm|\d+cm|\d+ltr|pot|pack|pick\s*up', cv.lower()):
                        result["cv"] = cv
            return result

    for t_lower, t_orig in pairs:
        candidate = _fallback_candidate(t_lower, lookup)
        if candidate:
            if _is_ornamental_relative(t_lower, candidate):
                return None
            result = dict(lookup[candidate])
            # Cultivar is the part BEFORE the species name
            matched = lookup[candidate]["cn"]
            match_idx = t_orig.lower().find(matched.lower())
            if match_idx > 0:
                cv = t_orig[:match_idx].strip(" -–—'\"()")
                # Remove trailing size info like (dwarf), (medium), (semi-dwarf)
                cv = re.sub(r'\s*\(?(dwarf|semi-dwarf|standard|medium|large|small|miniature)\)?$', '', cv, flags=re.I).strip()
                if cv and not re.match(r'\d+mm|\d+cm|\d+ltr|pot|pack', cv.lower()):
                    result["cv"] = cv
            return result

    return None
