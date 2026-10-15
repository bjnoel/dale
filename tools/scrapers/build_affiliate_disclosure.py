#!/usr/bin/env python3
"""
Build /affiliate-disclosure.html on treestock.com.au.

The page is generated FROM stocklib.utm.AFFILIATES, not written by hand, so the
public disclosure cannot fall out of date with what we actually earn commission
on. Adding a nursery to that dict adds it here on the next build; a disclosure
that lags the code is worse than no disclosure, because it reads as a promise.

Usage:
    python3 build_affiliate_disclosure.py /path/to/output/
"""

import sys
from pathlib import Path

from treestock_layout import render_page, CONTENT_MAX_WIDTH
from stocklib.registry import NURSERIES
from stocklib.utm import AFFILIATES

TITLE = "Affiliate disclosure"
DESCRIPTION = (
    "Which nurseries pay treestock.com.au a referral commission, and why that "
    "never affects search results or ordering."
)
CANONICAL = "https://treestock.com.au/affiliate-disclosure.html"

_NAMES = {n.key: n.name for n in NURSERIES}


def _nursery_name(nursery_key: str) -> str:
    """Display name, falling back to the key so a typo is visible rather than blank."""
    return _NAMES.get(nursery_key, nursery_key)


def build_rows() -> str:
    rows = []
    for domain, aff in sorted(AFFILIATES.items()):
        rows.append(
            '      <tr class="border-b border-gray-100">\n'
            f'        <td class="py-2 pr-4 font-medium">{_nursery_name(aff.nursery_key)}</td>\n'
            f'        <td class="py-2 pr-4 text-gray-600">{domain}</td>\n'
            f'        <td class="py-2 pr-4 text-gray-600">{aff.program}</td>\n'
            f'        <td class="py-2 text-gray-600">{aff.joined}</td>\n'
            '      </tr>'
        )
    return "\n".join(rows)


def build_body() -> str:
    count = len(AFFILIATES)
    total = len(NURSERIES)
    one = count == 1
    return f"""  <div class="max-w-2xl mx-auto py-8">
    <h1 class="text-2xl font-bold text-gray-800 mb-4">Affiliate disclosure</h1>

    <p class="text-gray-700 mb-4">
      treestock tracks stock and prices across {total} Australian nurseries.
      {'One of them pays' if one else f'{count} of them pay'} us a small commission
      when someone clicks through from here and buys something. Here's how that works.
    </p>

    <h2 class="text-lg font-semibold text-gray-800 mt-6 mb-2">
      It doesn't change the search results
    </h2>
    <p class="text-gray-700 mb-4">
      Results are sorted by price, stock and how well they match your search.
      Commission isn't part of that. No nursery can pay to rank higher, get listed,
      or stay listed. Prices come straight from each nursery's website and are
      checked every day, the same way for all of them.
    </p>
    <p class="text-gray-700 mb-4">
      There are no ads, sponsored listings or paid placements either. If nurseries
      could pay to move up the list, the list would be useless.
    </p>

    <h2 class="text-lg font-semibold text-gray-800 mt-6 mb-2">
      Who pays us
    </h2>
    <div class="overflow-x-auto">
      <table class="w-full text-sm mb-4">
        <thead>
          <tr class="border-b border-gray-300 text-left text-gray-500">
            <th class="py-2 pr-4 font-medium">Nursery</th>
            <th class="py-2 pr-4 font-medium">Site</th>
            <th class="py-2 pr-4 font-medium">Program</th>
            <th class="py-2 font-medium">Since</th>
          </tr>
        </thead>
        <tbody>
{build_rows()}
        </tbody>
      </table>
    </div>
    <p class="text-gray-700 mb-4">
      Links to {'this nursery' if one else 'these nurseries'} include
      <code class="text-xs bg-gray-100 px-1 py-0.5 rounded">ref=treestock</code>,
      which is how {'it knows' if one else 'they know'} an order came through us.
      We don't earn anything from the other {total - count}.
    </p>
    <p class="text-gray-700 mb-4">
      You'll also see
      <code class="text-xs bg-gray-100 px-1 py-0.5 rounded">utm_source=treestock</code>
      on every nursery link. That one has nothing to do with commission. It just
      shows up in the nursery's own website stats, so they can see how many visitors
      we send them.
    </p>
    <p class="text-gray-700 mb-4">
      None of this costs you anything. You pay exactly what you'd pay going to the
      nursery's website directly.
    </p>

    <h2 class="text-lg font-semibold text-gray-800 mt-6 mb-2">Why bother</h2>
    <p class="text-gray-700 mb-4">
      treestock costs money to run: a server, a domain, and a lot of time fixing
      scrapers whenever a nursery changes its website. It's been self-funded since it
      started in March 2026. A referral commission covers a bit of that without
      putting ads in front of you.
    </p>

    <p class="text-gray-600 text-sm mt-8">
      Questions? Email
      <a href="mailto:ben@treestock.com.au" class="underline">ben@treestock.com.au</a>.
    </p>
  </div>"""


def build_page() -> str:
    return render_page(
        title=TITLE,
        body=build_body(),
        description=DESCRIPTION,
        canonical_url=CANONICAL,
        max_width=CONTENT_MAX_WIDTH,
        show_nav=True,
        active_path="",
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: build_affiliate_disclosure.py /path/to/output/")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    output_dir.mkdir(parents=True, exist_ok=True)

    html = build_page()
    out_file = output_dir / "affiliate-disclosure.html"
    out_file.write_text(html)
    print(f"Written: {out_file} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
