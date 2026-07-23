"""
Shared product-title -> species matcher (the dashboard's matcher, extracted).

Moved verbatim from build-dashboard.py so nursery pages (and any future
surface that groups products by species) count EXACTLY like the dashboard.
build_nursery_pages.py previously had its own cruder fork: substring-anywhere
plus genus-anywhere matching, and it read a nonexistent "aliases" key instead
of "synonyms". That fork counted "Peach ... (Prunus persica)" as Plum (genus
hit) and inflated species counts, so the "In Stock" drill-down links pointed
at dashboard views showing different numbers than the table said.

Matching strategy: longest leading-word-sequence match first (so "finger lime"
wins over "lime"), then a bounded any-position fallback for "Variety Species"
titles (e.g. "Akane Apple (medium)"). Also extracts a best-effort cultivar
name into result["cv"].

Distinct from cultivar_parsing.parse_cultivar (the variety-slug parser pinned
by tests/test_parsing.py): that one answers "which /variety/ page is this?",
this one answers "which species bucket does this product count under?". They
have different tolerances; do not merge them casually.
"""
import re

from stocklib.taxonomy import enabled_species


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


def match_species(title: str, lookup: dict) -> dict | None:
    """Try to match a product title against the species lookup."""
    title_lower = title.lower()

    # Strip common prefixes that precede the actual species name
    prefixes = ["dwarf ", "semi-dwarf ", "semi dwarf ", "miniature ", "standard ",
                 "grafted ", "advanced ", "bare root ", "bare-root "]
    clean_title = title_lower
    clean_title_original = title
    for prefix in prefixes:
        if clean_title.startswith(prefix):
            clean_title = clean_title[len(prefix):]
            clean_title_original = title[len(prefix):]
            break

    # Try matching on both original and cleaned title (prefix-first approach)
    for t_lower, t_orig in [(title_lower, title), (clean_title, clean_title_original)]:
        words = re.split(r'[\s\-–—]+', t_lower)
        for n in range(len(words), 0, -1):
            candidate = " ".join(words[:n])
            if candidate in lookup:
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

    # Fallback: try matching any N-word sequence starting at each position.
    # Handles "Variety Species (size)" format (e.g. Heritage Fruit Trees titles
    # like "Akane Apple (medium)" where "apple" is not at position 0).
    # Only try starting positions > 0 (already tried position 0 above).
    for t_lower, t_orig in [(title_lower, title), (clean_title, clean_title_original)]:
        words = re.split(r'[\s\-–—(]+', t_lower)
        words = [w.rstrip(").,") for w in words if w]
        for start in range(1, len(words)):
            for n in range(min(len(words) - start, 3), 0, -1):
                candidate = " ".join(words[start:start + n])
                if candidate in lookup:
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
