"""
Shared page chrome (the <head> and the site <header>) for the stock sites.

These two blocks were duplicated, near-identically, in treestock_layout.py and
bee/beestock_layout.py: exactly the "edit one, forget the other" hazard the
stocklib package exists to remove (the header logo colour, nav, and Plausible
snippet had already drifted apart). They now live here once, parameterised by a
SiteConfig. Each site builds its SiteConfig and binds render_head/render_header
to it (see treestock_layout.TREESTOCK and beestock_layout.BEE), so the existing
`from treestock_layout import render_head` call sites keep working unchanged.

Only trusted values (site name, nav, canonical URL, logo SVG) are interpolated
here, so these stay f-strings and the output is byte-identical to the
pre-de-fork pages. Escaping untrusted nursery titles is a separate change to the
body builders (Jinja2 autoescape, PR10b), not to this chrome.

render_breadcrumb and render_footer deliberately stay per-site: the breadcrumb
markup and the footers diverge structurally between the two sites, so sharing
them would be mostly config plumbing for little gain (same call the PR10 plan
makes for the footer).
"""
from dataclasses import dataclass

# Identical in both sites today; shared here so a future tweak lands once.
DEFAULT_BASE_STYLE = """\
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
  #nav-menu.open { display: flex; }"""

# Tiny hamburger toggle, emitted after the header when nav is shown.
NAV_TOGGLE_SCRIPT = """\
<script>
document.getElementById('nav-toggle').addEventListener('click', function() {
  document.getElementById('nav-menu').classList.toggle('open');
});
</script>"""


@dataclass(frozen=True)
class SiteConfig:
    """Per-site chrome: everything render_head / render_header differ on between
    treestock and beestock. All trusted values, interpolated as-is.

    accent is the Tailwind colour token (e.g. "green", "yellow") used for the
    nav hover/active state and the logo wordmark -- the only colour that varies
    in the header.
    """
    site_name: str
    site_url: str
    tailwind_href: str       # href value for the stylesheet (treestock adds a ?v=DATE buster)
    plausible_script: str    # full analytics <script> block (differs per site)
    favicon_html: str        # full <link rel="icon" ...> line (attr order + value differ)
    logo_svg: str            # inline brand SVG shown in the header
    nav_items: list          # [(label, path), ...]; the "/" entry is the logo and is skipped
    accent: str = "green"
    default_max_width: str = "max-w-3xl"
    base_style: str = DEFAULT_BASE_STYLE


def render_head(
    config: SiteConfig,
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
    """Render the <head> block: meta, title, favicon, stylesheet, Plausible, styles.

    Bound to a SiteConfig per site (treestock_layout / beestock_layout).
    """
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

    style_block = f"<style>\n{config.base_style}"
    if extra_style:
        style_block += f"\n{extra_style}"
    style_block += "\n</style>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">{meta_desc}{canonical}{og_html}
<title>{title}</title>
{config.favicon_html}
<link href="{config.tailwind_href}" rel="stylesheet">
{config.plausible_script}
{style_block}
{extra_head}
</head>"""


def render_header(
    config: SiteConfig,
    subtitle: str = "",
    max_width: str = "",
    show_nav: bool = True,
    active_path: str = "",
    extra_right: str = "",
) -> str:
    """Render the sticky site header: brand logo, desktop nav, mobile hamburger.

    `subtitle` is accepted for call compatibility but unused (matches the prior
    treestock behaviour). `max_width` falls back to config.default_max_width when
    not given. Bound to a SiteConfig per site.
    """
    max_width = max_width or config.default_max_width
    accent = config.accent

    nav_section = ""
    nav_script = ""
    if show_nav:
        links = []
        for label, path in config.nav_items:
            if path == "/":
                continue  # Home link is the logo
            is_active = active_path and active_path.rstrip("/") == path.rstrip("/")
            active_cls = f" text-{accent}-800 font-semibold" if is_active else " text-gray-600"
            links.append(
                f'<a href="{path}" class="hover:text-{accent}-700 no-underline whitespace-nowrap{active_cls}">{label}</a>'
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
        nav_script = NAV_TOGGLE_SCRIPT

    right_section = extra_right or ""

    return f"""
<body class="bg-white text-gray-900">

<header class="border-b border-gray-200 bg-white sticky top-0 z-10">
  <div class="{max_width} mx-auto px-4 py-2">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <a href="/" class="flex items-center gap-2 no-underline flex-shrink-0">
        {config.logo_svg}
        <span class="text-lg font-bold text-{accent}-800">{config.site_name}</span>
      </a>{nav_section}{right_section}
    </div>
  </div>
</header>
{nav_script}"""
