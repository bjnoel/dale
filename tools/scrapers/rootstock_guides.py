#!/usr/bin/env python3
"""
Per-species ROOTSTOCK content layer for treestock.com.au (DAL-209).

An additive, static, cited editorial layer, deliberately modelled on the growing
guides (growing_guides.py) and variety descriptions (stocklib/variety_descriptions.py):
declarative JSON per species, a dumb renderer, no live scraping. Rootstock is sold
wholesale/seasonal/bare-root by phone and order form, so there is nothing to track
day to day; a maintained reference page is the right format, not a price tracker.

Content lives in one JSON file per species:
    tools/scrapers/rootstock_guides/<slug>.json   (see peach.json for the schema)

Each file carries:
  * intro          -- one paragraph framing rootstock choice for that species
  * rootstocks[]   -- the comparison-table rows: {name, type, vigour, soils, notes, cites}
  * grow_your_own  -- a block: {intro, sections:[{heading, body, cites}]}
  * faqs[]         -- {q, a} pairs, aggregated into the page-level FAQPage JSON-LD
  * sources[]      -- {id, name, short, url}; sections cite ids, https only

Graceful fallback: has_guide(slug) is False for any species without a JSON file, so
the hub builder simply skips it. Add a species by dropping in one JSON file.

The citation contract is the shared one: inline_cite from stocklib.citations (do NOT
fork it). No em dashes or en dashes anywhere (treestock copy rule); tests guard this.
"""

import json
from pathlib import Path

from stocklib.citations import inline_cite

GUIDES_DIR = Path(__file__).parent / "rootstock_guides"

# Cache parsed guides for the life of the process (the builder renders one page).
_CACHE: dict[str, dict | None] = {}


def _load(slug: str) -> dict | None:
    """Load and validate a rootstock guide for `slug`, or None if there is none usable."""
    if slug in _CACHE:
        return _CACHE[slug]
    path = GUIDES_DIR / f"{slug}.json"
    guide: dict | None = None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # A usable guide must carry at least one rootstock row.
        if isinstance(data, dict) and isinstance(data.get("rootstocks"), list) and data["rootstocks"]:
            guide = data
    except (OSError, json.JSONDecodeError):
        guide = None
    _CACHE[slug] = guide
    return guide


def has_guide(slug: str) -> bool:
    """True when a usable rootstock guide exists for this species slug."""
    return _load(slug) is not None


def common_name(slug: str) -> str:
    guide = _load(slug)
    return guide.get("common_name", slug.title()) if guide else slug.title()


def _sources_by_id(guide: dict) -> dict[str, dict]:
    return {s["id"]: s for s in guide.get("sources", []) if s.get("id")}


def _cites_html(cite_ids: list, by_id: dict[str, dict], used: set | None = None) -> str:
    """Inline citation links for a row or section, skipping unknown ids safely."""
    out = ""
    for cid in cite_ids or []:
        src = by_id.get(cid)
        if not src:
            continue
        if used is not None:
            used.add(cid)
        out += inline_cite(src.get("short") or src.get("name", "source"), src.get("url", "#"))
    return out


def _render_table(guide: dict, by_id: dict[str, dict], used: set) -> str:
    """The per-species rootstock comparison table."""
    rows = ""
    for r in guide["rootstocks"]:
        sub = (f'<div class="text-xs text-gray-400 font-normal">{r["type"]}</div>'
               if r.get("type") else "")
        cites = _cites_html(r.get("cites", []), by_id, used)
        rows += (
            '<tr class="border-b border-gray-100 align-top">'
            f'<td class="py-2.5 pl-3 pr-4 text-sm font-medium text-gray-800 whitespace-nowrap">{r["name"]}{sub}</td>'
            f'<td class="py-2.5 px-3 text-sm text-gray-600">{r.get("vigour", "")}</td>'
            f'<td class="py-2.5 px-3 text-sm text-gray-600">{r.get("soils", "")}</td>'
            f'<td class="py-2.5 px-3 text-sm text-gray-600">{r.get("notes", "")}{cites}</td>'
            '</tr>'
        )
    return f"""
  <div class="overflow-x-auto rounded-lg border border-gray-200 mb-4">
    <table class="w-full bg-white text-left">
      <thead class="bg-gray-50 border-b border-gray-200">
        <tr>
          <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Rootstock</th>
          <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Vigour / tree size</th>
          <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Soil and use</th>
          <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Notes</th>
        </tr>
      </thead>
      <tbody>{rows}
      </tbody>
    </table>
  </div>"""


def _render_block(block: dict, by_id: dict[str, dict], used: set) -> str:
    """Intro paragraph plus subheaded, cited sections (grow-your-own)."""
    parts = []
    if block.get("intro"):
        parts.append(f'<p class="text-sm text-gray-700 mb-4">{block["intro"]}</p>')
    for sec in block.get("sections", []):
        cites = _cites_html(sec.get("cites", []), by_id, used)
        parts.append(
            f'<h4 class="font-semibold text-gray-800 mt-4 mb-1">{sec.get("heading", "")}</h4>\n'
            f'<p class="text-sm text-gray-700">{sec.get("body", "")}{cites}</p>'
        )
    return "\n".join(parts)


def _render_sources_details(guide: dict, used: set) -> str:
    """Collapsible per-species Sources list, limited to sources actually cited."""
    cited = [s for s in guide.get("sources", []) if s.get("id") in used]
    if not cited:
        return ""
    items = "".join(
        f'<li><a href="{s["url"].replace("&", "&amp;")}" target="_blank" rel="noopener nofollow" '
        f'class="text-green-700 hover:underline">{s["name"]}</a></li>'
        for s in cited
    )
    return (
        '<details class="mt-2 text-xs text-gray-500">'
        '<summary class="cursor-pointer hover:text-gray-700">Sources for this section</summary>'
        f'<ul class="list-disc pl-5 mt-1 space-y-0.5">{items}</ul></details>'
    )


def render_species_section(slug: str) -> str:
    """The full block for one species: heading, intro, rootstock table, grow-your-own,
    and a collapsible Sources list limited to what this section cited."""
    guide = _load(slug)
    if not guide:
        return ""
    by_id = _sources_by_id(guide)
    used: set = set()
    name = guide.get("common_name", slug.title())

    table = _render_table(guide, by_id, used)
    gyo = ""
    if guide.get("grow_your_own"):
        gyo = (
            f'\n  <h3 class="text-lg font-semibold text-gray-800 mt-6 mb-2">Grow your own {name.lower()} rootstock</h3>\n'
            f'  {_render_block(guide["grow_your_own"], by_id, used)}'
        )
    intro = f'<p class="text-sm text-gray-600 mb-4">{guide["intro"]}</p>' if guide.get("intro") else ""
    sources = _render_sources_details(guide, used)

    return f"""
<section class="mb-10" id="{slug}">
  <h2 class="text-xl font-bold text-green-900 mb-3">{name} rootstock</h2>
  {intro}
  {table}{gyo}
  {sources}
</section>
"""


def get_faqs(slug: str) -> list[tuple[str, str]]:
    """FAQ (q, a) pairs for this species, for the page-level FAQ block and JSON-LD."""
    guide = _load(slug)
    if not guide:
        return []
    return [(f["q"], f["a"]) for f in guide.get("faqs", []) if f.get("q")]
