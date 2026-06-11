"""
The classification ladder (DEC-200 design doc 3.2): which category does a
scraped product belong to? Build-time only; snapshots stay raw facts.

Per product, first hit wins:

  1. Species-registry match. The caller supplies the matcher (the dashboard
     wires its existing match_species flow over ALL records, enabled or not:
     "category known but disabled" is useful needs-review information).
  2. Per-nursery category_raw mapping from the committed
     tools/scrapers/nursery_categories.json. Matchers run exact, then prefix,
     then contains, against the store's verbatim category string (Guildford's
     are comma-joined and HTML-escaped, e.g. "Berries &amp; Vines", which is
     why it uses contains).
  3. CATEGORY_KEYWORDS hint from stocklib.classify. Lowest confidence.
  4. Unclassified: stays in dashboard search exactly as before, excluded from
     category surfaces, counted per nursery for the /admin needs-review queue.

The correction loop is data, not code: add a species record or a mapping line
and the next nightly build reclassifies. No one hand-tunes keywords per
nursery.
"""
from __future__ import annotations

import json
from pathlib import Path

from .classify import CATEGORY_KEYWORDS

NURSERY_CATEGORIES_FILE = Path(__file__).parent.parent / "nursery_categories.json"

# Precedence order within a nursery's rules: an exact rule always beats a
# prefix rule, which always beats a contains rule, regardless of file order.
MATCH_MODES = ("exact", "prefix", "contains")

# Longest keyword first so "lemon scented gum" wins over a hypothetical
# shorter overlap; alphabetical second for determinism.
_KEYWORDS_ORDERED = sorted(CATEGORY_KEYWORDS, key=lambda kw: (-len(kw), kw))


def load_nursery_rules(path: Path | str | None = None) -> dict:
    """{nursery_key: [{match, mode, category}, ...]}. {} when the config is
    missing (the ladder just skips its second rung)."""
    path = Path(path) if path else NURSERY_CATEGORIES_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def match_category_raw(category_raw: str, rules: list[dict]) -> str | None:
    """Apply one nursery's rules to its verbatim category string:
    exact, then prefix, then contains. Case-insensitive; the string itself is
    NOT unescaped (rules target the verbatim value, &amp; included)."""
    if not category_raw or not rules:
        return None
    raw = category_raw.strip().lower()
    for mode in MATCH_MODES:
        for rule in rules:
            if rule.get("mode", "exact") != mode:
                continue
            needle = (rule.get("match") or "").strip().lower()
            if not needle:
                continue
            if ((mode == "exact" and raw == needle)
                    or (mode == "prefix" and raw.startswith(needle))
                    or (mode == "contains" and needle in raw)):
                return rule.get("category")
    return None


def keyword_hint(title: str) -> str | None:
    """Lowest-confidence rung: a CATEGORY_KEYWORDS hit in the title."""
    tl = title.lower()
    for kw in _KEYWORDS_ORDERED:
        if kw in tl:
            return CATEGORY_KEYWORDS[kw]
    return None


class Categorizer:
    """The ladder. species_matcher: callable(title) -> category | None
    (rung 1, supplied by the caller); nursery_rules: the parsed config
    (default: the committed file)."""

    def __init__(self, species_matcher=None, nursery_rules: dict | None = None):
        self.species_matcher = species_matcher or (lambda title: None)
        self.nursery_rules = (load_nursery_rules() if nursery_rules is None
                              else nursery_rules)

    def categorize(self, title: str, nursery: str = "",
                   category_raw: str = "") -> tuple[str | None, str]:
        """(category, source) with source in {"species", "category_raw",
        "keyword"}, or (None, "unclassified")."""
        cat = self.species_matcher(title)
        if cat:
            return (cat, "species")
        cat = match_category_raw(category_raw, self.nursery_rules.get(nursery, []))
        if cat:
            return (cat, "category_raw")
        cat = keyword_hint(title)
        if cat:
            return (cat, "keyword")
        return (None, "unclassified")


def build_needs_review(products, categorizer: Categorizer,
                       max_examples: int = 10) -> dict:
    """Run the ladder over (title, nursery, category_raw) triples and build
    the per-nursery needs-review report for /admin: totals, unclassified
    counts, per-category breakdown, example unclassified titles."""
    nurseries: dict[str, dict] = {}
    for title, nursery, category_raw in products:
        entry = nurseries.setdefault(nursery, {
            "total": 0, "unclassified": 0, "by_category": {}, "examples": [],
        })
        entry["total"] += 1
        cat, _source = categorizer.categorize(title, nursery, category_raw)
        if cat is None:
            entry["unclassified"] += 1
            if len(entry["examples"]) < max_examples:
                entry["examples"].append(title)
        else:
            entry["by_category"][cat] = entry["by_category"].get(cat, 0) + 1
    return {"nurseries": nurseries}
