"""
Shared personalised email footer for treestock + beestock digests and alerts.

Single source of truth for the unsubscribe + preferences links that every
subscriber email must carry (Australian Spam Act compliance). Previously
duplicated in send_digest.py (daily) and send_weekly_digest.py (weekly); the
two copies produced the same URLs but used different separators and could drift
(a compliance link or path changed in one but not the other). Centralised here
and pinned by tests/test_email_footer.py.

The default site_url is treestock; pass site_url= for beestock or other sites.
"""
from __future__ import annotations

import urllib.parse

DEFAULT_SITE_URL = "https://treestock.com.au"


def footer_urls(email: str, token: str, site_url: str = DEFAULT_SITE_URL) -> tuple[str, str]:
    """Return (unsubscribe_url, preferences_url) for a subscriber.

    The email is URL-encoded; the token authenticates the unsubscribe/preferences
    request server-side (see subscribe_server.py).
    """
    encoded_email = urllib.parse.quote(email)
    unsubscribe_url = f"{site_url}/unsubscribe.html?email={encoded_email}&token={token}"
    preferences_url = f"{site_url}/api/preferences?email={encoded_email}&token={token}"
    return unsubscribe_url, preferences_url


def _state_label(state: str) -> str:
    return f"Filtered to: {state}" if state != "ALL" else "Showing: all states"


def inject_footer(html: str, email: str, token: str, state: str,
                  site_url: str = DEFAULT_SITE_URL) -> str:
    """Append the personalised HTML footer (unsubscribe + preferences links).

    Inserts before </body> if present, else appends to the end. Spam Act
    compliant: every email carries a working unsubscribe link and identifies
    the sender.
    """
    unsubscribe_url, preferences_url = footer_urls(email, token, site_url)
    state_label = _state_label(state)
    footer = f"""
<hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb">
<p style="font-size:0.75em;color:#9ca3af;text-align:center">
  You're receiving this because you subscribed at <a href="{site_url}" style="color:#6b7280">{site_url}</a>.<br>
  {state_label} &middot; <a href="{preferences_url}" style="color:#6b7280">Manage your alerts</a> &middot; <a href="{unsubscribe_url}" style="color:#6b7280">Unsubscribe</a>
</p>
"""
    if "</body>" in html:
        return html.replace("</body>", footer + "</body>", 1)
    return html + footer


def inject_text_footer(text: str, email: str, token: str, state: str,
                       site_url: str = DEFAULT_SITE_URL) -> str:
    """Append the plain-text footer (unsubscribe + preferences links)."""
    unsubscribe_url, preferences_url = footer_urls(email, token, site_url)
    state_label = _state_label(state)
    return (
        text
        + f"\n\n---\nYou're receiving this because you subscribed at {site_url}.\n"
        + f"{state_label}\n"
        + f"Manage your alerts: {preferences_url}\n"
        + f"Unsubscribe: {unsubscribe_url}\n"
    )
