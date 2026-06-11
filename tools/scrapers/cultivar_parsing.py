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
from collections import defaultdict
from pathlib import Path


SIZE_WORDS = frozenset({
    'small', 'medium', 'large', 'xl', 'xxl', '75mm', '90mm',
    '140mm', '200mm', '250mm', '300mm', 'tube', 'pot', 'pots',
    'bag', 'bags', 'seedling', 'seedlings', 'grafted', 'cutting',
    'cuttings', 'standard', 'dwarf', 'semi', 'bareroot', 'bare', 'root',
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
        r'\bsemi[\s-]?dwarf\b',                        # before bare dwarf, or it leaves "Semi-"
        r'\bdwarf\b',
        r'\b\d+\s*mm\b',
        r'(?<=\s)\d+\s*(?:l|lt|ltr|litre|liter)\b',    # trailing volume only (space before)
    )
]


def _strip_listing_noise(s: str, *, keep_dwarf: bool = False) -> str:
    """keep_dwarf: banana titles keep dwarf/semi-dwarf -- "Dwarf Cavendish" is a
    cultivar, not a size (same exception _clean_cultivar_parts applies)."""
    for rx in _NOISE_RES:
        if keep_dwarf and rx.pattern in (r'\bsemi[\s-]?dwarf\b', r'\bdwarf\b'):
            continue
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


def _variety_ok(variety_tokens: list[str], species: str = '') -> str | None:
    """Clean + validate a candidate variety. Returns the variety string or None."""
    # A STANDALONE dash followed by nothing but size/noise words is trailing
    # listing noise ("Anna - Medium" after the cleaners ran): truncate there.
    # Anything substantive after the dash, or any other standalone separator
    # (| / : ; delimit foreign content like nursery names), still rejects.
    dashes = {'-', '–', '—'}
    sep_idx = next((i for i, t in enumerate(variety_tokens) if t in dashes), None)
    if sep_idx is not None:
        tail = [t for t in variety_tokens[sep_idx + 1:] if t not in dashes]
        if all(t.lower().strip('.,') in SIZE_WORDS for t in tail):
            variety_tokens = variety_tokens[:sep_idx]
        else:
            return None
    # If any embedded separator survived (- / | : etc.), a boundary was crossed
    # (e.g. "Sapodilla / Chicku", "Fruit Tree Cottage | Tamarillo"). Reject: the
    # token run is not a clean single variety.
    if any(re.search(r'[\-–—/|:;]', t) for t in variety_tokens):
        return None
    # Bananas keep dwarf/super/semi: "Dwarf Cavendish" is a cultivar, not a size.
    drop = SIZE_WORDS if species.strip().lower() != 'banana' else (SIZE_WORDS - {'dwarf', 'super', 'semi'})
    toks = [t for t in variety_tokens if t.lower().strip('.,') not in drop]
    # Strip a trailing restatement of the species the caller already found, so
    # "Pink Lady Apple" (species Apple) validates as "Pink Lady" instead of being
    # rejected for containing a species word.
    if species:
        sp_words = species.lower().split()
        while (len(toks) > len(sp_words)
               and [t.lower().strip(".,'\"()") for t in toks[-len(sp_words):]] == sp_words):
            toks = toks[:-len(sp_words)]
    # Drop pure-punctuation / non-alphanumeric leftovers.
    toks = [t for t in toks if re.search(r'[A-Za-z0-9]', t)]
    if not toks or len(toks) > 5:
        return None
    lookup = _load_species_lookup()
    low = [t.lower().strip(".,'\"()") for t in toks]
    # Reject foliage/lookalike qualifiers anywhere in the candidate.
    if any(t in _VARIETY_TOKEN_DENY for t in low):
        return None
    # A species word at either END is a lookalike or a mis-joined multi-species
    # title -> reject. MID-phrase species words are real cultivar names ("Cox
    # Orange Pippin") and pass.
    if low and (low[0] in lookup or low[-1] in lookup):
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
    cleaned = _strip_listing_noise(s, keep_dwarf=('banana' in s.lower()))
    if not cleaned:
        return None
    fs = _find_species_anywhere(cleaned)
    if not fs:
        return None
    species, before, after = fs
    # Species must sit cleanly at one end: words on exactly one side are the
    # variety. Species in the middle (words both sides) is ambiguous -> reject.
    # Banana exception: a dwarf/super/semi prefix BELONGS to the cultivar
    # ("Dwarf Banana Ducasse" is Dwarf Ducasse), so fold it into the variety.
    if before and after:
        if (species.lower() == 'banana'
                and all(t.lower() in ('dwarf', 'super', 'semi') for t in before)):
            before, after = [], before + after
        else:
            return None
    v = _variety_ok(before or after, species=species)
    return (species, v) if v else None


# --- Post-parse cleaning --------------------------------------------------
# The strict parser keeps clean separator shapes verbatim, so listing noise
# riding INSIDE the species/variety (pot sizes, "(grafted)", "QLD ONLY",
# "Super Dwarf", "Tubestock", ...) survives into the slug and fragments one
# cultivar across many variety pages. This pass runs on the FINAL (species,
# variety) tuple from EITHER parser and strips that noise so the variants
# collapse to one slug. Size/form words (super/semi/dwarf) are stripped
# EXCEPT for bananas, where "Dwarf Cavendish"/"Dwarf Ducasse" are real
# cultivars, not sizes (Benedict's call, 2026-06-08).

# A parenthetical group is pure noise (and gets deleted) when every alpha word
# inside it is one of these; otherwise the parens are unwrapped and the inner
# text kept, so "(grafted)" -> removed but "(Imperial)" -> "Imperial".
_NOISE_PAREN_WORDS = frozenset({
    'grafted', 'bare', 'bareroot', 'bear', 'rooted', 'root', 'cutting', 'grown',
    'qld', 'only', 'pick', 'pickup', 'up', 'dwarf', 'super', 'semi', 'standard',
    'advanced', 'size', 'orchard', 'tubestock', 'tube', 'stock', 'pot', 'pots',
    'restricted', 'to', 'se', 'south', 'east',
    'small', 'medium', 'large', 'low', 'chill',
    'stone', 'fruit',                       # "(stone fruit)" category tag
})

# --- Displayable type labels (DEC-177) ------------------------------------
# Form / rootstock / propagation tokens a shopper cares about when telling two
# otherwise-identical nursery rows apart (Yalca's Dwarf vs Aus Nurseries' Bare
# rooted on one /variety/apple-gala.html page). DEC-176 strips these from the
# cultivar NAME so the rows group onto a single page; extract_type_label() below
# brings the info back as a per-row pill.
#
# This ONE ordered (regex, Display Label) list is the single source of truth:
# the cleaner strips exactly these tokens AND extract_type_label surfaces exactly
# these labels (both reference these same compiled regexes), so the strip set and
# the label set can never drift. "grafted"/"standard" and pot sizes are NOT here
# -- they're stripped as noise but are the default form, so they get no pill.
#
# Output order is form, then propagation, then Advanced. Form is listed
# longest-first so "Super Dwarf" wins over "Dwarf": extract_type_label consumes a
# match before testing the next pattern, so bare "Dwarf" can't re-fire inside it.
_RE_SUPER_DWARF = re.compile(r'\bsuper[\s-]?dwarf\b', re.I)
_RE_SEMI_DWARF = re.compile(r'\bsemi[\s-]?dwarf\b', re.I)
_RE_DWARF = re.compile(r'\bdwarf\b', re.I)
_RE_BARE_ROOTED = re.compile(r'\bbare[\s-]?root(?:ed)?\b', re.I)
_RE_BEAR_ROOTED = re.compile(r'\bbear[\s-]?root(?:ed)?\b', re.I)   # common "bear rooted" typo
_RE_TUBESTOCK = re.compile(r'\btube[\s-]?stock\b', re.I)
_RE_CUTTING_GROWN = re.compile(r'\bcutting grown\b', re.I)
_RE_ADVANCED = re.compile(r'\badvanced\b', re.I)

_TYPE_LABELS = [
    (_RE_SUPER_DWARF, "Super Dwarf"),
    (_RE_SEMI_DWARF, "Semi Dwarf"),
    (_RE_DWARF, "Dwarf"),
    (_RE_BARE_ROOTED, "Bare rooted"),
    (_RE_BEAR_ROOTED, "Bare rooted"),
    (_RE_TUBESTOCK, "Tubestock"),
    (_RE_CUTTING_GROWN, "Cutting grown"),
    (_RE_ADVANCED, "Advanced"),
]

# Bare "super"/"semi" (no "dwarf"): used only by the cleaner, to catch a leftover
# "Dorsett Golden - Super" fragment. Not standalone pill labels.
_RE_SUPER = re.compile(r'\bsuper\b', re.I)
_RE_SEMI = re.compile(r'\bsemi\b', re.I)

# Multi-word noise phrases stripped from both sides, all species (longest /
# most specific first). Shipping restrictions (with or without a leading
# "restricted to" and an optional trailing "only"), container/propagation and
# chill-requirement noise, bare-rooted (and the common "bear rooted" typo). The
# tubestock / cutting-grown / bare-rooted entries reference the shared
# _TYPE_LABELS regexes so the strip and the pill stay in lockstep.
# NOTE: the bare "qld" (no "only") is deliberately NOT stripped -- it marks a
# real botanical form for some plants (Davidson Plum QLD, QLD Arrowroot).
_CLEAN_PHRASE_RES = [
    re.compile(r'restricted to [a-z/.\s]*?qld(?:\s*\[?\s*banana region\s*\]?)?(?:\s+only)?', re.I),
    re.compile(r'\b(?:south[\s-]?east|s\.?\s*e\.?|se)\s*qld(?:\s+only)?\b', re.I),
    re.compile(r'\bqld\s+only\b', re.I),
    re.compile(r'\bpick\s*up(?:\s+only)?\b', re.I),
    _RE_TUBESTOCK,
    _RE_CUTTING_GROWN,
    re.compile(r'\blow[\s-]?chill\b', re.I),
    re.compile(r'\badvanced size\b', re.I),
    re.compile(r'\borchard size\b', re.I),
    _RE_BARE_ROOTED,
    _RE_BEAR_ROOTED,
]

# Single-word noise stripped from both sides, all species. "large/medium/small"
# and "pot/pots" are pure size/container words; cultivar size names that ARE
# meaningful (Mammoth, Giant, Jumbo) are deliberately NOT here. "advanced" is the
# shared _TYPE_LABELS regex (runs after the "advanced size" phrase above).
_CLEAN_WORD_RES = [
    re.compile(r'\b' + p + r'\b', re.I) for p in (
        'grafted', 'bareroot', 'standard',
        'large', 'medium', 'small', 'pot', 'pots',
    )
] + [_RE_ADVANCED]

# Size/form words stripped EXCEPT for bananas. "super"/"semi" alone catch
# "Dorsett Golden - Super" (the trailing "Dwarf" already gone); the combined
# forms run first so "Super Dwarf" goes in one shot. super-dwarf / semi-dwarf /
# dwarf are the shared _TYPE_LABELS regexes.
_CLEAN_SIZEFORM_RES = [_RE_SUPER_DWARF, _RE_SEMI_DWARF, _RE_SUPER, _RE_SEMI, _RE_DWARF]

# Volume / pot tokens stripped anywhere. Litres ("2L", "45Ltr") and pot
# dimensions in mm/cm/ml ("90mm", "20 cm", "100/130mm", "140ml"). Verified NOT
# to match "2way" or "R2E2" (no word boundary before the digits there).
_CLEAN_VOLUME_RE = re.compile(r'\b\d+\s*(?:l|lt|ltr|litre|liter)\b', re.I)
_CLEAN_POTMM_RE = re.compile(r'\b\d+(?:\s*/\s*\d+)*\s*(?:mm|cm|ml)\b', re.I)

# A cleaned variety made of nothing but these is not a real cultivar -> reject.
_SIZEFORM_ONLY = frozenset({
    'dwarf', 'super', 'semi', 'standard', 'advanced', 'grafted', 'tubestock',
    'bareroot', 'bare', 'rooted', 'root', 'size', 'orchard', 'pot', 'pots', 'tube',
    'large', 'medium', 'small',
})


def _strip_noise_parens(s: str) -> str:
    """Delete parenthetical groups whose inner text is pure listing noise
    (e.g. "(grafted)", "(QLD ONLY)"); unwrap groups carrying a real qualifier
    (e.g. "(Imperial)" -> "Imperial")."""
    def repl(m: "re.Match[str]") -> str:
        inner = m.group(1)
        words = [w.lower().strip('.,') for w in re.findall(r'[A-Za-z]+', inner)]
        if words and all(w in _NOISE_PAREN_WORDS for w in words):
            return ' '
        return ' ' + inner + ' '
    return re.sub(r'\(([^)]*)\)', repl, s)


def _clean_part(text: str, *, strip_sizeform: bool) -> str:
    """Strip listing noise from one side (species or variety). Order matters:
    embedded en/em-dashes must collapse to spaces BEFORE the phrase regexes, or
    "Dorsett Golden - Super Dwarf" never matches the "Super Dwarf" phrase (the
    strict parser only splits on the FIRST dash)."""
    s = _strip_noise_parens(text)
    s = re.sub(r'[®™*]', ' ', s)            # trademark marks + **PICKUP** stars
    s = s.replace('(', ' ').replace(')', ' ')
    s = re.sub(r'[:;]', ' ', s)                       # "Blue Java: RESTRICTED..."
    s = s.replace('_', ' ')                           # "Navel_17cm" -> "Navel 17cm"
    s = re.sub(r'\s*[–—]\s*', ' ', s)       # embedded en/em-dash -> space
    for rx in _CLEAN_PHRASE_RES:
        s = rx.sub(' ', s)
    for rx in _CLEAN_WORD_RES:
        s = rx.sub(' ', s)
    if strip_sizeform:
        for rx in _CLEAN_SIZEFORM_RES:
            s = rx.sub(' ', s)
    s = _CLEAN_VOLUME_RE.sub(' ', s)
    s = _CLEAN_POTMM_RE.sub(' ', s)
    s = re.sub(r'\s+', ' ', s).strip(" -'\"")
    return s


def _clean_cultivar_parts(species: str, variety: str) -> tuple[str, str] | None:
    """Post-parse cleanup applied to BOTH strict and relaxed results. Returns a
    cleaned (species, variety) or None if cleaning leaves nothing real."""
    is_banana = species.strip().lower() == 'banana'
    sp = _clean_part(species, strip_sizeform=not is_banana)
    var = _clean_part(variety, strip_sizeform=not is_banana)
    if not sp or not var:
        return None
    if re.match(r'^[A-Za-z]\s*$', var):              # single-letter pollination type
        return None
    var_tokens = [t for t in re.split(r'[\s\-]+', var.lower()) if t]
    if var_tokens and all(t in _SIZEFORM_ONLY for t in var_tokens):
        return None
    return (sp, var)


def parse_cultivar(title: str) -> tuple[str, str] | None:
    """Return (species, variety) or None if the title doesn't express a cultivar.

    Tries the strict parser first (clean separator / quote / taxonomy shapes),
    then a relaxed pass for noisy titles, multigrafts, and leading-quote titles.
    The relaxed pass runs only when strict yields nothing, so a successful strict
    parse is never overridden. Both results pass through _clean_cultivar_parts,
    which strips listing noise (pot sizes, "(grafted)", "QLD ONLY", "Super
    Dwarf", ...) so size/rootstock variants of one cultivar collapse to a single
    slug. A strict result whose parts CLEAN to nothing (the cultivar sat inside
    the pre-dash segment, e.g. "Dwarf Apple 'Anna' - Medium") also falls through
    to the relaxed pass instead of failing outright.
    """
    r = _strict_parse(title)
    cleaned = _clean_cultivar_parts(*r) if r else None
    if cleaned is None:
        r = _relaxed_parse(title)
        cleaned = _clean_cultivar_parts(*r) if r else None
    return cleaned


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


# --- Taxonomy scope gate (DEC-195) ----------------------------------------
#
# /variety/ pages and variety alerts only cover the fruit/nut/berry taxonomy.
# General nurseries (Ladybird especially) sell ornamentals and veg whose titles
# parse cleanly ("Rose - Iceberg"), so parse success alone is not a scope test.

# Plant-form / other-plant words: a known species followed by one of these is
# a DIFFERENT plant that borrows the fruit's name ("Lemon Myrtle", "Apple
# Cactus", "Pineapple Lily", "Peanut Tree"), not a cultivar of the fruit.
_NON_FRUIT_FORM_WORDS = frozenset({
    'tree', 'palm', 'vine', 'bush', 'shrub', 'grass', 'fern', 'lily',
    'daisy', 'cactus', 'laurel', 'pine', 'myrtle', 'jessamine', 'gum',
    'wattle', 'ivy', 'creeper', 'berry', 'mint', 'thyme', 'sage', 'basil',
    'balm', 'verbena', 'melon', 'cucumber', 'gourd',
})

# Ornamental genus words. Needed because the relaxed parser can read a
# fruit-as-COLOR word as the species: "Hibiscus Petite Orange" parses to
# species "Orange". The species gate can't catch that, but the raw title
# names the real genus. Checked against whole-title tokens. Verified against
# the live catalogue 2026-06-11: every title carrying one of these is a true
# ornamental (incl. "Frangipani Mango Delight", "Leucadendron 'Strawberry and
# Cream'"). 'rosa'/'nerium' stay paren-only: "Plum - Santa Rosa" is a plum.
_ORNAMENTAL_WORDS = frozenset({
    'bougainvillea', 'grevillea', 'canna', 'heuchera', 'hibiscus',
    'philodendron', 'oleander', 'frangipani', 'plumeria', 'begonia',
    'bracteantha', 'leucospermum', 'leucadendron', 'nephrolepis',
    'saxifraga', 'fern', 'myrtle',
})
# Latin genus in parentheses ("Rose Showpiece Orange (Rosa)") is authoritative.
_ORNAMENTAL_PAREN_WORDS = _ORNAMENTAL_WORDS | frozenset({'rosa', 'nerium'})

# Active variety watches that predate the gate and point at non-fruit pages
# (kawakawa x2, maroon bush x2, mandevilla, begonia, cinnamon myrtle as of
# 2026-06-11). Their pages and alerts stay alive until the taxonomy grows a
# natives/ornamentals category (stocklib.taxonomy.ENABLED_CATEGORIES). Closed
# list: the pages' species stay out of scope, so no NEW watches can be added.
GRANDFATHERED_VARIETY_SLUGS = frozenset({
    'piper-excelsum-kawakawa',
    'maroon-bush-scaevola-spinescens',
    'mandevilla-peach-sunrise',
    'begonia-bewitched-red-black',
    'cinnamon-myrtle-mini',
})


_LATIN_NOISE_CACHE: frozenset[str] | None = None

# Australian state words duplicate the species' origin when they ride in the
# species slot ("Ooray Queensland Davidson's Plum"); dropped from leftovers
# only, never from the variety itself ("Davidson's Plum - NSW" is a real
# selection name).
_STATE_WORDS = frozenset({
    'nsw', 'qld', 'queensland', 'vic', 'victoria', 'wa', 'sa', 'nt',
    'tas', 'tasmania', 'act',
})


def _latin_noise_words() -> frozenset[str]:
    """Words that carry no cultivar information wherever they appear: latin
    binomial fragments from the taxonomy ("Davidsonia", "Plinia"), epithets of
    related species, propagation noise ("marcott"), cross markers, and 'form'
    ("NSW Form Davidsonia jerseyana" is the NSW selection)."""
    global _LATIN_NOISE_CACHE
    if _LATIN_NOISE_CACHE is None:
        words = {
            'marcott', 'marcotted', 'x', 'spp', 'var', 'cv', 'form',
            'jerseyana', 'johnsonii', 'pruriens', 'phitrantha',
        }
        if _SPECIES_FILE.exists():
            try:
                with open(_SPECIES_FILE) as f:
                    for r in json.load(f):
                        words.update(re.findall(r'[a-z]+', (r.get('latin_name') or '').lower()))
            except (OSError, json.JSONDecodeError):
                pass
        _LATIN_NOISE_CACHE = frozenset(words)
    return _LATIN_NOISE_CACHE


def _ornamental_title(title: str) -> bool:
    """True when the raw title names an ornamental genus, in the text or in a
    parenthesized latin name ("Rose Showpiece Orange (Rosa)")."""
    tl = title.lower()
    if set(re.findall(r'[a-z]+', tl)) & _ORNAMENTAL_WORDS:
        return True
    parens = ' '.join(re.findall(r'\(([^)]*)\)', tl))
    return bool(set(re.findall(r'[a-z]+', parens)) & _ORNAMENTAL_PAREN_WORDS)


def _synonym_extra(text: str, canonical: str) -> str:
    """Cultivar info a matched synonym carries beyond the canonical name:
    'Meyer Lemon' -> 'Meyer', 'Bacon Avocado' -> 'Bacon'. Pure renames and
    respellings ('Jakfruit', 'Cumquat', 'Annona squamosa') share no word with
    the canonical name and return ''. Words that are themselves a synonym of
    the same species ('Carambola Starfruit'), size/form words ('Dwarf Mango'),
    and plant-form words ('Kiwi Berry') are not cultivar info either."""
    lookup = _load_species_lookup()
    canon_words = [re.sub(r'[^a-z]', '', w) for w in canonical.lower().split()]

    def matches(wn: str) -> bool:
        return any(
            wn == c or (len(wn) >= 4 and len(c) >= 4 and (c.startswith(wn) or wn.startswith(c)))
            for c in canon_words
        )

    words = text.split()
    norm = [re.sub(r'[^a-z]', '', w.lower()) for w in words]
    if not any(matches(wn) for wn in norm if wn):
        return ""
    return ' '.join(
        w for w, wn in zip(words, norm)
        if wn and not matches(wn) and wn not in SIZE_WORDS
        and wn not in _NON_FRUIT_FORM_WORDS and lookup.get(wn) != canonical
    )


def canonicalize_species(species: str) -> tuple[str, str] | None:
    """Map a parsed species text onto the taxonomy: ('canonical name',
    'leftover cultivar words') or None when out of scope (DEC-195/196).

    'Jakfruit' -> ('Jackfruit', ''); 'Meyer Lemon' -> ('Lemon', 'Meyer');
    'Mandarin Imperial' -> ('Mandarin', 'Imperial'); 'Jackfruit Marcott' ->
    ('Jackfruit', ''); "Davidson's Plum Davidsonia jerseyana" ->
    ("Davidson's Plum", ''); 'Rose' -> None. A leading match is rejected when
    the remainder names a different plant form ('Lemon Myrtle', 'Apple
    Cactus'). Fails open (returns the input) when the species file is missing,
    matching the loaders' graceful behaviour."""
    lookup = _load_species_lookup()
    s = species.strip()
    if not lookup:
        return (s, "")
    if not s:
        return None
    if s.lower() in lookup:
        canon = lookup[s.lower()]
        return (canon, _synonym_extra(s, canon))
    # Parenthesized qualifiers: "Mandarin (Imperial)" is still a mandarin
    bare = re.sub(r'\s*\([^)]*\)', '', s).strip()
    if bare and bare.lower() in lookup:
        canon = lookup[bare.lower()]
        return (canon, _synonym_extra(bare, canon))
    tokens = (bare or s).split()
    lowered = [t.lower() for t in tokens]
    discard = _latin_noise_words() | SIZE_WORDS | _STATE_WORDS
    for n in range(min(len(tokens) - 1, 4), 0, -1):
        lead = ' '.join(lowered[:n])
        if lead not in lookup:
            continue
        rest = tokens[n:]
        rest_norm = [re.sub(r'[^a-z]', '', w.lower()) for w in rest]
        if any(wn in _NON_FRUIT_FORM_WORDS for wn in rest_norm if wn):
            return None
        canon = lookup[lead]
        # Restating the species in the species slot is noise, not cultivar
        # info: "Ooray Queensland Davidson's Plum" leaves just "Queensland".
        rest_str = ' '.join(rest)
        for phrase in sorted(
            [p for p, c in lookup.items() if c == canon] + [canon.lower()],
            key=len, reverse=True,
        ):
            rest_str = re.sub(rf'(?i)(?<![a-z]){re.escape(phrase)}(?![a-z])', ' ', rest_str)
        keep = [
            w for w in rest_str.split()
            if (wn := re.sub(r'[^a-z]', '', w.lower())) and wn not in discard
        ]
        lead_extra = _synonym_extra(' '.join(tokens[:n]), canon)
        leftover = ' '.join(([lead_extra] if lead_extra else []) + keep)
        return (canon, leftover)
    return None


def species_in_scope(species: str) -> bool:
    """True if a parsed species name belongs to the fruit taxonomy (DEC-195)."""
    return canonicalize_species(species) is not None


def cultivar_in_scope(species: str, slug: str = "", title: str = "") -> bool:
    """Boolean scope gate: grandfathered watched slugs always pass, titles
    naming an ornamental genus always fail, then the taxonomy decides."""
    if slug in GRANDFATHERED_VARIETY_SLUGS:
        return True
    if title and _ornamental_title(title):
        return False
    return species_in_scope(species)


def canonical_cultivar(species: str, variety: str, title: str = "") -> tuple[str, str, str] | None:
    """Scope-gate AND canonicalise one parsed cultivar: (canonical_species,
    variety, slug) or None when out of scope. This is THE grouping identity
    for /variety/ pages and variety alerts (DEC-196): respellings and synonym
    spellings of one species converge on one canonical name and one slug.
    Species-only listings ('Annona squamosa - Sugar apple') return None."""
    raw_slug = slugify(f"{species}-{variety}")
    if raw_slug in GRANDFATHERED_VARIETY_SLUGS:
        return (species, variety, raw_slug)
    if title and _ornamental_title(title):
        return None
    c = canonicalize_species(species)
    if c is None:
        return None
    canonical, leftover = c
    var = f"{leftover} {variety}".strip() if leftover else variety
    # Latin tails carry no cultivar info: "'Smooth' Davidsonia johnsonii" and
    # "Smooth" are the same selection and must share one slug.
    vt = var.split()
    while vt and re.sub(r'[^a-z]', '', vt[-1].lower()) in _latin_noise_words():
        vt.pop()
    if not vt:
        return None
    var = ' '.join(vt).strip('\'"‘’“” ')
    if not var:
        return None
    vl, cl = var.lower(), canonical.lower()
    # A "variety" that just restates the species is not a cultivar
    if vl == cl or _load_species_lookup().get(vl) == canonical:
        return None
    # Strip a trailing species restatement: 'Smooth Davidson's Plum' -> 'Smooth'
    if vl.endswith(' ' + cl):
        var = var[:-(len(cl) + 1)].strip()
        if not var:
            return None
    slug = slugify(f"{canonical}-{var}")
    return (canonical, var, slug) if slug else None


def product_variety_slug(title: str) -> str | None:
    """Parse + canonicalise + slugify in one step. Returns None when the title
    isn't a cultivar or is outside the fruit taxonomy (DEC-195)."""
    parsed = parse_cultivar(title)
    if not parsed:
        return None
    species, variety = parsed
    c = canonical_cultivar(species, variety, title)
    return c[2] if c else None


def _display_variety(variety: str) -> str:
    """Capitalize all-lowercase words for display, so a lowercase nursery title
    ("Semi Dwarf Apple granny smith") can't put "granny smith" in page H1s and
    headings when it happens to create the group first. Mixed-case and coded
    names (R2E2, J33, McIntosh, d'Agen) pass through untouched; slugs are
    lowercased separately and unaffected."""
    return ' '.join(
        w.capitalize() if w.isalpha() and w.islower() else w
        for w in variety.split()
    )


def group_by_cultivar(products: list[dict]) -> dict:
    """
    Group products by normalized cultivar name.
    Key: variety slug → normalized title and list of products.

    THE shared grouping for variety surfaces: build_variety_pages.py uses it
    to decide which /variety/<slug>.html pages exist, and build_species_pages.py
    uses the same output for the variety chip cloud, so a chip can never link
    to a page that was not generated.
    """
    groups = defaultdict(lambda: {"title": "", "species": "", "variety": "", "products": []})

    for p in products:
        parsed = parse_cultivar(p["title"])
        if not parsed:
            continue
        # Taxonomy gate + canonicalisation (DEC-195/196): out-of-scope products
        # get no page; respellings and synonym spellings of one species
        # ("Jakfruit", "Cumquat", "Davidson Plum") converge on one canonical
        # name and one slug.
        canon = canonical_cultivar(*parsed, p["title"])
        if canon is None:
            continue
        species, variety, key = canon
        if not groups[key]["title"]:
            # Use the cleaned parsed parts, not the raw first product title, so
            # the page H1/meta read "Black Sapote - Mossman" rather than the
            # messy "Black Sapote Mossman 5l" that happened to land first.
            variety_disp = _display_variety(variety)
            groups[key]["title"] = f"{species} - {variety_disp}"
            groups[key]["species"] = species
            groups[key]["variety"] = variety_disp
        groups[key]["products"].append(p)

    return groups


def extract_type_label(title: str) -> str:
    """Form / rootstock / propagation label(s) for a raw nursery title, for the
    per-row pill on variety pages (DEC-177).

    Returns a comma-joined, deduped, ordered label like "Super Dwarf, Bare rooted"
    (form, then propagation, then Advanced), or "" for a standard / grafted /
    plain listing. Uses _TYPE_LABELS -- the SAME patterns the post-parse cleaner
    strips with -- so a pill always names noise removed from the cultivar name,
    and the strip set and label set can never drift.
    """
    s = title
    labels: list[str] = []
    for rx, label in _TYPE_LABELS:
        if label in labels:
            continue
        if rx.search(s):
            labels.append(label)
            s = rx.sub(' ', s)   # consume so a shorter form (Dwarf) can't re-fire inside Super Dwarf
    return ', '.join(labels)
