#!/usr/bin/env python3
"""
Build the /treesmith.html landing page on treestock.com.au.

A dedicated pitch page for the Treesmith mobile app, framed for the treestock
audience: "you already track varieties on treestock, now track the ones you
bought." Inbound CTAs from the footer, subscription confirmation page, and
welcome email all link here, then this page links out to treesmith.app and
the app stores. Outbound clicks are tagged with UTM for Plausible.

Usage:
    python3 build_treesmith_page.py /path/to/output/
"""

import sys
from pathlib import Path

from stocklib.templates import render as render_template
from treestock_layout import render_page, CONTENT_MAX_WIDTH


TITLE = "Treesmith, the plant-tracking app for collectors"
DESCRIPTION = (
    "Treesmith is a mobile app for serious plant collectors. Catalog every "
    "tree, log grafts and harvests, capture photos over time. Free on iOS, "
    "Android in beta."
)
CANONICAL = "https://treestock.com.au/treesmith.html"
OG_IMAGE = "https://treestock.com.au/treesmith/grid.png"

APP_BASE = "https://treesmith.app/"
APP_UTM = "?utm_source=treestock&utm_medium=treesmith_page&utm_campaign=treesmith_launch"
APP_URL = APP_BASE + APP_UTM
IOS_URL = "https://apps.apple.com/us/app/treesmith/id6761506742?utm_source=treestock&utm_medium=treesmith_page&utm_campaign=treesmith_launch"
ANDROID_BETA_URL = "https://treesmith.app/beta/" + APP_UTM


def build_body() -> str:
    # Body lives in stocklib/templates/treesmith_page.html.j2 (autoescaped).
    # The only interpolated values are trusted app URLs; autoescape turns the
    # raw `&` in their UTM query strings into a valid `&amp;` in the href.
    return render_template(
        "treesmith_page.html.j2",
        ios_url=IOS_URL,
        android_beta_url=ANDROID_BETA_URL,
        app_url=APP_URL,
    )


def build_page() -> str:
    return render_page(
        title=TITLE,
        body=build_body(),
        description=DESCRIPTION,
        subtitle="",
        canonical_url=CANONICAL,
        max_width=CONTENT_MAX_WIDTH,
        show_nav=True,
        active_path="",
        og_title="Treesmith, the plant-tracking app for collectors",
        og_description=DESCRIPTION,
        og_image=OG_IMAGE,
        og_type="website",
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: build_treesmith_page.py /path/to/output/")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    output_dir.mkdir(parents=True, exist_ok=True)

    html = build_page()
    out_file = output_dir / "treesmith.html"
    out_file.write_text(html)
    print(f"Written: {out_file} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
