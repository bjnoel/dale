"""
Copy and markup for a page whose products are gone: tombstones and redirect stubs.

A tombstone keeps a URL alive when no nursery is listing the thing any more. We
already do exactly this in the adjacent case, without calling it anything: a
product that is *listed* but out of stock renders "0 in stock", its last known
rows, and the notify-me form, and about 1,220 live variety pages are in that
state right now. The only difference from a deleted page is whether the nursery
kept the listing up, which to a collector is the same event. Per-variety alerts
became the product on 2026-08-15 (DEC-294), so unavailability is when the signup
is worth most, and it is exactly when we used to delete the page.

**This module renders three things only: the callout, the date sentence, and the
CTA slot.** Each family renders its own table, because a variety tombstone's rows
are listings of one cultivar and a combo's are up to 60 products spanning many
cultivars. Sharing the table would grow a `mode=` parameter within a month, which
is the thing stocklib exists to prevent.

Two constraints that are defects rather than tradeoffs if broken:

- **No email capture on a combo tombstone.** Species-level watches were removed
  deliberately. DEC-294 found a "watch this species" banner POSTing an action the
  server never had, silently enrolling people in the digest while telling them
  they were watching a species. The combo CTA is links, never a form.
- **The soft-404 shape matters more than the words.** Lead with the variety, not
  with the absence: the H1 is unchanged and the callout sits *below* the blurb.
  A page whose first 200 words are a variety description is not a soft 404 to any
  classifier. The date sentence exists because it is unique, factual and
  per-page, and only 34 of the 2,512 dead URLs have a written blurb.

No em dashes in any copy here (house rule).
"""
from __future__ import annotations

from datetime import date

from .page_ledger import REDIRECT, TOMBSTONE, page_state_meta
from .templates import render as render_template

# Variety links listed on a combo tombstone. Long enough to be genuinely useful
# to someone who wanted that species, short enough not to become a link farm.
MAX_COMBO_CTA_LINKS = 12


def format_date(value: str | None) -> str:
    """2026-05-01 -> "1 May 2026". The empty string for anything unparseable,
    so a caller can test the result rather than handling an exception."""
    try:
        return date.fromisoformat(value).strftime("%-d %B %Y")
    except (TypeError, ValueError):
        return ""


def format_date_range(first: str | None, last: str | None) -> tuple[str, str]:
    """A pair of dates with the redundant year dropped: ("5 March", "1 May 2026").

    Only when both fall in the same year, and never on the second date, so the
    reader always gets a year without having to carry one across the sentence.
    """
    start, end = format_date(first), format_date(last)
    if start and end and start.rsplit(" ", 1)[-1] == end.rsplit(" ", 1)[-1]:
        start = start.rsplit(" ", 1)[0]
    return start, end


def format_price(value) -> str:
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return ""


def last_stock_sentence(entry: dict) -> str:
    """"It was last in stock on 1 May 2026 at Daleys for $49.00."

    Degrades a clause at a time: without a price, without a nursery, and finally
    to nothing at all if we never saw it in stock. A page that says "last in
    stock on" with no date is worse than a page that does not mention it.
    """
    when = format_date(entry.get("last_in_stock"))
    if not when:
        return ""
    rows = entry.get("rows") or []
    priced = [r for r in rows if r.get("available") and r.get("price")]
    row = priced[0] if priced else (rows[0] if rows else None)
    if not row:
        return f"It was last in stock on {when}."
    nursery = row.get("nursery_name") or row.get("nursery_key") or ""
    price = format_price(row.get("price"))
    if nursery and price:
        return f"It was last in stock on {when} at {nursery} for {price}."
    if nursery:
        return f"It was last in stock on {when} at {nursery}."
    return f"It was last in stock on {when}."


def tracking_sentence(entry: dict) -> str:
    """"We tracked it at 1 nursery between 5 March and 1 May 2026, in stock on
    44 of those 58 days."

    The unique, factual, per-page sentence. `live_days` is a count of nights we
    generated the page, not the span between the dates, because the pipeline
    misses nights and claiming otherwise would be a small lie repeated 2,500
    times.
    """
    first, last = format_date_range(entry.get("first_seen"),
                                    entry.get("last_seen"))
    if not first or not last:
        return ""
    nurseries = len({r.get("nursery_key") for r in (entry.get("rows") or [])
                     if r.get("nursery_key")})
    where = (f"at {nurseries} nurser{'y' if nurseries == 1 else 'ies'} "
             if nurseries else "")
    when = (f"between {first} and {last}"
            if entry.get("first_seen") != entry.get("last_seen")
            else f"on {last}")
    sentence = f"We tracked it {where}{when}"
    live_days = int(entry.get("live_days") or 0)
    in_stock_days = int(entry.get("in_stock_days") or 0)
    if live_days:
        sentence += f", in stock on {in_stock_days} of those {live_days} days"
    return sentence + "."


def headline_sentence(name: str, entry: dict) -> str:
    """Why this page is a dead end, in the reader's terms.

    Two different things end a page and only one of them is about stock. A page
    can end because nobody lists the plant any more, or because we decided the
    slug was never a distinct variety (a deny, or the taxonomy gate). Saying
    "no nursery is currently listing Male Kiwifruit" for the second is simply
    false: several nurseries list it, we just stopped calling it a cultivar.
    """
    if entry.get("retired_reason"):
        return f"We no longer track {name} as a separate variety."
    return f"No nursery we track is currently listing {name}."


def render_tombstone(name: str, entry: dict, *, cta_html: str = "") -> str:
    """The shared tombstone block for either family.

    `name` is what the page is about, in the reader's words ("Mahan (B) Pecan",
    "Feijoa trees in Western Australia"). `cta_html` is the family's slot:
    variety leaves it empty because the page's existing watch form already sits
    below and posts to a working endpoint, combo fills it with links.
    """
    # A page retired by curation has no meaningful "last in stock": its products
    # are usually still for sale under another name, so the date would sit
    # directly under a headline saying the opposite. The tracking sentence is
    # past tense and stays true either way.
    last_stock = "" if entry.get("retired_reason") else last_stock_sentence(entry)
    return render_template(
        "tombstone_block.html.j2",
        name=name,
        headline=headline_sentence(name, entry),
        last_stock=last_stock,
        tracking=tracking_sentence(entry),
        cta_html=cta_html,
    )


def combo_cta_html(species_name: str, *, variety_links: list[dict] = (),
                   species_href: str = "", state_links: list[dict] = (),
                   hub_href: str = "", hub_label: str = "") -> str:
    """The combo tombstone's CTA slot: links, and never a form.

    Degrades deliberately, because the slot can legitimately be empty: feijoa WA
    tombstones precisely because there is no feijoa in WA, so there are no
    variety links to offer. Falls back to the species page, then to the state
    hub, and renders nothing at all rather than an empty box.

    `variety_links` are dicts of {href, label, in_stock}; in-stock ones lead,
    since they are the useful answer for someone who wanted this species.
    """
    ordered = sorted(variety_links, key=lambda v: (not v.get("in_stock"),
                                                   v.get("label", "")))
    return render_template(
        "combo_tombstone_cta.html.j2",
        species_name=species_name,
        variety_links=ordered[:MAX_COMBO_CTA_LINKS],
        species_href=species_href,
        state_links=state_links,
        hub_href=hub_href,
        hub_label=hub_label or "all states",
    )


def stub_head_extras(target_url: str) -> str:
    """The <head> additions that make a redirect stub redirect.

    Passed to render_head(extra_head=...) along with canonical_url=target_url,
    so the canonical, the Open Graph URL and the refresh all agree without this
    module reaching into the site chrome.

    Two rules, both settled elsewhere and both easy to undo by accident:

    - **No noindex.** DEC-266 tested noindex on variety URLs and refuted it, and
      a page that both noindexes and canonicals elsewhere is a self-contradicting
      signal.
    - **No watch form** (enforced by the template, not here). A watch on a dead
      slug never fires, because the alert sender looks up watches by the slug
      that is generated. A form there is the DEC-294 shape exactly: a control
      that looks like it works and does not.
    """
    return (f'<meta http-equiv="refresh" content="0; url={target_url}">\n'
            f'{page_state_meta(REDIRECT)}')


def render_stub(*, head: str, header: str, footer: str, title: str,
                target_title: str, target_href: str,
                content_max_width: str = "max-w-3xl",
                heading: str | None = None, lede: str | None = None) -> str:
    """A redirect stub: 200, meta refresh, and a visible link.

    The visible link is not decoration. A stub returns 200, so anyone with meta
    refresh disabled, and every crawler that does not follow it, sees only what
    is on the page.

    Generated HTML rather than a Caddy redirect on purpose: a nightly
    root-privileged config write plus a reload has every domain we serve in its
    blast radius, and it would make the weekly config-drift snapshot email drift
    every Monday, training us to ignore drift alerts. The honest cost is that a
    meta refresh consolidates more slowly than a 301, and that monitoring asking
    "is this a 404" now says fine. If Search Console still shows the old URLs
    after 60 days, escalate to real 301s.
    """
    # heading/lede default to the variety wording this stub was written for,
    # byte for byte, so the variety goldens are unaffected. A compare page
    # redirects for a different reason (too few nurseries left to compare, not
    # a rename) and saying "we track this variety under a single name now"
    # there would be false. Copy is a parameter; the shape is not.
    return render_template(
        "redirect_stub.html.j2",
        head=head, header=header, footer=footer,
        title=title, target_title=target_title, target_href=target_href,
        content_max_width=content_max_width,
        heading=heading or f"{title} is now listed as {target_title}",
        lede=lede or "We track this variety under a single name now. Taking you there.",
    )


def tombstone_head_extras() -> str:
    """The <head> addition marking a page as a tombstone."""
    return page_state_meta(TOMBSTONE)
