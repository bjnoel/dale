"""
treestock.com.au page layout.

The <head> and the site <header> are shared with beestock via stocklib.layout
(parameterised by a SiteConfig); this module binds them to the treestock config
and keeps the treestock-specific breadcrumb, footer, Treesmith promo, and the
render_page convenience wrapper. Pure f-strings, no template engine.

Usage:
    from treestock_layout import render_head, render_header, render_footer, render_breadcrumb
"""

import functools
from datetime import datetime

from stocklib import layout
from stocklib import structured_data as _sd
from stocklib.layout import SiteConfig
from stocklib.templates import get_env

# --- Constants ---

SITE_NAME = "treestock.com.au"
SITE_URL = "https://treestock.com.au"
ORG_DESCRIPTION = (
    "treestock.com.au tracks fruit and rare plant stock, prices, and "
    "availability across Australian nurseries, updated daily."
)

TAILWIND_CSS = f"/styles.css?v={datetime.utcnow().strftime('%Y%m%d')}"
# Preconnect to the analytics origin before the deferred script needs it. PageSpeed
# estimated ~840ms mobile LCP savings from warming this connection early. No crossorigin:
# the script tag is a non-CORS request, so the warmed connection must match it.
PLAUSIBLE_SCRIPT = ('<link rel="preconnect" href="https://data.bjnoel.com">'
                    '<link rel="dns-prefetch" href="https://data.bjnoel.com">'
                    '<script defer data-domain="treestock.com.au" src="https://data.bjnoel.com/js/script.outbound-links.js"></script>')

# Top-level nav order: the three plant-browse pages (Species, Varieties, Bush
# Tucker) sit adjacent as the core of the site; Nurseries is a separate flat
# item (a different axis, not a plant type); then two dropdowns keep the bar
# short. Guides = informational content; Insights = the price/availability
# tracking data that is treestock's moat (digest, history, trends, compare,
# rare finds), all facets of "what changed and where to buy".
NAV_ITEMS = [
    ("Search", "/"),
    ("Species", "/species/"),
    ("Varieties", "/variety/"),
    ("Bush Tucker", "/bush-tucker/"),
    ("Nurseries", "/nursery/"),
    ("Guides", [
        ("Companion Planting", "/companion-planting-guide.html"),
        ("Bare Root Season", "/bare-root.html"),
        ("Planting Calendar", "/when-to-plant.html"),
        ("Fruit Tree Pollination", "/fruit-tree-pollination-guide.html"),
        ("Rootstock Guide", "/rootstock.html"),
    ]),
    ("Insights", [
        ("Digest", "/digest.html"),
        ("History", "/history.html"),
        ("Trends", "/trends.html"),
        ("Compare", "/compare/"),
        ("Rare Finds", "/rare.html"),
    ]),
]

LOGO_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" class="w-7 h-7 flex-shrink-0">\
<rect width="64" height="64" rx="12" fill="#065f46"/>\
<g transform="rotate(-40 32 32)">\
<path d="M20,14 L46,14 C48.2,14 50,15.8 50,18 L50,44 C50,46.2 48.2,48 46,48 L20,48 C18.6,48 17.3,47.3 16.5,46.1 L8.8,35.1 C7.9,33.8 7.9,32.2 8.8,30.9 L16.5,19.9 C17.3,18.7 18.6,18 20,18 Z" fill="#f59e0b"/>\
<circle cx="18" cy="31" r="3.6" fill="#065f46"/>\
<path d="M40,22 C31,25 26,32 27.5,40 C29.3,37 32,35 35.5,34 C32,37 30.5,41 30.7,45 C38,41.5 43,34.5 42,26.5 C41,23.5 41.5,21.4 40,22 Z" fill="#16a34a" transform="rotate(40 32 32)"/>\
</g>\
</svg>"""

BASE_STYLE = """\
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
  #nav-menu.open { display: flex; }
  #nav-menu details > summary { list-style: none; }
  #nav-menu details > summary::-webkit-details-marker { display: none; }"""

# Responsive content width, one token driving every page's header, main,
# breadcrumb, and footer so the widths never drift:
#   - mobile + tablet (<1024px): 768px (max-w-3xl) -- the comfortable reading column
#   - laptop/desktop (lg, >=1024px): 1024px (max-w-5xl)
#   - large monitor (2xl, >=1536px): 1280px (max-w-7xl)
# Previously this only widened at the 2xl breakpoint, so a 13" laptop (just under
# 1536px) stayed stuck at the narrow 768px column. The lg step fixes that.
CONTENT_MAX_WIDTH = "max-w-3xl lg:max-w-5xl 2xl:max-w-7xl"

# Make the width token available to the Jinja templates (treestock env only; the
# bee site renders its own inline HTML and never loads these templates).
get_env().globals["content_max_width"] = CONTENT_MAX_WIDTH

# --- Site config: head + header are shared via stocklib.layout ---

TREESTOCK = SiteConfig(
    site_name=SITE_NAME,
    site_url=SITE_URL,
    tailwind_href=TAILWIND_CSS,
    plausible_script=PLAUSIBLE_SCRIPT,
    favicon_html=(
        '<link rel="icon" href="/favicon.svg" type="image/svg+xml">'
        '<link rel="icon" href="/favicon-32.png" sizes="32x32" type="image/png">'
        '<link rel="icon" href="/favicon-16.png" sizes="16x16" type="image/png">'
        '<link rel="apple-touch-icon" href="/apple-touch-icon.png">'
        '<link rel="manifest" href="/site.webmanifest">'
    ),
    logo_svg=LOGO_SVG,
    nav_items=NAV_ITEMS,
    accent="green",
    default_og_image=f"{SITE_URL}/og-image.png",
    default_max_width=CONTENT_MAX_WIDTH,
    base_style=BASE_STYLE,
)

# Bound to the treestock config so existing callers keep using
# `render_head(...)` / `render_header(...)`. These are assignments (not `def`s),
# so the single real definition lives in stocklib/layout.py -- the anti-drift
# guard in tests/test_no_forking.py depends on that.
render_head = functools.partial(layout.render_head, TREESTOCK)
render_header = functools.partial(layout.render_header, TREESTOCK)


def organization_jsonld() -> str:
    """Organization JSON-LD (emit once, on the homepage)."""
    return _sd.organization_jsonld(
        SITE_URL, SITE_NAME, description=ORG_DESCRIPTION, same_as=["https://bjnoel.com"]
    )


def website_jsonld() -> str:
    """WebSite JSON-LD (emit once, on the homepage)."""
    return _sd.website_jsonld(SITE_URL, SITE_NAME)


def render_breadcrumb(crumbs: list[tuple[str, str]], max_width: str = CONTENT_MAX_WIDTH) -> str:
    """Render breadcrumb navigation plus its BreadcrumbList JSON-LD.

    crumbs: list of (label, url) tuples. Last item has no link (current page).
    The JSON-LD is appended after the <nav> (valid anywhere in the body), so
    every breadcrumbed page emits BreadcrumbList structured data for free.
    """
    parts = []
    for i, (label, url) in enumerate(crumbs):
        if i == len(crumbs) - 1:
            parts.append(label)
        else:
            parts.append(f'<a href="{url}" class="hover:underline">{label}</a>')
    nav = f"""
  <nav class="text-xs text-gray-400 mb-4">
    {" &#8250; ".join(parts)}
  </nav>"""
    return nav + "\n" + _sd.breadcrumb_jsonld(crumbs, SITE_URL)


def render_footer(max_width: str = CONTENT_MAX_WIDTH, extra_text: str = "") -> str:
    """Render the site footer with nav links and attribution."""
    links = []
    for label, path in NAV_ITEMS:
        if isinstance(path, (list, tuple)):
            # Grouped nav entry (e.g. Guides): flatten to its individual links so
            # the footer still deep-links every guide page for crawlers.
            for sub_label, sub_path in path:
                links.append(f'<a href="{sub_path}" class="inline-block py-1.5 px-1 hover:text-gray-900">{sub_label}</a>')
        elif path == "/":
            links.append(f'<a href="/" class="inline-block py-1.5 px-1 hover:text-gray-900">Home</a>')
        else:
            links.append(f'<a href="{path}" class="inline-block py-1.5 px-1 hover:text-gray-900">{label}</a>')

    nav_line = " &middot;\n    ".join(links)

    state_links = (
        '<a href="/buy-fruit-trees-wa.html" class="inline-block py-1.5 px-1 hover:text-gray-900">Buy in WA</a>'
        ' &middot; '
        '<a href="/buy-fruit-trees-qld.html" class="inline-block py-1.5 px-1 hover:text-gray-900">Buy in QLD</a>'
        ' &middot; '
        '<a href="/buy-fruit-trees-nsw.html" class="inline-block py-1.5 px-1 hover:text-gray-900">Buy in NSW</a>'
        ' &middot; '
        '<a href="/buy-fruit-trees-vic.html" class="inline-block py-1.5 px-1 hover:text-gray-900">Buy in VIC</a>'
        ' &middot; '
        '<a href="/compare/nurseries.html" class="inline-block py-1.5 px-1 hover:text-gray-900">Compare Nurseries</a>'
        ' &middot; '
        '<a href="/treesmith.html" class="inline-block py-1.5 px-1 hover:text-gray-900">Treesmith app</a>'
        ' &middot; '
        '<a href="/manage.html" class="inline-block py-1.5 px-1 hover:text-gray-900">Manage email alerts</a>'
    )

    extra = ""
    if extra_text:
        extra = f"\n  <p class=\"mt-2\">{extra_text}</p>"

    return f"""
<footer class="border-t border-gray-200 mt-8 py-6 text-center text-xs text-gray-600">
  <div class="{max_width} mx-auto px-4">
    {nav_line}
    <p class="mt-2">{state_links}</p>
    <p class="mt-2">Data updated daily. Prices and availability may change.</p>
    <p class="mt-1">A project by <a href="https://bjnoel.com" class="underline">Benedict Noel</a>, Perth WA</p>{extra}
  </div>
</footer>"""


def render_treesmith_promo(context: str = "variety") -> str:
    """Tasteful Treesmith cross-promo block for high-traffic pages.

    Reuses the copy/styling from build_treesmith_page.py. Designed to sit below
    the results and watch form (below the fold) so it never competes with the
    primary CTA. `context` tweaks the lead line for variety vs species pages.
    No em dashes (treestock copy rule).
    """
    lead = {
        "variety": "Tracking a variety here? Keep a record of the one you actually buy.",
        "species": "Found a tree to buy? Keep a record of the one you actually plant.",
    }.get(context, "Keep a record of the trees you actually buy.")
    return f"""
  <!-- Treesmith cross-promo (below the fold) -->
  <aside class="bg-green-50 border border-green-200 rounded-lg p-5 mb-8">
    <div class="flex items-start gap-4">
      <img src="/treesmith/icon.png" alt="Treesmith app icon" width="48" height="48"
           class="w-12 h-12 rounded-xl shadow flex-shrink-0">
      <div class="min-w-0">
        <h3 class="font-semibold text-green-900 mb-1">Track your collection with Treesmith</h3>
        <p class="text-sm text-green-900 mb-3">
          {lead} Treesmith is a mobile app for plant collectors: catalog every tree,
          log grafts and harvests, and capture growth photos over time. Built by the
          same person behind treestock.
        </p>
        <a href="/treesmith.html?utm_source=treestock&amp;utm_medium=web&amp;utm_campaign=promo_block&amp;utm_content={context}"
           class="inline-block bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-green-800 no-underline">
          See Treesmith &rarr;
        </a>
      </div>
    </div>
  </aside>"""


def render_page(
    title: str,
    body: str,
    description: str = "",
    subtitle: str = "",
    canonical_url: str = "",
    max_width: str = CONTENT_MAX_WIDTH,
    show_nav: bool = True,
    active_path: str = "",
    extra_head: str = "",
    extra_right: str = "",
    extra_style: str = "",
    extra_body_end: str = "",
    extra_footer_text: str = "",
    og_title: str = "",
    og_description: str = "",
    og_image: str = "",
    og_type: str = "",
    twitter_card: str = "summary_large_image",
    robots: str = "",
    jsonld="",
) -> str:
    """Convenience wrapper: renders a complete page."""
    head = render_head(
        title=title,
        description=description,
        canonical_url=canonical_url,
        extra_head=extra_head,
        og_title=og_title,
        og_description=og_description,
        og_image=og_image,
        og_type=og_type,
        twitter_card=twitter_card,
        robots=robots,
        jsonld=jsonld,
        extra_style=extra_style,
    )
    header = render_header(
        subtitle=subtitle,
        max_width=max_width,
        show_nav=show_nav,
        active_path=active_path,
        extra_right=extra_right,
    )
    footer = render_footer(max_width=max_width, extra_text=extra_footer_text)

    return f"""{head}
{header}

<main class="{max_width} mx-auto px-4 py-6">
{body}
</main>

{footer}
{extra_body_end}
</body>
</html>"""
