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


def build_species_lookup(species_list: list[dict] | None = None) -> dict:
    """Lowercase common_name/synonym -> the FULL species record."""
    if species_list is None:
        species_list = enabled_species()
    lookup = {}
    for s in species_list:
        lookup[s["common_name"].lower()] = s
        for syn in s.get("synonyms", []):
            if syn:
                lookup[syn.lower()] = s
    return lookup


def load_species_lookup() -> dict:
    """Load fruit species data and build a title-matching lookup."""
    species = enabled_species()

    lookup = {}
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
        for syn in s.get("synonyms", []):
            if syn:
                lookup[syn.lower()] = entry

    return lookup


def match_title(title: str, lookup: dict):
    """Match a product title to a lookup entry (values returned as-is)."""
    pairs = [(title.lower(), title), _cleaned(title)]
    for t_lower, _ in pairs:
        candidate = _leading_candidate(t_lower, lookup)
        if candidate:
            return lookup[candidate]
    for t_lower, _ in pairs:
        candidate = _fallback_candidate(t_lower, lookup)
        if candidate:
            return lookup[candidate]
    return None


def match_species(title: str, lookup: dict) -> dict | None:
    """match_title on the compressed-entry lookup, plus cultivar extraction."""
    pairs = [(title.lower(), title), _cleaned(title)]

    for t_lower, t_orig in pairs:
        candidate = _leading_candidate(t_lower, lookup)
        if candidate:
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
