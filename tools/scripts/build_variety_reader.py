#!/usr/bin/env python3
"""Compile all variety description articles into one readable HTML file.

Reads the committed per-species JSON files in tools/scrapers/variety_descriptions/
and emits a single self-contained HTML page organised by species, for offline
reading. This is a personal reader for Benedict, not a treestock page; it does
not touch the site builders or templates.

Usage:
    python3 tools/scripts/build_variety_reader.py [output.html]

Default output: docs/variety-articles.html
"""

import html
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DESCRIPTIONS_DIR = REPO_ROOT / "tools" / "scrapers" / "variety_descriptions"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "variety-articles.html"

CSS = """
:root {
  --ink: #2b2620;
  --muted: #7a6f60;
  --accent: #3f6f3f;
  --paper: #faf7f1;
  --card: #ffffff;
  --rule: #e4dccd;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: Georgia, 'Times New Roman', serif;
  line-height: 1.65;
}
.wrap { max-width: 46rem; margin: 0 auto; padding: 2rem 1.25rem 5rem; }
header.masthead { text-align: center; border-bottom: 3px double var(--rule); padding-bottom: 1.5rem; margin-bottom: 2rem; }
header.masthead h1 { font-size: 2.1rem; margin: 0 0 0.4rem; letter-spacing: 0.02em; }
header.masthead p { color: var(--muted); margin: 0.2rem 0; font-style: italic; }
nav.toc { background: var(--card); border: 1px solid var(--rule); border-radius: 8px; padding: 1.25rem 1.5rem; margin-bottom: 3rem; }
nav.toc h2 { margin: 0 0 0.75rem; font-size: 1.1rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }
nav.toc ul { list-style: none; margin: 0; padding: 0; columns: 2; column-gap: 2rem; }
@media (max-width: 540px) { nav.toc ul { columns: 1; } }
nav.toc li { margin: 0.15rem 0; break-inside: avoid; }
nav.toc a { color: var(--accent); text-decoration: none; }
nav.toc a:hover { text-decoration: underline; }
nav.toc .count { color: var(--muted); font-size: 0.85em; }
section.species { margin-bottom: 3.5rem; }
section.species > h2 {
  font-size: 1.7rem;
  border-bottom: 2px solid var(--rule);
  padding-bottom: 0.3rem;
  margin: 0 0 0.25rem;
}
section.species > .species-meta { color: var(--muted); font-size: 0.9rem; margin: 0 0 1.5rem; }
article.variety { margin-bottom: 2.25rem; }
article.variety h3 { font-size: 1.25rem; margin: 0 0 0.5rem; color: var(--accent); }
article.variety p { margin: 0 0 0.8rem; }
details.sources { font-size: 0.85rem; color: var(--muted); }
details.sources summary { cursor: pointer; user-select: none; }
details.sources ul { margin: 0.4rem 0 0; padding-left: 1.3rem; }
details.sources a { color: var(--muted); }
.backtop { font-size: 0.8rem; }
.backtop a { color: var(--muted); text-decoration: none; }
.backtop a:hover { text-decoration: underline; }
footer.colophon { text-align: center; color: var(--muted); font-size: 0.85rem; border-top: 3px double var(--rule); padding-top: 1.5rem; }
"""


def load_species():
    """Return [(display_name, slug, [variety, ...])], species and varieties sorted by name."""
    out = []
    for path in sorted(DESCRIPTIONS_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        varieties = list(data.get("varieties", {}).values())
        if not varieties:
            continue
        varieties.sort(key=lambda v: v.get("variety", "").lower())
        display = varieties[0].get("species") or path.stem.replace("-", " ").title()
        out.append((display, data.get("species_slug", path.stem), varieties))
    out.sort(key=lambda t: t[0].lower())
    return out


def render_variety(v):
    name = html.escape(v.get("variety") or v.get("slug", "Unknown"))
    anchor = html.escape(v.get("slug", ""))
    parts = [f'<article class="variety" id="{anchor}">', f"<h3>{name}</h3>"]
    for para in v.get("paragraphs", []):
        parts.append(f"<p>{html.escape(para)}</p>")
    sources = v.get("sources", [])
    if sources:
        n = len(sources)
        label = "1 source" if n == 1 else f"{n} sources"
        items = []
        for s in sources:
            sname = html.escape(s.get("name", s.get("id", "source")))
            url = s.get("url", "")
            if url:
                items.append(
                    f'<li><a href="{html.escape(url, quote=True)}" rel="noopener">{sname}</a></li>'
                )
            else:
                items.append(f"<li>{sname}</li>")
        parts.append(
            f'<details class="sources"><summary>{label}</summary><ul>'
            + "".join(items)
            + "</ul></details>"
        )
    parts.append("</article>")
    return "\n".join(parts)


def build(species_list):
    total = sum(len(vs) for _, _, vs in species_list)
    today = date.today().isoformat()

    toc_items = []
    sections = []
    for display, slug, varieties in species_list:
        esc_display = html.escape(display)
        esc_slug = html.escape(slug)
        toc_items.append(
            f'<li><a href="#species-{esc_slug}">{esc_display}</a> '
            f'<span class="count">({len(varieties)})</span></li>'
        )
        articles = "\n".join(render_variety(v) for v in varieties)
        plural = "variety" if len(varieties) == 1 else "varieties"
        sections.append(
            f'<section class="species" id="species-{esc_slug}">\n'
            f"<h2>{esc_display}</h2>\n"
            f'<p class="species-meta">{len(varieties)} {plural} '
            f'<span class="backtop"><a href="#top">(back to top)</a></span></p>\n'
            f"{articles}\n</section>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Fruit Tree Variety Articles</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap" id="top">
<header class="masthead">
<h1>Fruit Tree Variety Articles</h1>
<p>{total} varieties across {len(species_list)} species</p>
<p>Compiled {today} from the treestock variety descriptions</p>
</header>
<nav class="toc">
<h2>Species</h2>
<ul>
{chr(10).join(toc_items)}
</ul>
</nav>
{chr(10).join(sections)}
<footer class="colophon">
<p>Generated by tools/scripts/build_variety_reader.py. Every claim in these articles is backed by the cited sources in the per-species JSON files.</p>
</footer>
</div>
</body>
</html>
"""


def main():
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    species_list = load_species()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build(species_list))
    total = sum(len(vs) for _, _, vs in species_list)
    print(f"Wrote {output} ({total} varieties, {len(species_list)} species)")


if __name__ == "__main__":
    main()
