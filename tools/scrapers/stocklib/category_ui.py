"""Category badge + filter UI shared by the /species/ and /variety/ indexes.

A species shows one badge per category it belongs to: its primary ``category``
plus any ``tags`` that name another known category. So a cross-listed species
(finger-lime: category ``fruit``, tags ``["bush_tucker"]``) shows both a Fruit
and a Bush Tucker badge, and matches both the Fruit and Bush Tucker filter pills.

Add a line to ``CATEGORY_BADGES`` (and a colour to ``CATEGORY_FILTER_CSS``) when a
new category is enabled in ``stocklib.taxonomy.ENABLED_CATEGORIES``.
"""

# category key -> (badge label, badge CSS class)
CATEGORY_BADGES = {
    "fruit": ("Fruit", "cat-badge-fruit"),
    "bush_tucker": ("Bush Tucker", "cat-badge-bush"),
}

# Self-contained CSS (NOT Tailwind utilities) so it survives the purged Tailwind
# build, which only sees classes present in the static HTML. Injected via
# render_head(extra_style=...).

# Just the badge classes (the homepage uses these without the filter pills, since
# its category control is a <select> in the existing filter row).
CATEGORY_BADGE_CSS = """\
  .cat-badge { display: inline-block; font-size: 0.7rem; padding: 0.05rem 0.4rem; border-radius: 9999px; border: 1px solid; white-space: nowrap; margin-left: 0.35rem; vertical-align: middle; }
  .cat-badge-fruit { background-color: #f0fdf4; color: #15803d; border-color: #bbf7d0; }
  .cat-badge-bush { background-color: #f0fdfa; color: #0f766e; border-color: #99f6e4; }"""

# Pills + badges, for the /species/, /variety/ and /compare/ indexes. The
# tr.hidden-row rule is used by the table-based indexes; it is harmless on
# /variety/ (which hides via inline style). This composes the badge CSS so the
# string stays identical to its original inline value.
CATEGORY_FILTER_CSS = """\
  .cat-filter-btn { cursor: pointer; }
  .cat-filter-btn.active { background-color: #065f46; color: white; border-color: #065f46; }
  tr.hidden-row { display: none; }
""" + CATEGORY_BADGE_CSS


def category_keys(species: dict) -> list[str]:
    """The known categories a species belongs to: primary ``category`` first,
    then any ``tags`` that name another known category."""
    cats = [species.get("category", "fruit")]
    for tag in species.get("tags", []):
        if tag in CATEGORY_BADGES and tag not in cats:
            cats.append(tag)
    return [c for c in cats if c in CATEGORY_BADGES]


def category_badges_html(species: dict) -> str:
    """One badge span per category the species belongs to, primary first."""
    return "".join(
        f'<span class="cat-badge {CATEGORY_BADGES[c][1]}">{CATEGORY_BADGES[c][0]}</span>'
        for c in category_keys(species)
    )


def is_bush_tucker(species: dict) -> bool:
    """True if the species belongs to bush_tucker by category or tag."""
    return "bush_tucker" in category_keys(species)
