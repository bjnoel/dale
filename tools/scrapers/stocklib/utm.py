"""
UTM tagging for outbound nursery links.

Every link from treestock to a nursery's site should carry
utm_source=treestock plus a utm_medium naming the page type it came from, so
nurseries can see in their own analytics how much traffic treestock sends them
(goodwill/outreach currency), and so our Plausible outbound-click events can be
attributed by page type from the href alone.

This was forked as a one-liner across builders and email senders (each with a
slightly different medium); import this instead of copying it. Click *events*
are separate: script.outbound-links.js in treestock_layout.render_head handles
those on every page.

Do NOT tag citation/source links (gov sites, references) — UTM is for nursery
product/store links only.

Affiliate refs are separate from UTM and are the only thing here that earns
money: see AFFILIATES below.
"""
import re
from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True)
class Affiliate:
    """A nursery that pays us commission on a completed sale."""
    ref: str          # the ref code the nursery's affiliate software issued us
    nursery_key: str  # stocklib.registry key, so the disclosure can name them
    program: str      # what the nursery calls it, for the disclosure page
    joined: str       # ISO date, for the disclosure page


# The ONLY place a referral relationship is declared, keyed by the domain that
# appears in that nursery's product URLs.
#
# Everything that emits a nursery link routes through affiliate(), so a new
# agreement is one line here rather than a sweep. That includes the two
# JavaScript link builders (static/dashboard.js and
# templates/history_page.html.j2), which deliberately do NOT carry their own
# copy: their URLs are tagged in Python before being serialised into the page,
# precisely so this list cannot fork.
#
# /affiliate-disclosure.html is generated FROM this dict (build_affiliate_
# disclosure.py), so the public disclosure cannot silently fall out of date with
# what we actually earn on. Adding a nursery here updates the disclosure.
#
# Standing rule, from Benedict, 2026-08-10: search ranking and result ordering
# NEVER take commission into account. Sorting is on list price and stock alone.
# The moment that stops being true the site stops being worth using, and the
# dataset is the whole moat.
AFFILIATES: dict[str, Affiliate] = {
    "primalfruits.com.au": Affiliate(
        ref="treestock",
        nursery_key="primal-fruits",
        program="Primal Club",
        joined="2026-08-10",
    ),
}

# Derived, so it cannot drift from AFFILIATES.
AFFILIATE_REFS = {domain: a.ref for domain, a in AFFILIATES.items()}


def affiliate(url: str) -> str:
    """Return `url` with the nursery's affiliate ref appended, if we have one.

    A no-op for the 26 nurseries with no referral agreement, and idempotent, so
    it is safe to call on a URL that may already have been tagged.

    This is deliberately separate from outbound(): the JS link builders append
    their own UTM client-side, but must never build the ref themselves, so their
    URLs get affiliate() applied server-side and UTM applied in the browser.
    """
    if not url:
        return ""
    for domain, ref in AFFILIATE_REFS.items():
        if domain not in url:
            continue
        if f"?ref={ref}" in url or f"&ref={ref}" in url:
            return url
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}ref={ref}"
    return url


def outbound(url: str, medium: str, campaign: str = "") -> str:
    """Return `url` with utm_source=treestock&utm_medium=<medium> appended,
    preserving any existing query string. Empty url passes through unchanged.

    Also applies affiliate(), so every tagged outbound link earns commission
    where an agreement exists."""
    if not url:
        return ""
    url = affiliate(url)
    sep = "&" if "?" in url else "?"
    tagged = f"{url}{sep}utm_source=treestock&utm_medium={medium}"
    if campaign:
        tagged += f"&utm_campaign={campaign}"
    return tagged


# TreeSmith store links. The stores ignore utm_* on a listing URL: Apple
# attributes App Store downloads only by provider token (pt) plus campaign
# token (ct), and Play only by utm_* packed inside an encoded referrer= param.
# Same format as treesmith.app's storeLinks() (src/lib/urls.ts), so both sites'
# downloads land in the same App Store Connect / Play Console campaign reports.
# No /au/ storefront: on an iPhone Apple hands off to the App Store app in the
# reader's own storefront; a desktop browser lands on the /us/ web page.
TREESMITH_APPLE_ID = "6761506742"
TREESMITH_APPLE_PT = "128328374"
TREESMITH_PLAY_ID = "app.treesmith"
_CT_RE = re.compile(r"^[a-z0-9-]{1,40}$")


def treesmith_store_links(ct: str, medium: str) -> tuple[str, str]:
    """Return (apple_url, play_url) attributed to treestock under campaign `ct`.

    `ct` is Apple's campaign token (max 40 chars, a-z0-9 and hyphens) and is
    reused as Play's utm_campaign so one token names the surface in both
    consoles. `medium` is the treestock surface (treesmith_page, email)."""
    if not _CT_RE.match(ct):
        raise ValueError(f"invalid App Store campaign token: {ct!r}")
    apple = (f"https://apps.apple.com/app/id{TREESMITH_APPLE_ID}"
             f"?pt={TREESMITH_APPLE_PT}&ct={ct}&mt=8")
    referrer = f"utm_source=treestock&utm_medium={medium}&utm_campaign={ct}"
    play = (f"https://play.google.com/store/apps/details?id={TREESMITH_PLAY_ID}"
            f"&referrer={quote(referrer, safe='')}")
    return apple, play
