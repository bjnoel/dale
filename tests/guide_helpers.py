"""
Shared setup for the per-species growing-guide tests.

Each species' tests live in their own tests/test_guide_<slug>.py so that several
guide-building agents working in parallel (see docs/species-guide-rollout.md) never
edit the same test file and never collide on merge. Those per-species files all import
the builders and constants from here, and the cross-cutting guards (climate mapping,
the unenriched fallback, the archive index, the growing_guides module API, and the
FAQ-overlap guard) stay in tests/test_species_state_pages.py.

This module is NOT a test module (it defines no TestCase), so unittest discovery skips it.
"""
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
GUIDES_DIR = SCRAPERS / "growing_guides"

# The builders import treestock_layout, shipping, stocklib and growing_guides,
# so the scrapers dir must be importable.
sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bssp = _load(SCRAPERS / "build_species_state_pages.py")
gg = _load(SCRAPERS / "growing_guides.py")
bsp = _load(SCRAPERS / "build_species_pages.py")

# U+2014 em dash, U+2013 en dash. Both banned in treestock copy.
EM_DASH = "—"
EN_DASH = "–"

# The states every growing guide carries an overlay for. Derived from the guide files
# rather than typed, because this list follows the content instead of leading it: the
# per-species tests below are OVERLAY tests (region tokens, per-state FAQs, mutually
# distinct bodies) and a state with no overlay written yet cannot pass them. SA went
# into the builders in DAL-297 with zero overlays, so it is absent here and will appear
# by itself on the night the last SA overlay is written.
# NOT the builder's state list: for that, read bssp.STATES (see tests/test_combo_lifecycle.py).
def _states_every_guide_overlays():
    per_guide = [
        set((json.loads(p.read_text()).get("states") or {}).keys())
        for p in sorted(GUIDES_DIR.glob("*.json"))
        if "core" in json.loads(p.read_text())
    ]
    covered = set.intersection(*per_guide) if per_guide else set()
    return [st for st in bssp.STATES if st in covered]


STATES = _states_every_guide_overlays()
TODAY = "2026-06-01"

VALID_SLUGS = {s["slug"] for s in json.loads((SCRAPERS / "fruit_species.json").read_text()) if s.get("slug")}


def load_guide(slug: str) -> dict:
    """Parse growing_guides/<slug>.json."""
    return json.loads((GUIDES_DIR / f"{slug}.json").read_text(encoding="utf-8"))


def build_state_pages(slug: str, products: list) -> dict:
    """Render the buy-<slug>-trees-<state> combo page for every state."""
    return {st: bssp.build_combo_page(st, slug, products, TODAY) for st in STATES}


def assert_no_dashes(tc, obj, path: str):
    """Recursively assert a JSON value carries no em or en dashes (treestock copy rule)."""
    if isinstance(obj, str):
        tc.assertNotIn(EM_DASH, obj, f"em dash in {path}")
        tc.assertNotIn(EN_DASH, obj, f"en dash in {path}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            assert_no_dashes(tc, v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            assert_no_dashes(tc, v, f"{path}[{i}]")
