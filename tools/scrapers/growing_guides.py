#!/usr/bin/env python3
"""
Per-species growing-guide content layer for treestock.com.au.

This is an additive editorial layer shared by the species+state combo pages
(build_species_state_pages.py) and the species pages (build_species_pages.py).
For a species that has a guide, it replaces the generic, uncited fruit_species.json
blurb with scannable, cited, WA/state-aware growing guidance.

Design (the key to making each state page genuinely unique and to scaling cheaply):

  * "core"  sections are state-INVARIANT (variety choice, planting, water, harvest,
    curing, buying). Researched once per species. Rendered on the species page and at
    the bottom of every combo page for that species.
  * "states.<ST>" overlays are state-SPECIFIC (climate fit, regions, harvest window,
    pests, shipping/quarantine). Researched per state. Rendered above the core on the
    matching combo page, so buy-olive-trees-western-australia.html and the QLD/NSW/VIC
    pages no longer share a byte-identical editorial body.

Content lives in declarative JSON, one file per species:
    tools/scrapers/growing_guides/<slug>.json   (see olive.json for the schema)

Graceful fallback: has_guide(slug) is False for any species without a JSON file, so
both builders keep their current behaviour for the ~180 un-enriched pages. Enrich a
new species (mango, etc.) by adding one JSON file, no code change.

The render/citation helpers deliberately mirror build_when_to_plant.py (inline_cite,
build_references, build_faq_jsonld) so the cited, FAQ-rich house style stays consistent.

No em dashes or en dashes anywhere (treestock copy rule); tests guard this.
"""

import json
from pathlib import Path

GUIDES_DIR = Path(__file__).parent / "growing_guides"

# Cache parsed guides for the life of the process (builders render many pages).
_CACHE: dict[str, dict | None] = {}


def _load(slug: str) -> dict | None:
    """Load and validate a guide for `slug`, or None if there is no usable guide."""
    if slug in _CACHE:
        return _CACHE[slug]
    path = GUIDES_DIR / f"{slug}.json"
    guide: dict | None = None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # A usable guide must at least carry a core section.
        if isinstance(data, dict) and isinstance(data.get("core"), dict):
            guide = data
    except (OSError, json.JSONDecodeError):
        guide = None
    _CACHE[slug] = guide
    return guide


def has_guide(slug: str) -> bool:
    """True when a usable growing guide exists for this species slug."""
    return _load(slug) is not None


def _sources_by_id(guide: dict) -> dict[str, dict]:
    return {s["id"]: s for s in guide.get("sources", []) if s.get("id")}


def inline_cite(label: str, url: str) -> str:
    """A small bracketed citation link. Mirrors build_when_to_plant.inline_cite."""
    safe = url.replace("&", "&amp;")
    return (f' <a href="{safe}" rel="noopener nofollow" target="_blank" '
            f'class="text-xs text-green-700 hover:underline whitespace-nowrap">[{label}]</a>')


def _cites_html(cite_ids: list, by_id: dict[str, dict], used: set | None = None) -> str:
    """Render inline citation links for a section, skipping unknown ids safely."""
    out = ""
    for cid in cite_ids or []:
        src = by_id.get(cid)
        if not src:
            continue
        if used is not None:
            used.add(cid)
        label = src.get("short") or src.get("name", "source")
        out += inline_cite(label, src.get("url", "#"))
    return out


def _render_block(block: dict, by_id: dict[str, dict], used: set | None = None) -> str:
    """Render an intro paragraph plus a list of subheaded, cited sections."""
    parts = []
    intro = block.get("intro")
    if intro:
        parts.append(f'<p class="text-sm text-gray-700 mb-4">{intro}</p>')
    for sec in block.get("sections", []):
        heading = sec.get("heading", "")
        body = sec.get("body", "")
        cites = _cites_html(sec.get("cites", []), by_id, used)
        parts.append(
            f'<h3 class="font-semibold text-gray-800 mt-4 mb-1">{heading}</h3>\n'
            f'<p class="text-sm text-gray-700">{body}{cites}</p>'
        )
    return "\n".join(parts)


def render_state_overlay(slug: str, state: str, used: set | None = None) -> str:
    """State-specific sections for `state`. Empty string if this guide has no overlay
    for that state (the combo page then shows only the shared core)."""
    guide = _load(slug)
    if not guide:
        return ""
    overlay = (guide.get("states") or {}).get(state)
    if not overlay:
        return ""
    return _render_block(overlay, _sources_by_id(guide), used)


def render_core(slug: str, used: set | None = None) -> str:
    """State-invariant core sections (variety choice, planting, water, harvest, buying)."""
    guide = _load(slug)
    if not guide:
        return ""
    return _render_block(guide["core"], _sources_by_id(guide), used)


def _faqs(slug: str, state: str | None) -> list[tuple[str, str]]:
    guide = _load(slug)
    if not guide:
        return []
    faqs = [(f["q"], f["a"]) for f in guide["core"].get("faqs", []) if f.get("q")]
    if state:
        overlay = (guide.get("states") or {}).get(state) or {}
        faqs += [(f["q"], f["a"]) for f in overlay.get("faqs", []) if f.get("q")]
    return faqs


def render_faq_section(slug: str, state: str | None = None) -> str:
    """Visible FAQ block (core FAQs plus the state's FAQs). Mirrors build_faq_section."""
    faqs = _faqs(slug, state)
    if not faqs:
        return ""
    items = "".join(
        f'  <div class="mb-4">\n'
        f'    <h3 class="font-semibold text-gray-800 mb-1">{q}</h3>\n'
        f'    <p class="text-sm text-gray-600">{a}</p>\n'
        f'  </div>\n'
        for q, a in faqs
    )
    return (
        '\n<section class="mb-8" id="faq">\n'
        '  <h2 class="text-lg font-semibold text-gray-800 mb-3">Frequently asked questions</h2>\n'
        f'{items}</section>\n'
    )


def faq_jsonld(slug: str, state: str | None = None) -> str:
    """FAQPage JSON-LD for render_head(extra_head=...). Mirrors build_faq_jsonld."""
    faqs = _faqs(slug, state)
    if not faqs:
        return ""
    data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faqs
        ],
    }
    return '<script type="application/ld+json">\n' + json.dumps(data, indent=2) + "\n</script>"


def _render_references(guide: dict, used_ids: set) -> str:
    """Sources block, limited to the sources actually cited by the rendered content."""
    by_id = _sources_by_id(guide)
    # Preserve the authoring order from sources[].
    cited = [s for s in guide.get("sources", []) if s.get("id") in used_ids]
    if not cited:
        return ""
    items = "".join(
        f'<li><a href="{s["url"].replace("&", "&amp;")}" rel="noopener nofollow" '
        f'target="_blank" class="text-green-700 hover:underline">{s["name"]}</a></li>'
        for s in cited
    )
    note = guide.get("sources_note") or (
        "Growing guidance on this page draws on Australian state agriculture "
        "departments, horticultural research, and industry sources."
    )
    return (
        '\n<section class="mb-8" id="sources">\n'
        '  <h2 class="text-lg font-semibold text-gray-800 mb-2">Sources</h2>\n'
        f'  <p class="text-gray-600 text-xs mb-2">{note}</p>\n'
        '  <ul class="text-xs space-y-1 list-disc pl-5">\n'
        f'    {items}\n'
        '  </ul>\n'
        '</section>\n'
    )


ARCHIVE_LINKS_FILE = GUIDES_DIR / "archive_links.json"
_ARCHIVE_CACHE: dict | None = None


def _archive_links() -> dict:
    """The generated per-species RFCA index (build_archive_index.py). slug -> [entries]."""
    global _ARCHIVE_CACHE
    if _ARCHIVE_CACHE is None:
        try:
            _ARCHIVE_CACHE = json.loads(ARCHIVE_LINKS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _ARCHIVE_CACHE = {}
    return _ARCHIVE_CACHE


def get_further_reading(slug: str, cap: int = 6) -> list:
    """Merge a guide's hand-curated further_reading with the generated RFCA archive
    index for this slug. Curated entries win and come first; deduped by URL; capped."""
    guide = _load(slug)
    curated = (guide.get("further_reading") if guide else None) or []
    out, seen = [], set()
    for e in list(curated) + list(_archive_links().get(slug, [])):
        url = e.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(e)
        if len(out) >= cap:
            break
    return out


def render_further_reading(slug: str) -> str:
    """"Further reading" cross-links: hand-curated first-party links from a species
    guide merged with the generated RFCA archive index. Owned-site links are followed
    (rel=noopener); set "nofollow": true on an entry for third-party sources (e.g.
    rarefruitclub.au, which Benedict does not host) so they are not endorsed."""
    items = get_further_reading(slug)
    if not items:
        return ""
    lis = ""
    for it in items:
        title = it.get("title", "")
        url = it.get("url", "").replace("&", "&amp;")
        source = it.get("source", "")
        rel = "noopener nofollow" if it.get("nofollow") else "noopener"
        src_html = f' <span class="text-gray-400">({source})</span>' if source else ""
        lis += (f'<li><a href="{url}" rel="{rel}" target="_blank" '
                f'class="text-green-700 hover:underline">{title}</a>{src_html}</li>')
    return (
        '\n<section class="mb-8" id="further-reading">\n'
        '  <h2 class="text-lg font-semibold text-gray-800 mb-2">Further reading</h2>\n'
        '  <p class="text-gray-600 text-xs mb-2">In-depth articles from the WANATCA and Rare Fruit '
        'Council of Australia archives.</p>\n'
        '  <ul class="text-sm space-y-1 list-disc pl-5">\n'
        f'    {lis}\n'
        '  </ul>\n'
        '</section>\n'
    )


def render_combo_guide(slug: str, state: str) -> str:
    """Full editorial block for a buy-<species>-trees-<state> page: the state overlay
    first (so the page leads with state specifics), then the shared core, then the
    combined FAQ and a Sources block limited to what was cited. The caller keeps its
    own <h2>Growing ... in <state></h2> heading above this."""
    guide = _load(slug)
    if not guide:
        return ""
    used: set = set()
    overlay = render_state_overlay(slug, state, used)
    core = render_core(slug, used)
    body = "\n".join(p for p in (overlay, core) if p)
    return (
        f'<div class="max-w-2xl">\n{body}\n</div>\n'
        f'{render_faq_section(slug, state)}'
        f'{_render_references(guide, used)}'
        f'{render_further_reading(slug)}'
    )


def render_species_guide(slug: str) -> str:
    """Editorial block for /species/<slug>.html: shared core only (no state overlay),
    its FAQ, and a Sources block limited to what the core cited."""
    guide = _load(slug)
    if not guide:
        return ""
    used: set = set()
    core = render_core(slug, used)
    return (
        f'<div class="prose prose-sm max-w-none">\n{core}\n</div>\n'
        f'{render_faq_section(slug)}'
        f'{_render_references(guide, used)}'
        f'{render_further_reading(slug)}'
    )
