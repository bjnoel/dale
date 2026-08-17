#!/usr/bin/env python3
"""Propose redirects for the /variety/ URLs a cultivar parser change deleted.

    python3 recover_merged_slugs.py <data_dir> --on 2026-08-16 \
        [--old-rev 75df8b7] [--repo /opt/dale/repo] [--out proposals.json]

Task R1 of docs/page-lifecycle-plan.md. The 2026-08-16 parser merge folded
duplicate slugs onto one cultivar, which is the right answer for the catalogue
and the wrong answer for the URLs: the night after it deployed, the variety
build went from 2,717 pages to 2,570 and the difference 404s. Those are renames,
and a rename's correct artifact is a redirect, which passes authority to the
successor. A tombstone is a dead end and would throw that away.

Both ends of the mapping are derived rather than reconstructed, which is what
makes this worth doing properly:

  old slug   the PRE-merge parser AND that revision's species taxonomy, run
             over the dated snapshot the pre-merge nightly actually read. Not
             "what we think used to be there".
  new slug   the CURRENT parser, run over the SAME titles. Holding the input
             fixed is what isolates the parser change from overnight stock
             churn, which moves slugs for entirely unrelated reasons.

Pinning the taxonomy as well as the parser is not belt-and-braces. The first
run of this tool did not, and reported 2,725 slugs against the 2,717 in
scraper.log: `fruit_species.json` had been fixed later that morning to stop
filing canistel and mamey sapote under white sapote, and the old parser reading
today's species file reconstructed a night that never ran. Those 8 slugs were
never URLs. Proposing redirects for them would have been the same class of
mistake as seeding a page into existence at an address nobody ever linked.

Both ends are driven through `group_by_cultivar`, the same grouping the builder
uses to decide which pages exist, so the reconstructed slug set is comparable to
the count in scraper.log rather than merely similar to it. `--expect-old` asserts
that reconciliation and is the reason to trust anything below it.

This writes a PROPOSAL and applies nothing. A rename that names the wrong
successor is a permanent lie to a crawler, and prefix similarity is exactly the
signal that must not be trusted automatically: avocado-hass-lamb is Lamb Hass,
a different cultivar. Approval is a human's, via /admin/varieties.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from stocklib import taxonomy  # noqa: E402
from stocklib.classify import is_real_product  # noqa: E402
from stocklib.snapshots import iter_nursery_snapshots  # noqa: E402

PARSER_PATH = "tools/scrapers/cultivar_parsing.py"
SPECIES_PATH = "tools/scrapers/fruit_species.json"

# The commit immediately before "fix: one cultivar, one slug (parser)". Named
# rather than derived: which change to undo is a judgement, and a script that
# guesses it would silently propose a different mapping after the next parser
# edit.
DEFAULT_OLD_REV = "75df8b7"

# Below this share of a dead slug's titles, the majority target is not a
# majority worth acting on and the whole group goes to review.
DOMINANT_SHARE = 0.8


def find_repo(start: Path | None = None) -> Path | None:
    """The git checkout to read the old parser out of.

    Deliberately not the directory this script runs from: on the server that is
    /opt/dale/scrapers, a deployed copy with no .git, while the repo sits at
    /opt/dale/repo.
    """
    for candidate in [start, Path(__file__).resolve().parent, Path("/opt/dale/repo")]:
        if candidate is None:
            continue
        probe = subprocess.run(
            ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True)
        if probe.returncode == 0:
            return Path(probe.stdout.strip())
    return None


def write_revision(repo: Path, rev: str, repo_path: str, dest: Path) -> Path:
    """A tracked file as it stood at `rev`, on disk at `dest`."""
    blob = subprocess.run(
        ["git", "-C", str(repo), "show", f"{rev}:{repo_path}"],
        capture_output=True, text=True)
    if blob.returncode != 0:
        raise SystemExit(f"cannot read {repo_path} at {rev}: {blob.stderr.strip()}")
    dest.write_text(blob.stdout)
    return dest


def load_parser_revision(repo: Path, rev: str, workdir: Path):
    """Import cultivar_parsing.py as it stood at `rev`, alongside the current one.

    Under a distinct module name, so both parsers live in sys.modules at once and
    neither shadows the other. The old file still does `from stocklib import
    taxonomy`, so which species data it sees is decided by `pinned_taxonomy`
    rather than by the import.
    """
    name = "cultivar_parsing_premerge"
    path = write_revision(repo, rev, PARSER_PATH, workdir / f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def pinned_taxonomy(species_file: Path, modules):
    """Point the shared taxonomy at `species_file` for the duration.

    The parser reads species data through stocklib.taxonomy, which both parser
    revisions import as the same live module, so an old parser left alone reads
    TODAY's species file. That combination never ran, and it is not a small
    difference: one synonym fix in fruit_species.json moved 8 slugs.

    `modules` are the parser modules to reset around the swap. They memoise
    everything species-derived on first use, so a pin applied after the cache is
    warm changes nothing at all, and silently.
    """
    was = taxonomy.SPECIES_FILE
    taxonomy.SPECIES_FILE = Path(species_file)
    for module in modules:
        module._clear_species_caches()
    try:
        yield
    finally:
        taxonomy.SPECIES_FILE = was
        for module in modules:
            module._clear_species_caches()


def load_titles(data_dir: Path, on_date: str) -> list[dict]:
    """The product titles that were live on `on_date`, as the builder saw them.

    Same walk and same non-plant filter as build_variety_pages.load_all_products,
    against that date's snapshot rather than tonight's. Only the title matters
    here; group_by_cultivar reads nothing else.
    """
    products = []
    for _, data in iter_nursery_snapshots(data_dir, on_date):
        for p in data.get("products", []):
            title = (p.get("title") or "").strip()
            if title and is_real_product(title):
                products.append({"title": title})
    return products


def slug_for_title(module, title: str) -> str | None:
    """A parser module's answer for one title, or None if it maps to no page.

    The composition build_variety_pages.slug_for_title uses, applied to whichever
    parser was passed, so old and new are asked exactly the same question.
    """
    parsed = module.parse_cultivar(title)
    if not parsed:
        return None
    canon = module.canonical_cultivar(*parsed, title)
    return canon[2] if canon else None


def classify(titles: list[str], new_slug_for) -> dict:
    """What became of one dead slug's products under the current parser.

    rename   every mapped title agrees on one successor. The only verdict that
             can become a redirect without someone reading it.
    retired  nothing maps anywhere: the taxonomy gate or a deny took it. No
             successor exists, so a redirect would be a lie and a tombstone is
             the honest artifact.
    split    the products went to more than one successor. Naming one of them
             would silently discard the others, so a human picks.
    """
    targets = Counter()
    unmapped = 0
    for title in titles:
        slug = new_slug_for(title)
        if slug is None:
            unmapped += 1
        else:
            targets[slug] += 1

    mapped = sum(targets.values())
    if not mapped:
        return {"verdict": "retired", "target": None, "targets": {},
                "unmapped_titles": unmapped}
    if len(targets) == 1:
        target = next(iter(targets))
        return {"verdict": "rename", "target": target, "targets": dict(targets),
                "unmapped_titles": unmapped}

    target, count = targets.most_common(1)[0]
    return {"verdict": "split",
            "target": None,
            "suggested": target if count / mapped >= DOMINANT_SHARE else None,
            "targets": dict(targets),
            "unmapped_titles": unmapped}


def watch_counts(db_path: Path) -> dict[str, int]:
    """Watchers per slug, so a dead URL someone subscribed to is never silent.

    A watch on a slug is a person waiting for an email about it. Missing or
    unreadable DB returns empty rather than failing: this is evidence attached
    to a proposal, not a precondition for computing one.
    """
    if not Path(db_path).exists():
        return {}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT variety_slug, COUNT(*) FROM watches GROUP BY variety_slug"
            ).fetchall()
    except sqlite3.Error:
        return {}
    return {slug: n for slug, n in rows if slug}


def build_proposals(old_groups: dict, new_groups: dict, live_slugs: set[str],
                    new_slug_for, watchers: dict[str, int]) -> list[dict]:
    """One proposal per slug the parser change stopped generating.

    `live_slugs` is today's canonical index: a slug still in it is still a page,
    whatever the old parser thought, and proposing anything for it would be
    proposing to redirect a live URL onto itself.
    """
    proposals = []
    for slug in sorted(set(old_groups) - set(new_groups) - live_slugs):
        group = old_groups[slug]
        titles = [p["title"] for p in group["products"]]
        record = classify(titles, new_slug_for)
        target = record.get("target")
        proposals.append({
            "slug": slug,
            "title": group.get("title") or slug,
            # Carried so a seeded entry can render as something other than a
            # stub later. A stub needs only the title, but converting one to a
            # tombstone (a real decision a reviewer may make) needs the species
            # to draw a breadcrumb and offer siblings, and there is nowhere else
            # to recover it from once the old parser is gone.
            "species": group.get("species") or "",
            "variety": group.get("variety") or "",
            "verdict": record["verdict"],
            "target": target,
            "suggested": record.get("suggested"),
            # A redirect onto a slug that is not itself a page today would swap
            # a 404 for a 404 and spend the authority doing it.
            "target_live": bool(target) and target in live_slugs,
            "targets": record["targets"],
            "unmapped_titles": record["unmapped_titles"],
            "product_count": len(titles),
            "sample_titles": sorted(set(titles))[:5],
            "watchers": watchers.get(slug, 0),
            "target_title": (new_groups.get(target) or {}).get("title") if target else None,
        })
    return proposals


def summarise(proposals: list[dict]) -> dict:
    counts = Counter(p["verdict"] for p in proposals)
    ready = [p for p in proposals if p["verdict"] == "rename" and p["target_live"]]
    return {
        "total": len(proposals),
        "rename": counts["rename"],
        "retired": counts["retired"],
        "split": counts["split"],
        "ready_to_apply": len(ready),
        "watched": sum(1 for p in proposals if p["watchers"]),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_dir", type=Path, help="nursery-stock directory")
    ap.add_argument("--on", required=True, metavar="YYYY-MM-DD",
                    help="snapshot date to run both parsers over: the last day "
                         "the old slugs were still being generated")
    ap.add_argument("--old-rev", default=DEFAULT_OLD_REV,
                    help=f"commit holding the pre-merge parser (default {DEFAULT_OLD_REV})")
    ap.add_argument("--repo", type=Path, default=None,
                    help="git checkout to read the old parser from")
    ap.add_argument("--index", type=Path, default=Path("/opt/dale/data/variety-index.json"),
                    help="today's canonical variety index: what is still a page")
    ap.add_argument("--watches", type=Path,
                    default=Path("/opt/dale/data/variety_watches.db"))
    ap.add_argument("--out", type=Path, default=None,
                    help="write the proposal file here (default: stdout summary only)")
    # Two separate reconciliations, because they are claims about two different
    # nights. --expect-old is the count scraper.log recorded on --on, the night
    # the old parser last ran; matching it is what says this reconstruction is
    # the night that happened. --expect-new only means anything when --on is
    # also a date the current parser ran, which is not the usual case.
    ap.add_argument("--expect-old", type=int, default=None, metavar="N",
                    help="distinct cultivars scraper.log recorded on --on. "
                         "Exits non-zero on a mismatch")
    ap.add_argument("--expect-new", type=int, default=None, metavar="N",
                    help="distinct cultivars the CURRENT parser should find on "
                         "--on, if it ever ran against that date")
    args = ap.parse_args()

    repo = find_repo(args.repo)
    if repo is None:
        print("no git checkout found; pass --repo")
        return 2

    live_slugs: set[str] = set()
    if args.index.exists():
        loaded = json.loads(args.index.read_text())
        if isinstance(loaded, dict):
            live_slugs = set(loaded)
    print(f"Today's index: {len(live_slugs)} live variety slugs")

    products = load_titles(args.data_dir, args.on)
    print(f"Snapshot {args.on}: {len(products)} products")
    if not products:
        print(f"no snapshots for {args.on}; nothing to compare")
        return 2

    import cultivar_parsing as new_parser
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        old_parser = load_parser_revision(repo, args.old_rev, workdir)
        species = write_revision(repo, args.old_rev, SPECIES_PATH,
                                 workdir / "fruit_species_pinned.json")
        # Old parser and old species data together, which is the pair that ran.
        with pinned_taxonomy(species, (old_parser, new_parser)):
            old_groups = old_parser.group_by_cultivar(products)
        new_groups = new_parser.group_by_cultivar(products)

        print(f"Pre-merge parser ({args.old_rev}): {len(old_groups)} distinct cultivars")
        print(f"Current parser, same input: {len(new_groups)} distinct cultivars")
        print(f"Merge effect on a fixed input: {len(old_groups) - len(new_groups):+d}")

        for label, got, want in (("pre-merge", len(old_groups), args.expect_old),
                                 ("current", len(new_groups), args.expect_new)):
            if want is None:
                continue
            ok = got == want
            print(f"Reconcile {label} parser against scraper.log: "
                  f"expected {want}, got {got} -- {'MATCH' if ok else 'MISMATCH'}")
            if not ok:
                print("This reconstruction is not the night that ran, so the "
                      "mapping below is not evidence. Do not seed it.")
                return 1

        proposals = build_proposals(
            old_groups, new_groups, live_slugs,
            lambda t: slug_for_title(new_parser, t),
            watch_counts(args.watches))

    summary = summarise(proposals)
    print(f"\n{summary['total']} slug(s) stopped being generated:")
    print(f"  rename  {summary['rename']:>4}  ({summary['ready_to_apply']} onto a live page)")
    print(f"  split   {summary['split']:>4}  need a human to pick a successor")
    print(f"  retired {summary['retired']:>4}  no successor exists")
    if summary["watched"]:
        print(f"  {summary['watched']} of them have a live watcher")

    if args.out:
        args.out.write_text(json.dumps({
            "generated_for": args.on,
            "old_rev": args.old_rev,
            "old_cultivars": len(old_groups),
            "new_cultivars": len(new_groups),
            "summary": summary,
            "proposals": proposals,
        }, indent=2) + "\n")
        print(f"\nWritten {args.out}. Nothing applied: review, then seed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
