#!/usr/bin/env python3
"""
Per-variety description content layer for treestock.com.au.

Additive editorial layer for the cultivar/variety pages (build_variety_pages.py). For a
variety that has a verified description, it renders a short, multi-source-checked blurb
("what is unique about this variety") directly under the page meta line and above the
price table. Mirrors the growing_guides.py design: declarative committed JSON, one file
per species, a dumb cached renderer, graceful fallback (no blurb) for the long tail.

Content lives in declarative JSON, one file per species:
    tools/scrapers/variety_descriptions/<species-slug>.json   (see tests for the schema)

Each variety entry carries plain-text `paragraphs` (1-2 short paragraphs, no inline
citations), a `claims` ledger binding each fact to the `sources` that corroborate it,
plus `confidence`/`verified`. Sources and per-claim verification are kept for audit, not
rendered (the on-page blurb stays clean prose, per the design decision).

Generation is a SEPARATE dev-time step: each variety is researched and cross-checked by
hand against multiple reputable sources, then committed. This module NEVER calls an LLM
or the network; the nightly build only reads committed JSON. A wrong fact can only ship
if it survives research, the >=2-source gate, AND human review of the commit.

Graceful fallback: has_description() is False for any variety without a usable entry, so
build_variety_pages.py keeps its current output for the un-enriched pages. Enrich a
variety by adding one JSON entry, no code change.

No em dashes or en dashes anywhere (treestock copy rule); tests guard this.
"""

import json
from pathlib import Path

# This module lives in tools/scrapers/stocklib/, the content lives one level up in
# tools/scrapers/variety_descriptions/ (alongside growing_guides/, deployed by rsync).
DESCRIPTIONS_DIR = Path(__file__).parent.parent / "variety_descriptions"

# Defensive render-time bar. tests/test_variety_descriptions.py enforces the full
# committed bar (>=2 sources, confidence_score, an authoritative source, cites resolve,
# no dashes, slug matches a real variety); this is just enough to refuse to render a
# blurb that was hand-edited into a clearly unusable state.
VALID_CONFIDENCE = {"high", "medium"}
MIN_SOURCES = 2

# Cache parsed, validated files for the life of the process (the builder renders
# thousands of variety pages, so we parse each species file at most once).
_CACHE: dict[str, dict] = {}


def _is_usable(entry: object) -> bool:
    """True when an entry is structurally complete enough to render safely."""
    if not isinstance(entry, dict):
        return False
    if entry.get("verified") is not True:
        return False
    if entry.get("confidence") not in VALID_CONFIDENCE:
        return False
    paras = entry.get("paragraphs")
    if not isinstance(paras, list) or not any(
        isinstance(p, str) and p.strip() for p in paras
    ):
        return False
    sources = entry.get("sources")
    if not isinstance(sources, list) or len(sources) < MIN_SOURCES:
        return False
    return True


def _load_species(species_slug: str) -> dict:
    """{variety_slug: entry} of usable entries for a species; {} if missing/malformed.

    Cached. Malformed files and unusable entries are dropped silently so a bad hand-edit
    degrades to "no blurb" rather than a broken page (tests catch bad commits instead)."""
    if species_slug in _CACHE:
        return _CACHE[species_slug]
    path = DESCRIPTIONS_DIR / f"{species_slug}.json"
    usable: dict[str, dict] = {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        varieties = data.get("varieties", {}) if isinstance(data, dict) else {}
        if isinstance(varieties, dict):
            for vslug, entry in varieties.items():
                if _is_usable(entry):
                    usable[vslug] = entry
    except (OSError, json.JSONDecodeError):
        usable = {}
    _CACHE[species_slug] = usable
    return usable


def has_description(variety_slug: str, species_slug: str) -> bool:
    """True when a usable variety description exists for this variety slug."""
    return variety_slug in _load_species(species_slug)


def render_blurb(variety_slug: str, species_slug: str) -> str:
    """The variety blurb HTML fragment, or "" when there is no usable entry.

    Renders the stored plain-text paragraphs with the same body-paragraph styling the
    species pages use (build_species_description), so it sits cleanly above the price
    table. Returns "" for an un-enriched variety, so the template slot renders nothing."""
    entry = _load_species(species_slug).get(variety_slug)
    if not entry:
        return ""
    paras = [p.strip() for p in entry.get("paragraphs", []) if isinstance(p, str) and p.strip()]
    if not paras:
        return ""
    body = "\n".join(
        f'    <p class="text-gray-700 text-sm leading-relaxed mb-3">{p}</p>' for p in paras
    )
    return f'  <div class="mb-6" id="variety-about">\n{body}\n  </div>\n'
