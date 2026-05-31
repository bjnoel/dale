"""
Species taxonomy loader, category-aware.

Centralises loading the species list (currently fruit_species.json) and adds a
`category` dimension. Existing records have no category, so they default to
"fruit"; ENABLED_CATEGORIES is the single switch for which categories the site
covers. Today it is ("fruit",) so behaviour is unchanged.

This is the "all trees" enabler: to later cover ornamentals/natives, add records
with `"category": "ornamental"` (here or in an additional file) and append the
category to ENABLED_CATEGORIES -- a data + one-line change, not a code hunt.

Consumers are migrated onto this module incrementally (build-dashboard first);
the other per-builder species loaders still read the file directly for now.
"""
from __future__ import annotations

import json
from pathlib import Path

# The species data still lives at tools/scrapers/fruit_species.json (renaming it
# would ripple to ~13 readers; deferred). taxonomy.py sits in stocklib/, one level
# down, so the file is one directory up.
SPECIES_FILE = Path(__file__).parent.parent / "fruit_species.json"

DEFAULT_CATEGORY = "fruit"
ENABLED_CATEGORIES: tuple[str, ...] = ("fruit",)


def load_species(path: Path | None = None) -> list[dict]:
    """Load species records. Each record without a `category` defaults to
    DEFAULT_CATEGORY. Returns [] if the file is missing (matching the callers'
    previous behaviour)."""
    path = path or SPECIES_FILE
    if not path.exists():
        return []
    with open(path) as f:
        records = json.load(f)
    for r in records:
        r.setdefault("category", DEFAULT_CATEGORY)
    return records


def categories(path: Path | None = None) -> set[str]:
    """The set of categories present in the taxonomy."""
    return {r.get("category", DEFAULT_CATEGORY) for r in load_species(path)}


def category_of(common_name: str, species: list[dict] | None = None) -> str | None:
    """Category for a species by common name (case-insensitive), or None."""
    species = species if species is not None else load_species()
    target = common_name.lower()
    for r in species:
        if r.get("common_name", "").lower() == target:
            return r.get("category", DEFAULT_CATEGORY)
    return None


def is_enabled(common_name: str, species: list[dict] | None = None) -> bool:
    """True if the species' category is currently enabled."""
    return category_of(common_name, species) in ENABLED_CATEGORIES


def enabled_species(path: Path | None = None) -> list[dict]:
    """Records whose category is enabled (today: fruit only)."""
    return [r for r in load_species(path)
            if r.get("category", DEFAULT_CATEGORY) in ENABLED_CATEGORIES]
