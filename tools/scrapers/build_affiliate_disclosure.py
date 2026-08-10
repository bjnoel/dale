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
      treestock.com.au tracks stock and prices across {total} Australian nurseries.
      {'One of them pays' if one else f'{count} of them pay'} us a commission when
      someone we send {'them' if one else 'to them'} buys something. Everything below
      is what that does and does not mean.
    </p>

    <h2 class="text-lg font-semibold text-gray-800 mt-6 mb-2">
      Search results are never affected
    </h2>
    <p class="text-gray-700 mb-4">
      This is the important one. Results are ordered on price, stock and how well
      they match what you searched for. Commission is not an input, and no nursery
      can pay to rank higher, to be listed, or to stay listed. The prices shown are
      the nursery's own list prices, collected daily, the same way for every nursery
      whether they pay us or not.
    </p>
    <p class="text-gray-700 mb-4">
      There are no ads on this site, no sponsored rows and no paid placement. We
      have turned those down before, and the reason is self-interested as much as
      ethical: the only thing this site is worth anything for is being accurate
      about who has what and for how much.
    </p>

    <h2 class="text-lg font-semibold text-gray-800 mt-6 mb-2">
      {'The nursery' if one else 'The nurseries'} we earn from
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
      Links to {'this nursery' if one else 'these nurseries'} carry a
      <code class="text-xs bg-gray-100 px-1 py-0.5 rounded">ref</code> parameter so
      they can tell the sale came from here. Links to the other
      {total - count} nurseries carry no such parameter and earn us nothing. Every
      outbound link also carries a
      <code class="text-xs bg-gray-100 px-1 py-0.5 rounded">utm_source=treestock</code>
      tag, which is not a commission arrangement: it just lets a nursery see in
      their own analytics how much traffic we send them.
    </p>
    <p class="text-gray-700 mb-4">
      You never pay more because of it. The commission comes out of the nursery's
      margin, not off your price, and the price you see here is the price they
      charge everyone.
    </p>

    <h2 class="text-lg font-semibold text-gray-800 mt-6 mb-2">Why we do it at all</h2>
    <p class="text-gray-700 mb-4">
      Running this site costs money (a server, a domain, and the time to keep 27
      scrapers working). It has been funded out of pocket since March 2026.
      Referral commission is the least intrusive way we found to cover that:
      nothing on the page changes, nobody's results move, and it only pays when
      someone actually buys a tree they were already looking for.
    </p>
    <p class="text-gray-700 mb-4">
      If that ever stops being true, this page changes first.
    </p>

    <p class="text-gray-600 text-sm mt-8">
      Questions about any of this, email
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
