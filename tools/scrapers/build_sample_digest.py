#!/usr/bin/env python3
"""
Build /sample-digest.html — a preview page showing what email subscribers receive daily.

This is used to improve signup conversion by letting visitors see a real example
before committing their email address.

Usage:
    python3 build_sample_digest.py /path/to/dashboard/

Reads digest-email.html (today's email) and wraps it in a conversion-focused page.
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DASHBOARD_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/opt/dale/dashboard")
SUBSCRIBE_API = "https://treestock.com.au/api/subscribe"

# Get nursery count from shipping module
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from shipping import SHIPPING_MAP
    NURSERY_COUNT = len(SHIPPING_MAP)
except Exception:
    NURSERY_COUNT = 15  # fallback

from stocklib.templates import render as render_template


def make_subscribe_form(form_id="subscribeForm", email_id="subEmail", btn_id="subBtn", msg_id="subMsg", state_id="subState", nursery_count=15):
    return f"""
<div class="subscribe-box">
  <p class="box-heading">Get this in your inbox every day — free</p>
  <p class="box-sub">Daily stock alerts: price drops, restocks, and new arrivals across {nursery_count} Australian nurseries. Unsubscribe any time.</p>
  <form id="{form_id}" class="sub-form">
    <input type="email" id="{email_id}" placeholder="your@email.com" required class="sub-input">
    <select id="{state_id}" class="sub-input" style="flex:0 0 auto;width:auto;min-width:0">
      <option value="ALL">All states</option>
      <option value="NSW">NSW</option><option value="VIC">VIC</option>
      <option value="QLD">QLD</option><option value="WA">WA</option>
      <option value="SA">SA</option><option value="TAS">TAS</option>
      <option value="NT">NT</option><option value="ACT">ACT</option>
    </select>
    <button type="submit" id="{btn_id}" class="sub-btn">Subscribe free</button>
  </form>
  <p id="{msg_id}" class="sub-msg"></p>
</div>
"""


def make_subscribe_js(form_id, email_id, btn_id, msg_id, state_id="subState"):
    return f"""
<script>
document.getElementById('{form_id}').addEventListener('submit', async function(e) {{
  e.preventDefault();
  const email = document.getElementById('{email_id}').value.trim();
  const stateEl = document.getElementById('{state_id}');
  const state = stateEl ? stateEl.value : 'ALL';
  const btn = document.getElementById('{btn_id}');
  const msg = document.getElementById('{msg_id}');
  if (!email) return;
  btn.disabled = true;
  btn.textContent = 'Subscribing...';
  try {{
    const resp = await fetch('{SUBSCRIBE_API}', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{email, state}})
    }});
    const data = await resp.json();
    if (resp.ok) {{
      document.getElementById('{form_id}').style.display = 'none';
      msg.style.color = '#065f46';
      msg.textContent = data.message === 'Already subscribed'
        ? "You're already subscribed!"
        : '\\u2713 Subscribed! Check your inbox tomorrow morning.';
    }} else {{
      btn.disabled = false;
      btn.textContent = 'Subscribe free';
      msg.style.color = '#dc2626';
      msg.textContent = data.message || 'Something went wrong. Try again.';
    }}
  }} catch (err) {{
    btn.disabled = false;
    btn.textContent = 'Subscribe free';
    msg.style.color = '#dc2626';
    msg.textContent = 'Network error. Please try again.';
  }}
  msg.classList.remove('hidden');
}});
</script>
"""


def extract_email_body(html: str) -> str:
    """Extract the inner body content from the email HTML."""
    match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    html = re.sub(r'<!DOCTYPE[^>]*>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'<html[^>]*>|</html>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'<head>.*?</head>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<body[^>]*>|</body>', '', html, flags=re.IGNORECASE)
    return html.strip()


def extract_highlights(email_html: str) -> dict:
    """
    Extract positive items (restocks, price drops, new arrivals) from email HTML.
    Returns dict with keys 'restocks', 'price_drops', 'new_items', each a list of li HTML strings.
    """
    li_pattern = re.compile(r'<li[^>]*>.*?</li>', re.DOTALL)
    restocks = []
    price_drops = []
    new_items = []

    for m in li_pattern.finditer(email_html):
        li_html = m.group(0)
        li_text = li_html  # keep HTML for rendering
        if 'Back in stock' in li_html or ('✅' in li_html and 'Back in stock' in li_html):
            restocks.append(li_html)
        elif '📉' in li_html:
            price_drops.append(li_html)
        elif '🆕' in li_html:
            new_items.append(li_html)

    return {
        'restocks': restocks,
        'price_drops': price_drops,
        'new_items': new_items,
    }


def build_highlights_section(highlights: dict, max_each: int = 4) -> str:
    """Build a highlights section HTML from extracted items."""
    restocks = highlights['restocks'][:max_each]
    price_drops = highlights['price_drops'][:max_each]
    new_items = highlights['new_items'][:max_each]

    total = len(restocks) + len(price_drops) + len(new_items)
    if total == 0:
        return ""

    parts = []

    if restocks:
        li_html = '\n'.join(f'<li style="padding:5px 0;border-bottom:1px solid #d1fae5;last-child:border-0">{li}</li>' for li in restocks)
        # Actually just use the li elements directly since they have their own styling
        parts.append(f"""
    <div class="hl-group">
      <p class="hl-label">✅ Back in stock</p>
      <ul class="hl-list">{''.join(restocks)}</ul>
    </div>""")

    if price_drops:
        parts.append(f"""
    <div class="hl-group">
      <p class="hl-label">📉 Price drops</p>
      <ul class="hl-list">{''.join(price_drops)}</ul>
    </div>""")

    if new_items:
        parts.append(f"""
    <div class="hl-group">
      <p class="hl-label">🆕 New listings</p>
      <ul class="hl-list">{''.join(new_items)}</ul>
    </div>""")

    return f"""
<div class="highlights-box">
  <p class="hl-heading">Today's best alerts</p>
  <p class="hl-sub">This is what subscribers got in this morning's email.</p>
  <div class="hl-groups">
    {''.join(parts)}
  </div>
  <p class="hl-more">Plus restocks, new arrivals, and price tracking across {NURSERY_COUNT} nurseries — full digest below.</p>
</div>
"""


def build_sample_digest():
    email_file = DASHBOARD_DIR / "digest-email.html"
    if not email_file.exists():
        print(f"Warning: {email_file} not found. Skipping sample digest.")
        return

    email_html = email_file.read_text()
    email_body = extract_email_body(email_html)

    highlights = extract_highlights(email_html)
    highlights_section = build_highlights_section(highlights)

    today = datetime.now(timezone.utc).strftime("%-d %B %Y")
    n = NURSERY_COUNT

    form1 = make_subscribe_form("subscribeForm", "subEmail", "subBtn", "subMsg", "subState", n)
    form2 = make_subscribe_form("subscribeForm2", "subEmail2", "subBtn2", "subMsg2", "subState2", n)
    js1 = make_subscribe_js("subscribeForm", "subEmail", "subBtn", "subMsg", "subState")
    js2 = make_subscribe_js("subscribeForm2", "subEmail2", "subBtn2", "subMsg2", "subState2")

    page = render_template(
        "sample_digest_page.html.j2",
        n=n, today=today, form1=form1, form2=form2,
        highlights_section=highlights_section, email_body=email_body,
        js1=js1, js2=js2,
    )

    out_file = DASHBOARD_DIR / "sample-digest.html"
    out_file.write_text(page)
    print(f"Built {out_file} ({n} nurseries, {len(highlights['restocks'])} restocks, {len(highlights['price_drops'])} price drops, {len(highlights['new_items'])} new items in highlights)")


if __name__ == "__main__":
    build_sample_digest()
