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

TAILWIND_CDN = "https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css"
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

BASE_STYLE = """\
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }"""


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
<link href="{TAILWIND_CDN}" rel="stylesheet">
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
    """Render the sticky site header with optional nav links."""
    nav_html = ""
    if show_nav:
        links = []
        for label, path in NAV_ITEMS:
            if path == "/":
                continue  # Don't show "Search" link on subpages, home link is the logo
            is_active = active_path and active_path.rstrip("/") == path.rstrip("/")
            active_cls = " bg-green-50 text-green-800 border-green-300" if is_active else ""
            links.append(
                f'<a href="{path}" class="px-2 py-1 rounded border border-gray-300 '
                f'hover:bg-gray-50 no-underline whitespace-nowrap{active_cls}">{label}</a>'
            )
        nav_html = f"""
      <div class="flex gap-1.5 text-xs flex-wrap justify-end">
        {"".join(links)}
      </div>"""

    right_content = extra_right or nav_html

    subtitle_html = ""
    if subtitle:
        subtitle_html = f'\n        <p class="text-sm text-gray-500">{subtitle}</p>'

    return f"""
<body class="bg-white text-gray-900">

<header class="border-b border-gray-200 bg-white sticky top-0 z-10">
  <div class="{max_width} mx-auto px-4 py-3">
    <div class="flex items-center justify-between gap-3">
      <div class="flex-shrink-0">
        <h1 class="text-xl font-bold text-green-800">
          <a href="/" class="hover:underline">{SITE_NAME}</a>
        </h1>{subtitle_html}
      </div>{right_content}
    </div>
  </div>
</header>"""


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
