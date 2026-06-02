#!/usr/bin/env python3
"""
Local generator for the per-species "Further reading" index used by the growing guides:
  tools/scrapers/growing_guides/archive_links.json   (slug -> [{title, url, source}])

It pulls first-party links from Benedict's OWNED horticultural archives. RFCA folders map
cleanly to one species (<rfca>/Next/Fruits/<Species>/*.htm, served at
https://rfcarchives.org.au/Next/Fruits/<Species>/<file>), so they are high precision and feed
the rendered index. WANATCA yearbook matches are keyword-based and lower precision (for example
"Chinese olives" is Canarium, not Olea), so they are printed as a CURATION AID only and added
to a species' guide further_reading by hand (citable as
https://wanatca.org.au/yearbooks/Y<vol>all.pdf).

The source sites live OUTSIDE this repo, so this runs LOCALLY (not in the server pipeline);
the JSON it writes is committed and deployed, and growing_guides.py reads it at build time.
Re-run it when the archives change.

Species are matched to treestock slugs using fruit_species.json (common names + synonyms)
plus a small ALIAS table for naming mismatches. Recipes (R_*) and image pages (*_Image)
are skipped. Output is sorted, deduped by URL, capped per species, and dash-free.

Usage:
    python3 build_archive_index.py [--rfca DIR] [--wanatca DIR] [--out FILE] [--cap N]
"""

import argparse
import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
SPECIES_FILE = SCRIPT_DIR / "fruit_species.json"
DEFAULT_OUT = SCRIPT_DIR / "growing_guides" / "archive_links.json"
# Sibling checkouts under the projects directory by default.
DEFAULT_RFCA = REPO_ROOT.parent / "rfcarchive.org.au"
DEFAULT_WANATCA = REPO_ROOT.parent / "wanatca-hugo"

# RFCA folder / WANATCA keyword spellings that do not match a treestock slug or synonym.
ALIAS = {
    "figs": "fig", "grapes": "grape", "jakfruit": "jackfruit", "litchi": "lychee",
    "carambola": "starfruit", "custardapple": "custard-apple", "blacksapote": "black-sapote",
    "fingerlime": "finger-lime", "dragonfruit": "dragon-fruit", "lillypilly": "lilly-pilly",
    "waxjambu": "wax-jambu", "kiwifruit": "kiwi", "mandarins": "mandarin", "oranges": "orange",
}

DASHES = {"—": "-", "–": "-"}


def no_dash(s: str) -> str:
    for d, r in DASHES.items():
        s = s.replace(d, r)
    return s


def clean(s: str) -> str:
    return no_dash(re.sub(r"\s+", " ", s).strip())


def norm(s: str) -> str:
    """Normalise a name for matching: lowercase, drop non-letters."""
    return re.sub(r"[^a-z]", "", s.lower())


def build_name_lookup() -> dict:
    """Map normalised species names/synonyms -> treestock slug."""
    lookup = {}
    species = json.loads(SPECIES_FILE.read_text())
    for s in species:
        slug = s.get("slug")
        if not slug:
            continue
        names = [s.get("common_name", ""), slug.replace("-", " ")] + (s.get("synonyms") or [])
        for n in names:
            if n:
                lookup[norm(n)] = slug
    lookup.update({norm(k): v for k, v in ALIAS.items()})
    return lookup, {s["slug"] for s in species if s.get("slug")}


def title_from_htm(path: Path) -> str:
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        return ""
    m = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
    title = m.group(1) if m else ""
    title = clean(re.sub(r"<[^>]+>", "", title))
    return title


def collect_rfca(rfca_dir: Path, lookup: dict) -> dict:
    """slug -> [entries] from <rfca>/Next/Fruits/<Folder>/*.htm."""
    out: dict[str, list] = {}
    fruits = rfca_dir / "Next" / "Fruits"
    if not fruits.is_dir():
        return out
    for folder in sorted(p for p in fruits.iterdir() if p.is_dir()):
        slug = lookup.get(norm(folder.name))
        if not slug:
            continue
        for htm in sorted(folder.glob("*.htm")):
            name = htm.name
            if name.endswith("_Image.htm") or name.startswith("R_"):
                continue  # skip image pages and recipes
            title = title_from_htm(htm)
            if not title or title.lower() in ("untitled", "index"):
                continue
            title = title.title() if title.isupper() else title
            url = f"https://rfcarchives.org.au/Next/Fruits/{folder.name}/{name}"
            out.setdefault(slug, []).append(
                {"title": title, "url": url, "source": "Rare Fruit Council archives"}
            )
    return out


YEAR_RE = re.compile(
    r"\)\s*(?P<title>.+?)\.\s*\*(?P<author>[^*]*)\*.*?Vol\s*(?P<vol>\d+).*?(?:KWs?:\s*(?P<kw>.*))?$"
)


def collect_wanatca(wanatca_dir: Path, lookup: dict) -> dict:
    """slug -> [entries] from the WANATCA YearbookIndex.md."""
    out: dict[str, list] = {}
    idx = wanatca_dir / "content" / "wanatca yearbook" / "YearbookIndex.md"
    if not idx.is_file():
        return out
    # word-boundary matcher per known name token (>=4 chars to avoid false hits)
    names = sorted((n for n in lookup if len(n) >= 4), key=len, reverse=True)
    for line in idx.read_text(errors="ignore").splitlines():
        m = YEAR_RE.search(line)
        if not m:
            continue
        title = clean(m.group("title"))
        author = clean(m.group("author") or "")
        vol = m.group("vol")
        hay = norm(title + " " + (m.group("kw") or ""))
        slug = next((lookup[n] for n in names if n in hay), None)
        if not slug:
            continue
        label = f"{title} ({author})" if author else title
        url = f"https://wanatca.org.au/yearbooks/Y{vol}all.pdf"
        out.setdefault(slug, []).append(
            {"title": clean(label), "url": url, "source": "WANATCA Yearbook"}
        )
    return out


def merge(*maps, cap: int) -> dict:
    out: dict[str, list] = {}
    for m in maps:
        for slug, entries in m.items():
            out.setdefault(slug, []).extend(entries)
    result = {}
    for slug in sorted(out):
        seen, kept = set(), []
        for e in out[slug]:
            if e["url"] in seen:
                continue
            seen.add(e["url"])
            kept.append(e)
        result[slug] = kept[:cap]
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rfca", default=str(DEFAULT_RFCA))
    ap.add_argument("--wanatca", default=str(DEFAULT_WANATCA))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--cap", type=int, default=8)
    args = ap.parse_args()

    lookup, _slugs = build_name_lookup()

    # RFCA folder matches are high precision, so they feed the rendered index.
    rfca = collect_rfca(Path(args.rfca), lookup)
    index = merge(rfca, cap=args.cap)
    Path(args.out).write_text(json.dumps(index, indent=2, ensure_ascii=True) + "\n")
    total = sum(len(v) for v in index.values())
    print(f"Wrote {args.out}: {len(index)} species, {total} RFCA links (rendered)")

    # WANATCA yearbook matches are keyword-based (lower precision), so they are NOT
    # auto-rendered. Printed here as a curation aid: add good ones to a guide by hand.
    wanatca = collect_wanatca(Path(args.wanatca), lookup)
    print(f"\nWANATCA yearbook candidates (curate by hand) for {len(wanatca)} species:")
    for slug in sorted(wanatca):
        titles = "; ".join(e["title"][:48] for e in wanatca[slug][:3])
        print(f"  {slug}: {titles}")


if __name__ == "__main__":
    main()
