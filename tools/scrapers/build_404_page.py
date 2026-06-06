#!/usr/bin/env python3
"""
Build the /404.html page on treestock.com.au.

Caddy serves this via a handle_errors block (see infrastructure/Caddyfile) for
any path that does not resolve to a real file, while preserving the 404 status
code. Absolute links (/, /species/, etc.) work from any missing URL.

Usage:
    python3 build_404_page.py /path/to/output/
"""

import sys
from pathlib import Path

from treestock_layout import render_page

# --- Copy (swap these two lines to change the message) ------------------------
HEADLINE = "This branch didn't take"
MESSAGE = (
    "The page you were after has been pruned, moved, or never took root. "
    "Let's get you back to something fruitful."
)
# -----------------------------------------------------------------------------

TITLE = "Page not found"
DESCRIPTION = "That page could not be found on treestock.com.au."
# noindex: a 404 should never be indexed, and we deliberately set no canonical.
NOINDEX = '<meta name="robots" content="noindex">'

LINKS = [
    ("Search stock", "/", True),
    ("Browse species", "/species/", False),
    ("Planting calendar", "/when-to-plant.html", False),
    ("Rare finds", "/rare.html", False),
]


def build_body() -> str:
    buttons = []
    for label, href, primary in LINKS:
        if primary:
            cls = ("bg-green-700 text-white px-4 py-2 rounded-lg text-sm "
                   "font-medium hover:bg-green-800 no-underline")
        else:
            cls = ("border border-gray-300 text-gray-700 px-4 py-2 rounded-lg "
                   "text-sm font-medium hover:bg-gray-50 no-underline")
        buttons.append(f'    <a href="{href}" class="{cls}">{label}</a>')
    button_row = "\n".join(buttons)
    return f"""  <div class="max-w-xl mx-auto text-center py-12">
    <p class="text-6xl font-bold text-green-700 mb-3">404</p>
    <h1 class="text-2xl font-bold text-gray-800 mb-3">{HEADLINE}</h1>
    <p class="text-gray-600 mb-8">{MESSAGE}</p>
    <div class="flex flex-wrap justify-center gap-3">
{button_row}
    </div>
  </div>"""


def build_page() -> str:
    return render_page(
        title=TITLE,
        body=build_body(),
        description=DESCRIPTION,
        canonical_url="",
        max_width="max-w-3xl",
        show_nav=True,
        active_path="",
        extra_head=NOINDEX,
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: build_404_page.py /path/to/output/")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    output_dir.mkdir(parents=True, exist_ok=True)

    html = build_page()
    out_file = output_dir / "404.html"
    out_file.write_text(html)
    print(f"Written: {out_file} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
