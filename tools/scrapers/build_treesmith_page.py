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

from treestock_layout import render_page


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
IOS_URL = "https://apps.apple.com/us/app/treesmith/id6761506742"
ANDROID_BETA_URL = "https://treesmith.app/beta/" + APP_UTM


def build_body() -> str:
    return f"""
<main class="max-w-3xl mx-auto px-4 py-6">

  <section class="text-center mb-10">
    <img src="/treesmith/icon.png" alt="Treesmith app icon"
         width="80" height="80"
         class="block w-20 h-20 mx-auto mb-4 rounded-2xl shadow">
    <h1 class="text-3xl sm:text-4xl font-bold text-gray-900 mb-3">
      Track the trees you buy from treestock
    </h1>
    <p class="text-lg text-gray-600 max-w-xl mx-auto mb-6">
      Treesmith is a mobile app for serious plant collectors. Catalog every
      tree, log grafts and harvests, capture growth photos over time. Built
      by the same person behind treestock.
    </p>
    <div class="flex gap-3 flex-wrap justify-center">
      <a href="{IOS_URL}"
         class="inline-block bg-gray-900 text-white px-6 py-3 rounded-lg text-base font-semibold shadow hover:bg-gray-800">
        Get it on iOS
      </a>
      <a href="{ANDROID_BETA_URL}"
         class="inline-block bg-white border border-gray-300 text-gray-800 px-6 py-3 rounded-lg text-base font-semibold hover:bg-gray-50">
        Android (beta)
      </a>
    </div>
    <p class="text-xs text-gray-400 mt-3">Free to use. Pro subscription unlocks unlimited plants and cloud backup.</p>
  </section>

  <section class="grid sm:grid-cols-3 gap-6 mb-12">
    <div>
      <img src="/treesmith/grid.png" alt="Plant grid view in Treesmith"
           class="w-full rounded-lg border border-gray-200 mb-3">
      <h2 class="text-base font-semibold text-gray-900 mb-1">Your collection at a glance</h2>
      <p class="text-sm text-gray-600">
        Every plant with photos, species, variety, source, and acquisition
        details. A personal botanical inventory you actually own.
      </p>
    </div>
    <div>
      <img src="/treesmith/detail.png" alt="Plant detail with photo timeline"
           class="w-full rounded-lg border border-gray-200 mb-3">
      <h2 class="text-base font-semibold text-gray-900 mb-1">Growth over time</h2>
      <p class="text-sm text-gray-600">
        Photo timelines for flowering, fruiting, new growth, and harvest. Each
        moment tagged and dated, kept against the plant.
      </p>
    </div>
    <div>
      <img src="/treesmith/activity.png" alt="Activity log in Treesmith"
           class="w-full rounded-lg border border-gray-200 mb-3">
      <h2 class="text-base font-semibold text-gray-900 mb-1">A full care history</h2>
      <p class="text-sm text-gray-600">
        Log water, prune, fertilise, repot, harvest, pest treatment, grafts.
        Build a complete record of how each tree has been managed.
      </p>
    </div>
  </section>

  <section class="bg-green-50 border border-green-200 rounded-lg p-6 mb-10">
    <h2 class="text-lg font-semibold text-green-900 mb-2">Why we built it</h2>
    <p class="text-sm text-green-900 mb-2">
      treestock tells you where to buy a rare variety. Treesmith helps you
      remember which one you bought, where it came from, when you grafted it,
      and how it has performed since.
    </p>
    <p class="text-sm text-green-900">
      If you have spent any time tracking a wishlist on treestock, you already
      know the problem Treesmith solves: a collection grows past what a
      spreadsheet or a Notes app can carry.
    </p>
  </section>

  <section class="mb-10">
    <h2 class="text-lg font-semibold text-gray-900 mb-3">Pricing</h2>
    <div class="grid sm:grid-cols-2 gap-4">
      <div class="border border-gray-200 rounded-lg p-5">
        <h3 class="text-base font-semibold text-gray-900 mb-2">Free</h3>
        <ul class="text-sm text-gray-700 space-y-1 list-disc pl-5">
          <li>Up to 30 plants</li>
          <li>One location</li>
          <li>Photos, activity log, GPS garden map</li>
          <li>Local export</li>
        </ul>
      </div>
      <div class="border border-green-300 bg-white rounded-lg p-5">
        <h3 class="text-base font-semibold text-green-900 mb-2">Pro</h3>
        <ul class="text-sm text-gray-700 space-y-1 list-disc pl-5">
          <li>Unlimited plants</li>
          <li>Multiple locations</li>
          <li>Cloud backup</li>
          <li>Reminders and bulk operations</li>
        </ul>
        <p class="text-xs text-gray-500 mt-3">Yearly subscription or one-time lifetime purchase.</p>
      </div>
    </div>
  </section>

  <section class="text-center mb-12">
    <a href="{APP_URL}"
       class="inline-block bg-green-700 text-white px-8 py-4 rounded-lg text-lg font-semibold shadow hover:bg-green-800 hover:shadow-md">
      See more at treesmith.app &rarr;
    </a>
  </section>

</main>
"""


def build_page() -> str:
    return render_page(
        title=TITLE,
        body=build_body(),
        description=DESCRIPTION,
        subtitle="",
        canonical_url=CANONICAL,
        max_width="max-w-3xl",
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
