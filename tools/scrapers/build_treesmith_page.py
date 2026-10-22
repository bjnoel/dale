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
from stocklib.utm import treesmith_store_links
from treestock_layout import render_page, CONTENT_MAX_WIDTH


TITLE = "Treesmith, the plant-tracking app for collectors"
DESCRIPTION = (
    "Treesmith is a mobile app for serious plant collectors. Catalog every "
    "tree, log grafts and harvests, capture photos over time. Free on iOS "
    "and Android."
)
CANONICAL = "https://treestock.com.au/treesmith.html"
OG_IMAGE = "https://treestock.com.au/treesmith/grid.png"

APP_BASE = "https://treesmith.app/"
UTM_PARAMS = "utm_source=treestock&utm_medium=treesmith_page&utm_campaign=treesmith_launch"
APP_UTM = "?" + UTM_PARAMS
APP_URL = APP_BASE + APP_UTM
# Store links carry the stores' own attribution (pt/ct for Apple, an encoded
# referrer for Play), since both ignore the utm_* above. See stocklib.utm.
IOS_URL, ANDROID_URL = treesmith_store_links("treestock", "treesmith_page")

# Deep links for the grafting section. Readers arriving from the variety and
# rootstock promo blocks came here for grafting, not for a feature list.
GRAFTING_TECHNIQUES_URL = (
    "https://treesmith.app/grafting-techniques/?" + UTM_PARAMS
    + "&utm_content=grafting_techniques"
)
GRAFT_TRACKING_URL = (
    "https://treesmith.app/graft-tracking/?" + UTM_PARAMS
    + "&utm_content=graft_tracking"
)


def build_body() -> str:
    # Body lives in stocklib/templates/treesmith_page.html.j2 (autoescaped).
    # The only interpolated values are trusted app URLs; autoescape turns the
    # raw `&` in their UTM query strings into a valid `&amp;` in the href.
    return render_template(
        "treesmith_page.html.j2",
        ios_url=IOS_URL,
        android_url=ANDROID_URL,
        app_url=APP_URL,
        grafting_techniques_url=GRAFTING_TECHNIQUES_URL,
        graft_tracking_url=GRAFT_TRACKING_URL,
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
