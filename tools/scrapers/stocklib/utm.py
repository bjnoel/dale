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
"""


def outbound(url: str, medium: str, campaign: str = "") -> str:
    """Return `url` with utm_source=treestock&utm_medium=<medium> appended,
    preserving any existing query string. Empty url passes through unchanged."""
    if not url:
        return ""
    sep = "&" if "?" in url else "?"
    tagged = f"{url}{sep}utm_source=treestock&utm_medium={medium}"
    if campaign:
        tagged += f"&utm_campaign={campaign}"
    return tagged
