"""
Shared layout module for beestock pages.

Mirrors treestock_layout.py but with beekeeping branding.
Pure f-strings, no template engine dependencies.

Usage:
    from beestock_layout import render_head, render_header, render_footer
"""

# --- Constants ---

SITE_NAME = "beestock.com.au"
SITE_URL = "https://beestock.com.au"

TAILWIND_CDN = "https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css"
PLAUSIBLE_SCRIPT = '<script defer data-domain="beestock.com.au" src="https://data.bjnoel.com/js/script.outbound-links.js"></script>'

NAV_ITEMS = [
    ("Search", "/"),
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

BASE_STYLE = """\
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
  #nav-menu.open { display: flex; }"""

_NAV_TOGGLE_SCRIPT = """\
<script>
document.getElementById('nav-toggle').addEventListener('click', function() {
  document.getElementById('nav-menu').classList.toggle('open');
});
</script>"""


# --- Functions ---

def render_head(
    title: str,
    description: str = "",
    canonical_url: str = "",
    extra_head: str = "",
    og_title: str = "",
    og_description: str = "",
    og_image: str = "",
    og_type: str = "",
    extra_style: str = "",
) -> str:
    """Render the <head> block."""
    meta_desc = f'\n<meta name="description" content="{description}">' if description else ""
    canonical = f'\n<link rel="canonical" href="{canonical_url}">' if canonical_url else ""

    og_parts = []
    if og_title:
        og_parts.append(f'<meta property="og:title" content="{og_title}">')
    if og_description:
        og_parts.append(f'<meta property="og:description" content="{og_description}">')
    if og_image:
        og_parts.append(f'<meta property="og:image" content="{og_image}">')
    if og_type:
        og_parts.append(f'<meta property="og:type" content="{og_type}">')
    if canonical_url:
        og_parts.append(f'<meta property="og:url" content="{canonical_url}">')
    og_html = "\n".join(og_parts)
    if og_html:
        og_html = "\n" + og_html

    style_block = f"<style>\n{BASE_STYLE}"
    if extra_style:
        style_block += f"\n{extra_style}"
    style_block += "\n</style>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">{meta_desc}{canonical}{og_html}
<title>{title}</title>
<link href="{TAILWIND_CDN}" rel="stylesheet">
{PLAUSIBLE_SCRIPT}
{style_block}
{extra_head}
</head>"""


def render_header(
    max_width: str = "max-w-5xl",
    show_nav: bool = True,
    active_path: str = "",
) -> str:
    """Render the sticky site header."""
    nav_section = ""
    nav_script = ""
    if show_nav:
        links = []
        for label, path in NAV_ITEMS:
            if path == "/":
                continue
            is_active = active_path and active_path.rstrip("/") == path.rstrip("/")
            active_cls = " text-yellow-800 font-semibold" if is_active else " text-gray-600"
            links.append(
                f'<a href="{path}" class="hover:text-yellow-700 no-underline whitespace-nowrap{active_cls}">{label}</a>'
            )
        links_html = "\n        ".join(links)

        nav_section = f"""
      <nav id="nav-menu" class="hidden sm:flex sm:items-center sm:gap-4 text-sm
                                flex-col sm:flex-row gap-2 w-full sm:w-auto mt-2 sm:mt-0
                                border-t sm:border-0 border-gray-100 pt-2 sm:pt-0">
        {links_html}
      </nav>
      <button id="nav-toggle" class="sm:hidden p-1 text-gray-500 hover:text-gray-800" aria-label="Menu">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
        </svg>
      </button>"""
        nav_script = _NAV_TOGGLE_SCRIPT

    return f"""
<body class="bg-white text-gray-900">

<header class="border-b border-gray-200 bg-white sticky top-0 z-10">
  <div class="{max_width} mx-auto px-4 py-2">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <a href="/" class="flex items-center gap-2 no-underline flex-shrink-0">
        {LOGO_SVG}
        <span class="text-lg font-bold text-yellow-800">{SITE_NAME}</span>
      </a>{nav_section}
    </div>
  </div>
</header>
{nav_script}"""


def render_footer(max_width: str = "max-w-5xl") -> str:
    """Render the site footer."""
    links = []
    for label, path in NAV_ITEMS:
        if path == "/":
            links.append(f'<a href="/" class="hover:text-gray-600">Home</a>')
        else:
            links.append(f'<a href="{path}" class="hover:text-gray-600">{label}</a>')

    nav_line = " &middot;\n    ".join(links)

    return f"""
<footer class="border-t border-gray-200 mt-8 py-6 text-center text-xs text-gray-400">
  <div class="{max_width} mx-auto px-4">
    {nav_line}
    <p class="mt-2">Data updated daily. Prices and availability may change.</p>
    <p class="mt-1">A project by <a href="https://bjnoel.com" class="underline">Benedict Noel</a>, Perth WA</p>
  </div>
</footer>"""
