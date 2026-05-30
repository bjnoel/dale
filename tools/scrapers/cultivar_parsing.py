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
_CANONICAL_SPECIES_CACHE: set[str] | None = None


def _canonical_species() -> set[str]:
    """Lowercased set of CANONICAL species names only (no cultivar synonyms).

    The full lookup maps cultivar-level synonyms like 'bacon avocado' or 'blood
    orange' to their species, which is right for availability matching but wrong
    for variety extraction (it would swallow the cultivar). The relaxed parser
    matches against this canonical set so 'Bacon Avocado' yields variety 'Bacon'."""
    global _CANONICAL_SPECIES_CACHE
    if _CANONICAL_SPECIES_CACHE is None:
        _CANONICAL_SPECIES_CACHE = {v.lower() for v in _load_species_lookup().values()}
    return _CANONICAL_SPECIES_CACHE


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


# --- Relaxed pass helpers -------------------------------------------------
# The strict parser below handles the clean, well-separated title shapes.
# Many real nursery titles wrap a perfectly good cultivar in listing noise
# (pot sizes, "Bare Rooted", "(Coffea arabica)", "Tree", trademark marks) or
# express a multigraft ("2-Way Apple 'Fuji + Pink Lady'") or put the variety
# in leading quotes ('"Alstonville" Finger Lime'). The relaxed pass below runs
# ONLY when the strict parser returns None, so it can never change an existing
# strict result (the strict tests stay pinned).

# Variety tokens that signal "this is a different (aromatic/foliage/lookalike)
# plant, not the fruit". A variety containing any of these is rejected, e.g.
# "Lemon Myrtle" (Backhousia, not Lemon), "Fiddle Leaf Fig" (Ficus lyrata),
# "Native Mulberry" (Pipturus), "Brazilian Cherry" (Eugenia). High-precision
# guard for the relaxed pass; the strict pass never consults it.
_VARIETY_TOKEN_DENY = frozenset({
    # aromatic / foliage confusables
    'myrtle', 'grass', 'balm', 'verbena', 'scented', 'leaf', 'leaves', 'aloe',
    # lookalike / wrong-genus qualifiers
    'native', 'wild', 'false', 'mock', 'ornamental', 'flowering', 'weeping',
    'fiddle', 'brazil', 'brazilian', 'barbados', 'cedar', 'chilean', 'african',
    'desert', 'mountain', 'midgen', 'midyim',
})

# Listing noise stripped before the relaxed taxonomy match. Leading volume
# tokens (e.g. "1L Mango") are deliberately NOT stripped here either, and a
# leading-digit variety is rejected below.
_NOISE_RES = [
    re.compile(p, re.I) for p in (
        r'\([^)]*\)',                                  # (Bare rooted), (Coffea arabica)
        r'[®™]',                             # registered / trademark
        r'["\'‘’“”]',                        # stray quotes
        r'\bcutting grown\b',
        r'\bgrafted\b',
        r'\bbare[\s-]?root(?:ed)?\b',
        r'\bpick\s*up only\b',
        r'\bpickup only\b',
        r'\bfruit trees?\b',
        r'\bnut trees?\b',
        r'\btrees?\b',
        r'\bpots?\b',
        r'\blow chill\b',
        r'\bdwarf\b',
        r'\b\d+\s*mm\b',
        r'(?<=\s)\d+\s*(?:l|lt|ltr|litre|liter)\b',    # trailing volume only (space before)
    )
]


def _strip_listing_noise(s: str) -> str:
    for rx in _NOISE_RES:
        s = rx.sub(' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _find_species_anywhere(cleaned: str) -> tuple[str, list[str], list[str]] | None:
    """Find a CANONICAL species as a contiguous word-run in `cleaned`.
    Returns (canonical_species, words_before, words_after) or None.
    Matches canonical names only (not cultivar synonyms), longest then earliest,
    so 'Bacon Avocado' yields species Avocado with 'Bacon' as the variety."""
    canon = _canonical_species()
    if not canon:
        return None
    words = cleaned.split()
    wl = [w.lower().strip('.,') for w in words]
    best = None  # (length, start_index, canonical)
    for n in range(min(len(words), 3), 0, -1):
        for i in range(len(words) - n + 1):
            cand = ' '.join(wl[i:i + n])
            if cand in canon:
                if best is None or i < best[1]:
                    best = (n, i, cand.title())
        if best:
            break
    if not best:
        return None
    n, i, _ = best
    # Use the canonical casing from the lookup values.
    canon_name = next((v for v in _load_species_lookup().values()
                       if v.lower() == ' '.join(wl[i:i + n])), ' '.join(words[i:i + n]))
    return (canon_name, words[:i], words[i + n:])


def _variety_ok(variety_tokens: list[str]) -> str | None:
    """Clean + validate a candidate variety. Returns the variety string or None."""
    # If any structural separator survived (- / | : etc.), a boundary was crossed
    # (e.g. "Sapodilla / Chicku", "Fruit Tree Cottage | Tamarillo"). Reject: the
    # token run is not a clean single variety.
    if any(re.search(r'[\-–—/|:;]', t) for t in variety_tokens):
        return None
    toks = [t for t in variety_tokens if t.lower().strip('.,') not in SIZE_WORDS]
    # Drop pure-punctuation / non-alphanumeric leftovers.
    toks = [t for t in toks if re.search(r'[A-Za-z0-9]', t)]
    if not toks or len(toks) > 5:
        return None
    lookup = _load_species_lookup()
    low = [t.lower().strip(".,'\"()") for t in toks]
    # Reject foliage/lookalike qualifiers, and varieties that themselves contain
    # another species word (usually a lookalike or a mis-joined multi-species title).
    if any(t in _VARIETY_TOKEN_DENY or t in lookup for t in low):
        return None
    variety = ' '.join(toks)
    # Reject single-letter (pollination type) and digit-leading varieties.
    if re.match(r'^[A-Za-z]\s*$', variety) or re.match(r'^\d', variety):
        return None
    # Require at least one alphabetic token (not all numbers/codes).
    if not any(re.search(r'[A-Za-z]', t) for t in toks):
        return None
    return variety


def _parse_multigraft(s: str) -> tuple[str, str] | None:
    """Treat an N-way / multigraft tree as ONE combo variety.

    'Apple 2-Way Fuji + Pink Lady' -> ('Apple', '2way fuji pink lady'),
    with the component cultivars sorted so the same combo collapses to one slug
    regardless of order. Single-species picks that species; cross-species combos
    (peach/nectarine) take the first recognised species.
    """
    nway = re.search(r'\b(\d+)\s*[-\s]?way\b', s, re.I)
    multi = re.search(r'\bmulti[\s-]?graft', s, re.I)
    if not nway and not multi:
        return None
    cleaned = _strip_listing_noise(s)
    fs = _find_species_anywhere(cleaned)
    if not fs:
        return None
    species, _, _ = fs
    # Remove the N-way / multigraft marker and every species word from the blob,
    # leaving the component cultivar names.
    blob = re.sub(r'\b\d+\s*[-\s]?way\b', ' ', cleaned, flags=re.I)
    blob = re.sub(r'\bmulti[\s-]?graft(?:ed)?\b', ' ', blob, flags=re.I)
    for tok in species.lower().split():
        blob = re.sub(r'\b' + re.escape(tok) + r'\b', ' ', blob, flags=re.I)
    parts = re.split(r'\s*(?:\+|&|\band\b|/|,|\bx\b)\s*', blob, flags=re.I)
    comps = []
    for part in parts:
        toks = [t for t in part.split() if t.lower() not in SIZE_WORDS]
        phrase = ' '.join(toks).strip().lower()
        if phrase and phrase not in comps:
            comps.append(phrase)
    if not comps:
        return None
    prefix = (nway.group(1) + 'way') if nway else 'multigraft'
    variety = prefix + ' ' + ' '.join(sorted(comps))
    return (species, variety.strip())


def _parse_leading_quote(s: str) -> tuple[str, str] | None:
    """'"Alstonville" Finger Lime 90mm Pots' -> ('Finger Lime', 'Alstonville').

    Only accepted when the words AFTER the quote lead with a known fruit species
    (so '"Some Name" Tomato/Basil' is not turned into a fruit cultivar)."""
    m = re.match(r"^['\"‘“]([^'\"’”‘“]+)['\"’”]\s+(.+)$", s)
    if not m:
        return None
    variety = m.group(1).strip()
    rest = _strip_listing_noise(m.group(2))
    fs = _find_species_anywhere(rest)
    if not fs:
        return None
    species, before, _after = fs
    if before:                       # species must lead the post-quote remainder
        return None
    v = _variety_ok(variety.split())
    return (species, v) if v else None


def _relaxed_parse(title: str) -> tuple[str, str] | None:
    """Best-effort parse for titles the strict parser rejects. High precision:
    multigrafts, leading-quote fruit titles, and noise-stripped single-cultivar
    titles where the species sits cleanly on one side. Aromatic/lookalike
    confusables are denied."""
    s = title.strip()
    mg = _parse_multigraft(s)
    if mg:
        return mg
    lq = _parse_leading_quote(s)
    if lq:
        return lq
    cleaned = _strip_listing_noise(s)
    if not cleaned:
        return None
    fs = _find_species_anywhere(cleaned)
    if not fs:
        return None
    species, before, after = fs
    # Species must sit cleanly at one end: words on exactly one side are the
    # variety. Species in the middle (words both sides) is ambiguous -> reject.
    if before and after:
        return None
    v = _variety_ok(before or after)
    return (species, v) if v else None


def parse_cultivar(title: str) -> tuple[str, str] | None:
    """Return (species, variety) or None if the title doesn't express a cultivar.

    Tries the strict parser first (clean separator / quote / taxonomy shapes),
    then a relaxed pass for noisy titles, multigrafts, and leading-quote titles.
    The relaxed pass runs only when strict returns None, so strict behaviour is
    unchanged.
    """
    r = _strict_parse(title)
    if r is not None:
        return r
    return _relaxed_parse(title)


def _strict_parse(title: str) -> tuple[str, str] | None:
    """Strict cultivar parse. Handles these title shapes (in order of preference):
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
