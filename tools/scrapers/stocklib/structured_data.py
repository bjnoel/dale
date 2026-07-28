"""
schema.org JSON-LD builders for the stock sites.

Pure functions that each return a ready
'<script type="application/ld+json">...</script>' string (the same contract as
growing_guides.faq_jsonld), so callers drop them into render_head(jsonld=...) or
append them in the body. Kept out of stocklib/layout.py so the render_head /
render_header anti-fork guard (tests/test_no_forking.py) is unaffected.

Site-agnostic: the site URL/name are passed in. treestock_layout binds the
treestock values (see render_breadcrumb, organization_jsonld, website_jsonld
there). No em or en dashes in any emitted copy (CLAUDE.md copy rule).
"""
import json


def _script(data) -> str:
    return '<script type="application/ld+json">\n' + json.dumps(data, indent=2) + "\n</script>"


def _abs_url(url: str, site_url: str) -> str:
    """Make a breadcrumb url absolute. Empty stays empty (current-page crumb)."""
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return site_url + url
    return f"{site_url}/{url}"


def drop_linkless_crumbs(crumbs: list) -> list:
    """Drop any non-final crumb that has no url.

    Google requires "item" on every breadcrumb EXCEPT the last one ("If the
    breadcrumb is the last item in the breadcrumb trail, item is not required").
    A linkless crumb in the middle of the trail therefore emits a ListItem with no
    "item", which Search Console reports as the critical error "Missing field
    'item' (in 'itemListElement')". It is also useless to a reader: the nav would
    render it as <a href="">, a dead link back to the current page.

    Callers pass an empty url to mean "no page exists for this level" (e.g.
    build_variety_pages, when the species has no species page). Dropping the crumb
    is the honest rendering of that. The trailing crumb keeps its empty url: it is
    the current page, and Google falls back to the containing page's URL.

    Shared by breadcrumb_jsonld and treestock_layout.render_breadcrumb so the
    visible trail and the markup always agree, per Google's breadcrumb guidance.
    """
    return [
        (label, url) for i, (label, url) in enumerate(crumbs)
        if url or i == len(crumbs) - 1
    ]


def breadcrumb_jsonld(crumbs: list, site_url: str) -> str:
    """BreadcrumbList from the same (label, url) tuples render_breadcrumb takes.

    The last crumb is the current page and conventionally has an empty url, so it
    is emitted without an "item". Linkless crumbs earlier in the trail are dropped
    (see drop_linkless_crumbs) and positions renumbered over what remains.
    """
    items = []
    for i, (label, url) in enumerate(drop_linkless_crumbs(crumbs)):
        item = {"@type": "ListItem", "position": i + 1, "name": label}
        abs_url = _abs_url(url, site_url)
        if abs_url:
            item["item"] = abs_url
        items.append(item)
    return _script({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": items,
    })


def organization_jsonld(site_url: str, site_name: str, description: str = "",
                        same_as: list | None = None, logo: str = "") -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": site_name,
        "url": site_url + "/",
        "logo": logo or f"{site_url}/og-image.png",
    }
    if description:
        data["description"] = description
    if same_as:
        data["sameAs"] = same_as
    return _script(data)


def website_jsonld(site_url: str, site_name: str) -> str:
    """WebSite node for the homepage.

    No potentialAction/SearchAction: the homepage has no ?q= query endpoint yet
    (dashboard.js reads only ?nursery=), and Google requires the searchbox
    target to be a working URL. Add a SearchAction here once a ?q= handler ships.
    """
    return _script({
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": site_name,
        "url": site_url + "/",
        "publisher": {"@type": "Organization", "name": site_name},
    })


def _product_offers(products: list, currency: str = "AUD") -> tuple[list, list]:
    """Build one Offer per nursery listing, using the price the page displays.

    The variety/species/compare pages show a single price per nursery (the
    cheapest variant), so each nursery becomes one Offer at that visible price.
    Emitting per-pot-size offers would put prices in the markup that are not shown
    on the page, which Google flags as inconsistent. Deduped by product URL.
    Returns (offers, prices) with prices as floats for the AggregateOffer range.
    """
    seen = set()
    offers: list = []
    prices: list = []
    for p in products:
        price = p.get("price")
        if not price:
            continue
        url = p.get("url", "")
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        price_f = round(float(price), 2)
        prices.append(price_f)
        offer = {
            "@type": "Offer",
            "price": f"{price_f:.2f}",
            "priceCurrency": currency,
            "availability": (
                "https://schema.org/InStock" if p.get("available") else "https://schema.org/OutOfStock"
            ),
        }
        if url:
            offer["url"] = url
        seller = p.get("nursery_name", "")
        if seller:
            offer["seller"] = {"@type": "Organization", "name": seller}
        offers.append(offer)
    return offers, prices


def product_offer_jsonld(name: str, url: str, products: list, description: str = "",
                         currency: str = "AUD", include_offers: bool = True) -> str:
    """Product + AggregateOffer JSON-LD for a cultivar/species page.

    lowPrice/highPrice/offerCount are computed from the per-nursery offers (each
    at the price the page shows). Returns "" when no listing has a price (so no
    empty offer block triggers a Search Console "missing price" warning).

    include_offers=True embeds the individual Offer list (right for a cultivar
    page with a handful of sellers). Set it False on aggregation pages (a species
    or compare page can span hundreds of listings) to emit the AggregateOffer
    summary only (priceCurrency/lowPrice/highPrice/offerCount), which avoids
    bloating the page with hundreds of Offer objects.
    """
    offers, prices = _product_offers(products, currency)
    if not offers or not prices:
        return ""
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
    }
    if description:
        data["description"] = description
    if url:
        data["url"] = url
    agg = {
        "@type": "AggregateOffer",
        "priceCurrency": currency,
        "lowPrice": f"{min(prices):.2f}",
        "highPrice": f"{max(prices):.2f}",
        "offerCount": len(offers),
    }
    if include_offers:
        agg["offers"] = offers
    data["offers"] = agg
    return _script(data)
