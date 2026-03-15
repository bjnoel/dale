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

SUBSCRIBE_FORM = """
<div class="subscribe-box">
  <p class="box-heading">Get this in your inbox every day — free</p>
  <p class="box-sub">Daily stock alerts: price drops, restocks, new arrivals across 11 Australian nurseries. Unsubscribe any time.</p>
  <form id="subscribeForm" class="sub-form">
    <input type="email" id="subEmail" placeholder="your@email.com" required class="sub-input">
    <button type="submit" id="subBtn" class="sub-btn">Subscribe free</button>
  </form>
  <p id="subMsg" class="sub-msg"></p>
</div>
"""

SUBSCRIBE_JS = f"""
<script>
document.getElementById('subscribeForm').addEventListener('submit', async function(e) {{
  e.preventDefault();
  const email = document.getElementById('subEmail').value.trim();
  const btn = document.getElementById('subBtn');
  const msg = document.getElementById('subMsg');
  if (!email) return;
  btn.disabled = true;
  btn.textContent = 'Subscribing...';
  try {{
    const resp = await fetch('{SUBSCRIBE_API}', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{email}})
    }});
    const data = await resp.json();
    if (resp.ok) {{
      document.getElementById('subscribeForm').style.display = 'none';
      msg.style.color = '#065f46';
      msg.textContent = data.message === 'Already subscribed'
        ? "You're already subscribed!"
        : '✓ Subscribed! Check your inbox tomorrow morning.';
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
    # Remove doctype, html, head, body tags — just keep the content
    match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Fallback: strip outer tags
    html = re.sub(r'<!DOCTYPE[^>]*>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'<html[^>]*>|</html>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'<head>.*?</head>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<body[^>]*>|</body>', '', html, flags=re.IGNORECASE)
    return html.strip()


def build_sample_digest():
    email_file = DASHBOARD_DIR / "digest-email.html"
    if not email_file.exists():
        print(f"Warning: {email_file} not found. Skipping sample digest.")
        return

    email_html = email_file.read_text()
    email_body = extract_email_body(email_html)

    today = datetime.now(timezone.utc).strftime("%-d %B %Y")

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sample Daily Digest — treestock.com.au</title>
  <meta name="description" content="See what you'll receive in your inbox — daily nursery stock alerts, price drops, and restocks from 11 Australian nurseries.">
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
    <a href="/" class="back-link">← Back to stock tracker</a>
  </div>
</header>

<div class="hero">
  <div class="hero-inner">
    <h1>Your daily fruit tree digest</h1>
    <p>This is a real example of what lands in your inbox each morning — price drops, restocks, and new arrivals from 11 Australian nurseries.</p>
    <p class="meta">Example from {today}. Sent every day, free, unsubscribe any time.</p>
    <div class="features">
      <span class="feature">📦 11 nurseries monitored</span>
      <span class="feature">💰 Price drop alerts</span>
      <span class="feature">✅ Restock notifications</span>
      <span class="feature">🆕 New arrivals</span>
      <span class="feature">🚛 WA shipping filter</span>
    </div>
  </div>
</div>

<div class="main">

  {SUBSCRIBE_FORM}

  <hr class="divider">
  <p class="email-label">Today's digest email — example</p>
  <div class="email-frame">
    {email_body}
  </div>
  <hr class="divider">

  {SUBSCRIBE_FORM.replace('subscribeForm', 'subscribeForm2').replace('subEmail', 'subEmail2').replace('subBtn', 'subBtn2').replace('subMsg', 'subMsg2')}

</div>

<footer class="footer">
  <p>
    <a href="/">treestock.com.au</a> ·
    <a href="/species/">Browse by species</a> ·
    <a href="/rare.html">Rare &amp; Exotic</a> ·
    <a href="/compare/">Compare prices</a>
  </p>
  <p style="margin-top:6px">Data updated daily from 11 Australian nurseries. Not affiliated with any nursery.</p>
</footer>

{SUBSCRIBE_JS}
<script>
// Wire up second form too
document.getElementById('subscribeForm2').addEventListener('submit', async function(e) {{
  e.preventDefault();
  const email = document.getElementById('subEmail2').value.trim();
  const btn = document.getElementById('subBtn2');
  const msg = document.getElementById('subMsg2');
  if (!email) return;
  btn.disabled = true;
  btn.textContent = 'Subscribing...';
  try {{
    const resp = await fetch('{SUBSCRIBE_API}', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{email}})
    }});
    const data = await resp.json();
    if (resp.ok) {{
      document.getElementById('subscribeForm2').style.display = 'none';
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

</body>
</html>"""

    out_file = DASHBOARD_DIR / "sample-digest.html"
    out_file.write_text(page)
    print(f"Built {out_file}")


if __name__ == "__main__":
    build_sample_digest()
