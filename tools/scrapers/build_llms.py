#!/usr/bin/env python3
"""
Build /llms.txt for treestock.com.au.

llms.txt (https://llmstxt.org) is a concise, Markdown map of the site's most
useful pages for LLMs and AI answer engines. We list the curated guides, the
browse/section hubs, and the per-species pages (each a substantial growing +
availability guide), kept in sync with fruit_species.json. Sitemap.xml remains
the exhaustive list; this is the curated "start here" map.

Usage:
    python3 build_llms.py [output_dir]   # default /opt/dale/dashboard
"""

import json
import sys
from pathlib import Path

from treestock_layout import SITE_URL, SITE_NAME

FRUIT_SPECIES = Path(__file__).parent / "fruit_species.json"
DEFAULT_OUTPUT_DIR = Path("/opt/dale/dashboard")

SUMMARY = (
    "treestock.com.au tracks fruit and rare plant stock, prices, and availability "
    "across Australian nurseries, updated daily. It aggregates many nurseries so "
    "collectors can find where a species or named variety is in stock and compare "
    "prices."
)

GUIDES = [
    ("/when-to-plant.html", "When to Plant Fruit Trees in Australia",
     "Planting calendar across five climate zones: bare-root season, chill hours, frost guidance."),
    ("/companion-planting-guide.html", "Companion Planting Guide for Fruit Trees",
     "Evidence-graded companion and avoidance pairings for fruit trees."),
    ("/buy-fruit-trees-wa.html", "Buy Fruit Trees by State",
     "State guides with quarantine and shipping notes (WA, QLD, NSW, VIC)."),
]

BROWSE = [
    ("/species/", "All species", "Per-species availability, prices, and growing guides."),
    ("/variety/", "Named varieties", "Cultivar-level pages (e.g. Hass avocado, R2E2 mango, Brown Turkey fig)."),
    ("/nursery/", "Nurseries", "Per-nursery stock, prices, and shipping restrictions."),
    ("/compare/", "Price comparisons", "Cheapest nursery per species, compared at the variant level."),
    ("/rare.html", "Rare and exotic in stock", "Hard-to-find species currently available somewhere in Australia."),
]


def build_llms_txt(species: list) -> str:
    species_sorted = sorted(species, key=lambda s: s["common_name"])
    lines = [f"# {SITE_NAME}", "", f"> {SUMMARY}", "", "## Guides"]
    for path, name, desc in GUIDES:
        lines.append(f"- [{name}]({SITE_URL}{path}): {desc}")
    lines += ["", "## Browse"]
    for path, name, desc in BROWSE:
        lines.append(f"- [{name}]({SITE_URL}{path}): {desc}")
    lines += ["", "## Species guides"]
    for s in species_sorted:
        name = s["common_name"]
        lines.append(
            f"- [{name} trees in Australia]({SITE_URL}/species/{s['slug']}.html): "
            f"Where to buy {name}, current prices, and a per-state growing guide."
        )
    lines.append("")
    return "\n".join(lines)


def build(output_dir=DEFAULT_OUTPUT_DIR):
    species = json.loads(FRUIT_SPECIES.read_text())
    text = build_llms_txt(species)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "llms.txt"
    path.write_text(text, encoding="utf-8")
    print(f"Built {path} ({len(species)} species)")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUTPUT_DIR
    build(target)
