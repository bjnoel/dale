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

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sample Daily Digest — treestock.com.au</title>
  <meta name="description" content="See what you'll receive in your inbox — daily nursery stock alerts, price drops, and restocks from {n} Australian nurseries.">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f9fafb; color: #111827; }}
    a {{ color: #059669; }}
    .header {{ background: white; border-bottom: 1px solid #e5e7eb; padding: 12px 16px; position: sticky; top: 0; z-index: 10; }}
    .header-inner {{ max-width: 680px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; }}
    .site-name {{ font-size: 1.1rem; font-weight: 700; color: #065f46; text-decoration: none; }}
    .back-link {{ font-size: 0.85rem; color: #6b7280; text-decoration: none; }}
    .back-link:hover {{ color: #059669; }}
    .hero {{ background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border-bottom: 1px solid #bbf7d0; padding: 32px 16px; text-align: center; }}
    .hero-inner {{ max-width: 600px; margin: 0 auto; }}
    .hero h1 {{ font-size: 1.5rem; font-weight: 700; color: #065f46; margin: 0 0 8px; }}
    .hero p {{ font-size: 0.95rem; color: #374151; margin: 0 0 8px; line-height: 1.5; }}
    .hero .meta {{ font-size: 0.8rem; color: #6b7280; }}
    .features {{ display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin-top: 16px; }}
    .feature {{ font-size: 0.8rem; background: white; border: 1px solid #d1fae5; border-radius: 999px; padding: 4px 12px; color: #065f46; font-weight: 500; }}
    .main {{ max-width: 680px; margin: 0 auto; padding: 24px 16px; }}
    .subscribe-box {{ background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 10px; padding: 20px; margin-bottom: 24px; }}
    .box-heading {{ font-size: 1rem; font-weight: 700; color: #065f46; margin: 0 0 4px; }}
    .box-sub {{ font-size: 0.85rem; color: #374151; margin: 0 0 14px; line-height: 1.5; }}
    .sub-form {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .sub-input {{ flex: 1; min-width: 200px; padding: 10px 12px; border: 1px solid #d1d5db; border-radius: 8px; font-size: 0.9rem; outline: none; }}
    .sub-input:focus {{ border-color: #059669; box-shadow: 0 0 0 2px #d1fae5; }}
    .sub-btn {{ background: #16a34a; color: white; border: none; padding: 10px 20px; border-radius: 8px; font-size: 0.9rem; font-weight: 600; cursor: pointer; white-space: nowrap; }}
    .sub-btn:hover {{ background: #15803d; }}
    .sub-btn:disabled {{ opacity: 0.6; cursor: not-allowed; }}
    .sub-msg {{ font-size: 0.85rem; margin-top: 8px; min-height: 1.2em; }}
    .divider {{ border: none; border-top: 1px solid #e5e7eb; margin: 24px 0; }}
    .email-label {{ font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #9ca3af; margin-bottom: 8px; }}
    .email-frame {{ background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 24px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
    .email-frame h2 {{ color: #065f46; margin-top: 0; }}
    .email-frame h3 {{ color: #1f2937; margin: 20px 0 8px; }}
    .email-frame ul {{ list-style: none; padding: 0; }}
    .email-frame li {{ padding: 4px 0; line-height: 1.5; }}
    .email-frame a {{ color: #059669; }}
    .email-frame hr {{ border: none; border-top: 1px solid #e5e7eb; margin: 20px 0; }}
    /* Highlights section */
    .highlights-box {{ background: white; border: 1px solid #e5e7eb; border-radius: 10px; padding: 20px; margin-bottom: 24px; }}
    .hl-heading {{ font-size: 1rem; font-weight: 700; color: #111827; margin: 0 0 4px; }}
    .hl-sub {{ font-size: 0.85rem; color: #6b7280; margin: 0 0 16px; }}
    .hl-groups {{ display: grid; gap: 16px; }}
    @media (min-width: 540px) {{ .hl-groups {{ grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }} }}
    .hl-group {{ background: #f9fafb; border: 1px solid #f3f4f6; border-radius: 8px; padding: 12px 14px; }}
    .hl-label {{ font-size: 0.8rem; font-weight: 600; color: #374151; margin: 0 0 8px; }}
    .hl-list {{ list-style: none; padding: 0; margin: 0; font-size: 0.85rem; }}
    .hl-list li {{ padding: 3px 0; line-height: 1.4; color: #374151; border-bottom: 1px solid #e5e7eb; }}
    .hl-list li:last-child {{ border-bottom: none; }}
    .hl-list a {{ color: #059669; text-decoration: none; }}
    .hl-list a:hover {{ text-decoration: underline; }}
    .hl-more {{ font-size: 0.8rem; color: #9ca3af; margin: 12px 0 0; text-align: center; }}
    .footer {{ text-align: center; padding: 24px 16px; font-size: 0.75rem; color: #9ca3af; border-top: 1px solid #e5e7eb; background: white; margin-top: 16px; }}
    .footer a {{ color: #9ca3af; }}
    .footer a:hover {{ color: #6b7280; }}
    @media (max-width: 480px) {{
      .hero h1 {{ font-size: 1.25rem; }}
      .email-frame {{ padding: 16px; }}
    }}
  </style>
</head>
<body>

<header class="header">
  <div class="header-inner">
    <a href="/" class="site-name">treestock.com.au</a>
    <a href="/" class="back-link">Back to stock tracker</a>
  </div>
</header>

<div class="hero">
  <div class="hero-inner">
    <h1>Your daily fruit tree digest</h1>
    <p>Price drops, restocks, and new arrivals from {n} Australian nurseries — delivered free each morning.</p>
    <p class="meta">Real example from {today}. Sent every day, unsubscribe any time.</p>
    <div class="features">
      <span class="feature">📦 {n} nurseries</span>
      <span class="feature">💰 Price drop alerts</span>
      <span class="feature">✅ Restock notifications</span>
      <span class="feature">🆕 New arrivals</span>
      <span class="feature">🚛 WA shipping filter</span>
    </div>
  </div>
</div>

<div class="main">

  {form1}

  {highlights_section}

  <hr class="divider">
  <p class="email-label">Full digest — sent to subscribers this morning</p>
  <div class="email-frame">
    {email_body}
  </div>
  <hr class="divider">

  {form2}

</div>

<footer class="footer">
  <p>
    <a href="/">treestock.com.au</a> ·
    <a href="/species/">Browse by species</a> ·
    <a href="/rare.html">Rare &amp; Exotic</a> ·
    <a href="/compare/">Compare prices</a>
  </p>
  <p style="margin-top:6px">Data updated daily from {n} Australian nurseries. Not affiliated with any nursery.</p>
</footer>

{js1}
{js2}

</body>
</html>"""

    out_file = DASHBOARD_DIR / "sample-digest.html"
    out_file.write_text(page)
    print(f"Built {out_file} ({n} nurseries, {len(highlights['restocks'])} restocks, {len(highlights['price_drops'])} price drops, {len(highlights['new_items'])} new items in highlights)")


if __name__ == "__main__":
    build_sample_digest()
