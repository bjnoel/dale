"""
Shared helpers for turning raw nursery product titles into cultivar
(species, variety) tuples and treestock variety slugs.

Used by:
- build_variety_pages.py  (builds /variety/<slug>.html pages)
- build_species_pages.py  (decides whether to render an Alerts link)
- send_variety_alerts.py  (detects watched varieties in today's stock)

Pinned to a shared behaviour by tests/test_parsing.py. Any change here
needs a passing test before being committed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


SIZE_WORDS = frozenset({
    'small', 'medium', 'large', 'xl', 'xxl', '75mm', '90mm',
    '140mm', '200mm', '250mm', '300mm', 'tube', 'pot', 'pots',
    'bag', 'bags', 'seedling', 'seedlings', 'grafted', 'cutting',
    'cuttings', 'standard', 'dwarf', 'bareroot', 'bare', 'root',
    'advanced', 'budget', 'self', 'fertile',
})

_SPECIES_FILE = Path(__file__).parent / "fruit_species.json"
_SPECIES_LOOKUP_CACHE: dict[str, str] | None = None


def _load_species_lookup() -> dict[str, str]:
    """Build {lowercased common_name or synonym -> canonical common_name}.
    Cached after first call. Returns {} if the species file is missing."""
    global _SPECIES_LOOKUP_CACHE
    if _SPECIES_LOOKUP_CACHE is not None:
        return _SPECIES_LOOKUP_CACHE
    if not _SPECIES_FILE.exists():
        _SPECIES_LOOKUP_CACHE = {}
        return _SPECIES_LOOKUP_CACHE
    lookup: dict[str, str] = {}
    try:
        with open(_SPECIES_FILE) as f:
            for s in json.load(f):
                name = s.get("common_name", "").strip()
                if name:
                    lookup[name.lower()] = name
                for syn in s.get("synonyms", []) or []:
                    syn = (syn or "").strip()
                    if syn:
                        lookup[syn.lower()] = name or syn
    except (OSError, json.JSONDecodeError):
        pass
    _SPECIES_LOOKUP_CACHE = lookup
    return lookup


def _species_match(title: str) -> tuple[str, str] | None:
    """For titles with no explicit separator, try to match a leading run
    of words against the species taxonomy. Returns (species, variety) or None.
    Only considered for titles with purely alphanumeric+space text, to avoid
    false-positives like 'Sapodilla / Chicku' (slash is a synonym marker)."""
    if re.search(r'[^\w\s]', title):
        return None
    lookup = _load_species_lookup()
    if not lookup:
        return None
    words = re.split(r'\s+', title.strip())
    for n in range(min(len(words), 4), 0, -1):
        candidate = ' '.join(words[:n]).lower()
        if candidate in lookup:
            species = ' '.join(words[:n])        # preserve original casing
            remainder = ' '.join(words[n:]).strip()
            if not remainder:
                return None                       # plain species name, no variety
            return (species, remainder)
    return None


def slugify(title: str) -> str:
    """Lowercase slug-form: 'Avocado - Hass' -> 'avocado-hass'."""
    s = title.lower()
    s = re.sub(r'[\u00ae\u2122()]', '', s)        # registered / trademark / parens
    s = re.sub(r'\s*[-\u2013\u2014]\s*', '-', s)  # normalize dash separators
    s = re.sub(r'[^a-z0-9-]', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-')


def parse_cultivar(title: str) -> tuple[str, str] | None:
    """Return (species, variety) or None if the title doesn't express a cultivar.

    Handles these title shapes (in order of preference):
        Species - Variety                 (most nurseries)
        Species 'Variety'                 (Ladybird style, curly or straight quotes)
        Species | Variety                 (Fruit Tree Cottage style; species must be
                                          a known one to avoid pipe false-positives)
        SpeciesWord VarietyWord...        (no separator; species taxonomy fallback)

    After parsing: strips trailing repeats of the species name from the variety
    ('Red Tamarillo' -> 'Red') and strips trailing size words ('Red Advanced' ->
    'Red') so that differently-worded titles for the same cultivar collapse to
    the same slug.
    """
    s = title.strip()

    has_dash = bool(re.search(r'\s*[-\u2013\u2014]\s+', s))
    quote_match = re.match(
        r"^(.+?)\s+['\"\u2018\u201c]([^'\"\u2018\u2019\u201c\u201d]+)['\"\u2019\u201d]", s,
    )

    species = variety = None

    if quote_match and not has_dash:
        species, variety = quote_match.group(1).strip(), quote_match.group(2).strip()
    elif has_dash:
        m = re.match(r'^(.+?)\s*[-\u2013\u2014]\s*(.+)$', s)
        if m:
            species, variety = m.group(1).strip(), m.group(2).strip()
    else:
        # Pipe separator, but only when the left side is a known species
        m = re.match(r'^(.+?)\s*\|\s*(.+)$', s)
        if m:
            lookup = _load_species_lookup()
            cand = m.group(1).strip()
            if cand.lower() in lookup:
                species, variety = cand, m.group(2).strip()
        # No separator at all -> taxonomy-based split
        if species is None:
            sp = _species_match(s)
            if sp:
                species, variety = sp

    if species is None or variety is None:
        return None

    # Collapse "Red Tamarillo" -> "Red" when variety redundantly ends with species
    sp_lower = species.lower()
    if variety.lower() == sp_lower:
        return None
    if variety.lower().endswith(' ' + sp_lower):
        variety = variety[:-(len(sp_lower) + 1)].strip()

    # Strip trailing size tokens: "Red Advanced" -> "Red"
    tokens = re.split(r'\s+', variety)
    while tokens and tokens[-1].lower() in SIZE_WORDS:
        tokens.pop()
    if not tokens:
        return None
    variety = ' '.join(tokens)

    # Reject single-letter varieties (avocado pollination types, etc.)
    if re.match(r'^[A-Za-z]\s*$', variety):
        return None
    # Reject species that start with a digit (e.g. "1L Richgro 'Poss")
    if re.match(r'^\d', species):
        return None
    # Reject when every remaining variety token is a size word
    variety_tokens = [t for t in re.split(r'[\s\-]+', variety.lower()) if t]
    if variety_tokens and all(t in SIZE_WORDS for t in variety_tokens):
        return None

    return (species, variety)


def product_variety_slug(title: str) -> str | None:
    """Parse + slugify in one step. Returns None when the title isn't a cultivar."""
    parsed = parse_cultivar(title)
    if not parsed:
        return None
    species, variety = parsed
    return slugify(f"{species}-{variety}") or None
