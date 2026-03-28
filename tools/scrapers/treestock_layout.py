"""
Shared layout module for treestock.com.au pages.

Provides consistent head, header, navigation, breadcrumbs, and footer
across all build scripts. Pure f-strings, no template engine dependencies.

Usage:
    from treestock_layout import render_head, render_header, render_footer, render_breadcrumb
"""

# --- Constants ---

SITE_NAME = "treestock.com.au"
SITE_URL = "https://treestock.com.au"

TAILWIND_CSS = "/styles.css"
PLAUSIBLE_SCRIPT = '<script defer data-domain="treestock.com.au" src="https://data.bjnoel.com/js/script.outbound-links.js"></script>'

NAV_ITEMS = [
    ("Search", "/"),
    ("Species", "/species/"),
    ("Nurseries", "/nursery/"),
    ("Varieties", "/variety/"),
    ("Compare", "/compare/"),
    ("Rare Finds", "/rare.html"),
    ("Digest", "/digest.html"),
    ("History", "/history.html"),
]

LOGO_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" class="w-7 h-7 flex-shrink-0">\
<rect width="64" height="64" rx="12" fill="#065f46"/>\
<path d="M32,12 C18,16 12,28 14,42 C16,38 20,34 26,32 C22,38 20,44 20,50 C28,44 38,34 40,20 C38,14 34,12 32,12Z" fill="#22c55e" opacity="0.9"/>\
<path d="M32,14 C28,24 24,34 20,48" fill="none" stroke="#065f46" stroke-width="1.5" opacity="0.4"/>\
<circle cx="44" cy="44" r="8" fill="#f59e0b"/>\
<text x="44" y="48" text-anchor="middle" font-family="sans-serif" font-size="12" font-weight="bold" fill="#065f46">$</text>\
</svg>"""

BASE_STYLE = """\
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
  #nav-menu.open { display: flex; }"""

# Hamburger toggle script (tiny, no dependencies)
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
    """Render the <head> block including Tailwind CDN, Plausible, and base styles."""
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
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link href="{TAILWIND_CSS}" rel="stylesheet">
{PLAUSIBLE_SCRIPT}
{style_block}
{extra_head}
</head>"""


def render_header(
    subtitle: str = "",
    max_width: str = "max-w-3xl",
    show_nav: bool = True,
    active_path: str = "",
    extra_right: str = "",
) -> str:
    """Render the sticky site header with SVG logo, desktop nav, and mobile hamburger."""

    # Build nav links (desktop inline, mobile dropdown)
    nav_section = ""
    nav_script = ""
    if show_nav:
        links = []
        for label, path in NAV_ITEMS:
            if path == "/":
                continue  # Home link is the logo
            is_active = active_path and active_path.rstrip("/") == path.rstrip("/")
            active_cls = " text-green-800 font-semibold" if is_active else " text-gray-600"
            links.append(
                f'<a href="{path}" class="hover:text-green-700 no-underline whitespace-nowrap{active_cls}">{label}</a>'
            )
        links_html = "\n        ".join(links)

        # Desktop: inline row of text links. Mobile: hidden, toggled by hamburger.
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

    right_section = ""
    if extra_right:
        right_section = extra_right

    return f"""
<body class="bg-white text-gray-900">

<header class="border-b border-gray-200 bg-white sticky top-0 z-10">
  <div class="{max_width} mx-auto px-4 py-2">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <a href="/" class="flex items-center gap-2 no-underline flex-shrink-0">
        {LOGO_SVG}
        <span class="text-lg font-bold text-green-800">{SITE_NAME}</span>
      </a>{nav_section}{right_section}
    </div>
  </div>
</header>
{nav_script}"""


def render_breadcrumb(crumbs: list[tuple[str, str]], max_width: str = "max-w-3xl") -> str:
    """Render breadcrumb navigation.

    crumbs: list of (label, url) tuples. Last item has no link (current page).
    """
    parts = []
    for i, (label, url) in enumerate(crumbs):
        if i == len(crumbs) - 1:
            parts.append(label)
        else:
            parts.append(f'<a href="{url}" class="hover:underline">{label}</a>')
    return f"""
  <nav class="text-xs text-gray-400 mb-4">
    {" &#8250; ".join(parts)}
  </nav>"""


def render_footer(max_width: str = "max-w-3xl", extra_text: str = "") -> str:
    """Render the site footer with nav links and attribution."""
    links = []
    for label, path in NAV_ITEMS:
        if path == "/":
            links.append(f'<a href="/" class="hover:text-gray-600">Home</a>')
        else:
            links.append(f'<a href="{path}" class="hover:text-gray-600">{label}</a>')

    nav_line = " &middot;\n    ".join(links)

    extra = ""
    if extra_text:
        extra = f"\n  <p class=\"mt-2\">{extra_text}</p>"

    return f"""
<footer class="border-t border-gray-200 mt-8 py-6 text-center text-xs text-gray-400">
  <div class="{max_width} mx-auto px-4">
    {nav_line}
    <p class="mt-2">Data updated daily. Prices and availability may change.</p>
    <p class="mt-1">A project by <a href="https://bjnoel.com" class="underline">Benedict Noel</a>, Perth WA</p>{extra}
  </div>
</footer>"""


def render_page(
    title: str,
    body: str,
    description: str = "",
    subtitle: str = "",
    canonical_url: str = "",
    max_width: str = "max-w-3xl",
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
