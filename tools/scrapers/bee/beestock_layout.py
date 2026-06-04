"""
beestock.com.au page layout.

The <head> and the site <header> are shared with treestock via stocklib.layout
(parameterised by a SiteConfig); this module binds them to the beestock config
and keeps the beestock-specific breadcrumb and footer. Pure f-strings, no
template engine.

Usage:
    from beestock_layout import render_head, render_header, render_footer
"""

import base64
import functools
import sys
from pathlib import Path

# beestock_layout lives in tools/scrapers/bee/; reach stocklib in the parent dir
# (matches how the bee builders set up sys.path before importing the package).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from stocklib import layout
from stocklib.layout import SiteConfig

# --- Constants ---

SITE_NAME = "beestock.com.au"
SITE_URL = "https://beestock.com.au"

TAILWIND_CSS = "/styles.css"
PLAUSIBLE_SCRIPT = """\
<script async src="https://data.bjnoel.com/js/pa-ncu0JIgthEVy21f-Vfd6K.js"></script>
<script>
  window.plausible=window.plausible||function(){(plausible.q=plausible.q||[]).push(arguments)},plausible.init=plausible.init||function(i){plausible.o=i||{}};
  plausible.init()
</script>"""

NAV_ITEMS = [
    ("Search", "/"),
    ("Categories", "/category/hives-boxes.html"),
    ("Compare", "/compare/"),
    ("Retailers", "/retailer/"),
    ("Digest", "/digest.html"),
]

# Bee-themed logo: hexagon (honeycomb cell) with $ price tag
LOGO_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" class="w-7 h-7 flex-shrink-0">\
<rect width="64" height="64" rx="12" fill="#92400e"/>\
<path d="M32,10 L50,22 L50,42 L32,54 L14,42 L14,22Z" fill="#f59e0b" opacity="0.9"/>\
<path d="M32,18 L42,25 L42,39 L32,46 L22,39 L22,25Z" fill="#fbbf24" opacity="0.6"/>\
<circle cx="44" cy="46" r="8" fill="#065f46"/>\
<text x="44" y="50" text-anchor="middle" font-family="sans-serif" font-size="12" font-weight="bold" fill="#f59e0b">$</text>\
</svg>"""

# Standalone favicon SVG (same design, no Tailwind classes)
FAVICON_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">\
<rect width="64" height="64" rx="12" fill="#92400e"/>\
<path d="M32,10 L50,22 L50,42 L32,54 L14,42 L14,22Z" fill="#f59e0b" opacity="0.9"/>\
<path d="M32,18 L42,25 L42,39 L32,46 L22,39 L22,25Z" fill="#fbbf24" opacity="0.6"/>\
<circle cx="44" cy="46" r="8" fill="#065f46"/>\
<text x="44" y="50" text-anchor="middle" font-family="sans-serif" font-size="12" font-weight="bold" fill="#f59e0b">$</text>\
</svg>"""

FAVICON_DATA_URI = "data:image/svg+xml;base64," + base64.b64encode(FAVICON_SVG.encode()).decode()

BASE_STYLE = """\
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
  #nav-menu.open { display: flex; }"""

# --- Site config: head + header are shared via stocklib.layout ---

BEE = SiteConfig(
    site_name=SITE_NAME,
    site_url=SITE_URL,
    tailwind_href=TAILWIND_CSS,
    plausible_script=PLAUSIBLE_SCRIPT,
    favicon_html=f'<link rel="icon" type="image/svg+xml" href="{FAVICON_DATA_URI}">',
    logo_svg=LOGO_SVG,
    nav_items=NAV_ITEMS,
    accent="yellow",
    default_max_width="max-w-5xl",
    base_style=BASE_STYLE,
)

# Bound to the beestock config so existing callers keep using
# `render_head(...)` / `render_header(...)`. These are assignments (not `def`s),
# so the single real definition lives in stocklib/layout.py (see
# tests/test_no_forking.py).
render_head = functools.partial(layout.render_head, BEE)
render_header = functools.partial(layout.render_header, BEE)


def render_breadcrumb(crumbs: list[tuple[str, str]], max_width: str = "max-w-5xl") -> str:
    """Render breadcrumb navigation. Each crumb is (label, url). Last crumb has no link."""
    parts = []
    for i, (label, url) in enumerate(crumbs):
        if i == len(crumbs) - 1:
            parts.append(f'<span class="text-gray-500">{label}</span>')
        else:
            parts.append(f'<a href="{url}" class="text-yellow-700 hover:underline">{label}</a>')
    sep = ' <span class="text-gray-300 mx-1">/</span> '
    return f'<nav class="text-xs text-gray-500 mb-4" aria-label="Breadcrumb">{sep.join(parts)}</nav>'


def render_footer(max_width: str = "max-w-5xl") -> str:
    """Render the site footer."""
    links = []
    for label, path in NAV_ITEMS:
        if path == "/":
            links.append(f'<a href="/" class="hover:text-gray-600">Home</a>')
        else:
            links.append(f'<a href="{path}" class="hover:text-gray-600">{label}</a>')

    nav_line = " &middot;\n    ".join(links)

    state_links = (
        '<a href="/buy-beekeeping-supplies-wa.html" class="hover:text-gray-600">WA</a> &middot;\n    '
        '<a href="/buy-beekeeping-supplies-qld.html" class="hover:text-gray-600">QLD</a> &middot;\n    '
        '<a href="/buy-beekeeping-supplies-nsw.html" class="hover:text-gray-600">NSW</a> &middot;\n    '
        '<a href="/buy-beekeeping-supplies-vic.html" class="hover:text-gray-600">VIC</a>'
    )

    return f"""
<footer class="border-t border-gray-200 mt-8 py-6 text-center text-xs text-gray-400">
  <div class="{max_width} mx-auto px-4">
    {nav_line}
    <p class="mt-2">Buy beekeeping supplies: {state_links}</p>
    <p class="mt-2">Data updated daily. Prices and availability may change.</p>
    <p class="mt-1">A project by <a href="https://bjnoel.com" class="underline">Benedict Noel</a>, Perth WA</p>
  </div>
</footer>"""
