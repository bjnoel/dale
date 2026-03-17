#!/usr/bin/env python3
"""
Build nursery value / sponsorship pitch report for a given nursery.
Outputs a self-contained HTML file to /opt/dale/dashboard/nursery-report-[key].html

Usage: python3 build_nursery_report.py primal-fruits
       python3 build_nursery_report.py heritage-fruit-trees
"""

import json
import sys
import os
from datetime import datetime, date

DATA_DIR = "/opt/dale/data/nursery-stock"
DASHBOARD_DIR = "/opt/dale/dashboard"
SCRAPERS_DIR = "/opt/dale/scrapers"
TREESTOCK_URL = "https://treestock.com.au"

# Nursery metadata for the report
NURSERY_META = {
    "primal-fruits": {
        "name": "Primal Fruits Perth",
        "location": "Parkwood, WA",
        "ships_to": "WA (local)",
        "audience_note": "Your entire customer base is in WA. Our WA audience is the most valuable segment.",
        "unique_angle": "Only WA-based tropical rare fruit nursery on the platform",
        "wa_only": True,
        "season_note": None,
        "contact_name": "Cyrus",
        "price": 49,
    },
    "heritage-fruit-trees": {
        "name": "Heritage Fruit Trees",
        "location": "Beaufort, VIC",
        "ships_to": "Australia-wide (winter/dormant season, approx May-Sep)",
        "audience_note": "Your WA shipping window opens in ~8 weeks. Our audience includes serious WA collectors who plan ahead.",
        "unique_angle": "Only heritage/heirloom temperate specialist on the platform",
        "wa_only": False,
        "season_note": "Your WA shipping season (May-September) is 8 weeks away. Buyers are planning now.",
        "contact_name": None,
        "price": 49,
    },
}

# Site-wide stats (updated from Plausible, accurate as of 2026-03-17)
SITE_STATS = {
    "visitors_7d": 526,
    "visitors_30d": 490,
    "pageviews_30d": 716,
    "subscribers": 4,
    "products_tracked": 5688,
    "nurseries": 12,
    "launch_date": "2026-03-05",
    "top_sources": [
        ("Facebook (rare fruit groups)", "322 visitors / 7 days"),
        ("Direct / bookmarks", "166 visitors / 7 days"),
        ("Whirlpool forums", "23 visitors / 7 days"),
        ("Google", "13 visitors / 7 days"),
    ],
}

def load_nursery_data(key):
    latest = os.path.join(DATA_DIR, key, "latest.json")
    if not os.path.exists(latest):
        return None
    with open(latest) as f:
        return json.load(f)

def get_in_stock_products(data):
    if not data:
        return []
    products = data.get("products", [])
    return [p for p in products
            if p.get("available")
            and p.get("price", 0) > 0
            and "gift" not in p.get("title", "").lower()
            and "workshop" not in p.get("title", "").lower()]

def get_top_products(products, n=8):
    return sorted(products, key=lambda p: -p.get("price", 0))[:n]

def build_report(nursery_key):
    meta = NURSERY_META.get(nursery_key)
    if not meta:
        print(f"No metadata for nursery: {nursery_key}")
        print(f"Available: {list(NURSERY_META.keys())}")
        sys.exit(1)

    data = load_nursery_data(nursery_key)
    all_products = data.get("products", []) if data else []
    in_stock = get_in_stock_products(data)
    top_products = get_top_products(in_stock)
    total_count = len(all_products)
    in_stock_count = len(in_stock)
    prices = [p['price'] for p in in_stock if p.get('price', 0) > 0]
    avg_price = round(sum(prices) / len(prices)) if prices else 0

    nursery_page_url = f"{TREESTOCK_URL}/nursery/{nursery_key}.html"
    report_date = date.today().strftime("%-d %B %Y")

    # Build product rows
    product_rows = ""
    for p in top_products:
        price_str = f"${p['price']:.0f}"
        product_rows += f"""
                    <tr>
                        <td>{p['title']}</td>
                        <td class="price">{price_str}</td>
                    </tr>"""

    season_banner = ""
    if meta["season_note"]:
        season_banner = f"""
            <div class="season-banner">
                <strong>Timing opportunity:</strong> {meta["season_note"]}
            </div>"""

    wa_note = ""
    if meta["wa_only"]:
        wa_note = "<span class='badge'>WA audience</span>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>treestock.com.au — Nursery Partnership Report: {meta['name']}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #1a1a1a; background: #f8f5f0; }}
  .header {{ background: #2d5a1b; color: white; padding: 2rem; }}
  .header h1 {{ font-size: 1.5rem; font-weight: 700; }}
  .header p {{ margin-top: 0.5rem; opacity: 0.85; font-size: 0.95rem; }}
  .logo {{ font-size: 1.1rem; font-weight: 800; letter-spacing: -0.5px; margin-bottom: 1rem; }}
  .logo span {{ color: #a8d87a; }}
  .container {{ max-width: 720px; margin: 0 auto; padding: 2rem 1.5rem; }}
  .section {{ background: white; border-radius: 12px; padding: 1.75rem; margin-bottom: 1.5rem; border: 1px solid #e8e0d0; }}
  .section h2 {{ font-size: 1.05rem; font-weight: 700; color: #2d5a1b; border-bottom: 2px solid #e8f0e0; padding-bottom: 0.6rem; margin-bottom: 1.1rem; }}
  .stats-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; }}
  .stat {{ background: #f4f8f0; border-radius: 8px; padding: 1rem; text-align: center; }}
  .stat .number {{ font-size: 2rem; font-weight: 800; color: #2d5a1b; }}
  .stat .label {{ font-size: 0.8rem; color: #555; margin-top: 0.2rem; }}
  .source-list {{ list-style: none; }}
  .source-list li {{ display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid #f0ebe0; font-size: 0.9rem; }}
  .source-list li:last-child {{ border-bottom: none; }}
  .source-count {{ color: #2d5a1b; font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
  th {{ text-align: left; padding: 0.5rem; background: #f4f8f0; font-weight: 600; color: #444; }}
  td {{ padding: 0.5rem; border-bottom: 1px solid #f0ebe0; }}
  td.price {{ text-align: right; font-weight: 600; color: #2d5a1b; }}
  .badge {{ background: #2d5a1b; color: white; font-size: 0.75rem; font-weight: 600; padding: 0.2rem 0.6rem; border-radius: 999px; }}
  .featured-list {{ list-style: none; }}
  .featured-list li {{ padding: 0.5rem 0; border-bottom: 1px solid #f0ebe0; font-size: 0.92rem; display: flex; align-items: flex-start; gap: 0.6rem; }}
  .featured-list li:last-child {{ border-bottom: none; }}
  .check {{ color: #2d5a1b; font-weight: 700; font-size: 1.1rem; flex-shrink: 0; }}
  .cta {{ background: #2d5a1b; color: white; border-radius: 12px; padding: 2rem; text-align: center; }}
  .cta h2 {{ font-size: 1.3rem; margin-bottom: 0.75rem; }}
  .cta p {{ opacity: 0.9; margin-bottom: 1rem; font-size: 0.95rem; }}
  .cta .price-tag {{ font-size: 2rem; font-weight: 800; color: #a8d87a; }}
  .cta .price-period {{ font-size: 1rem; opacity: 0.8; }}
  .nursery-link {{ color: #2d5a1b; text-decoration: none; font-weight: 600; }}
  .nursery-link:hover {{ text-decoration: underline; }}
  .intro-note {{ color: #555; font-size: 0.92rem; line-height: 1.6; }}
  .season-banner {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 1rem; font-size: 0.9rem; }}
  .basic-vs-featured {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
  .plan {{ border-radius: 8px; padding: 1rem; }}
  .plan.basic {{ background: #f8f8f8; border: 1px solid #ddd; }}
  .plan.featured {{ background: #f0f8e8; border: 2px solid #2d5a1b; }}
  .plan h3 {{ font-size: 0.9rem; font-weight: 700; margin-bottom: 0.75rem; }}
  .plan ul {{ list-style: none; font-size: 0.85rem; }}
  .plan ul li {{ padding: 0.3rem 0; }}
  .plan ul li::before {{ content: "• "; color: #2d5a1b; }}
  .footer {{ text-align: center; color: #888; font-size: 0.8rem; padding: 1.5rem; }}
  @media (max-width: 480px) {{
    .stats-grid {{ grid-template-columns: 1fr 1fr; }}
    .basic-vs-featured {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<div class="header">
  <div class="logo">treestock<span>.com.au</span></div>
  <h1>Nursery Partnership — {meta['name']}</h1>
  <p>How treestock.com.au promotes your business to serious fruit tree buyers</p>
</div>

<div class="container">

  <div class="section">
    <h2>Your current presence on treestock.com.au</h2>
    {season_banner}
    <p class="intro-note" style="margin-bottom:1rem;">
      We already track your stock every day. Your nursery page is live at
      <a class="nursery-link" href="{nursery_page_url}">{nursery_page_url}</a>.
      Here's what we know about your catalogue right now:
    </p>
    <div class="stats-grid">
      <div class="stat">
        <div class="number">{total_count}</div>
        <div class="label">Products tracked</div>
      </div>
      <div class="stat">
        <div class="number">{in_stock_count}</div>
        <div class="label">Currently in stock</div>
      </div>
      <div class="stat">
        <div class="number">${avg_price}</div>
        <div class="label">Avg price per item (AUD)</div>
      </div>
      <div class="stat">
        <div class="number">Daily</div>
        <div class="label">Stock updates</div>
      </div>
    </div>
    <p style="margin-top:1rem; font-size:0.85rem; color:#666;">
      Ships to: {meta['ships_to']} &nbsp; Location: {meta['location']}
    </p>
  </div>

  <div class="section">
    <h2>Our audience</h2>
    <p class="intro-note" style="margin-bottom:1rem;">
      {meta['audience_note']}
    </p>
    <div class="stats-grid">
      <div class="stat">
        <div class="number">526</div>
        <div class="label">Visitors this week</div>
      </div>
      <div class="stat">
        <div class="number">490</div>
        <div class="label">Visitors past 30 days</div>
      </div>
      <div class="stat">
        <div class="number">4</div>
        <div class="label">Email subscribers<br>(growing daily)</div>
      </div>
      <div class="stat">
        <div class="number">5,688</div>
        <div class="label">Products tracked<br>across 12 nurseries</div>
      </div>
    </div>
    <p style="margin-top:1.25rem; font-size:0.92rem; font-weight:600;">Where our visitors come from:</p>
    <ul class="source-list" style="margin-top:0.5rem;">
      {"".join(f'<li><span>{src}</span><span class="source-count">{cnt}</span></li>' for src, cnt in SITE_STATS["top_sources"])}
    </ul>
    <p style="margin-top:1rem; font-size:0.85rem; color:#666;">
      We launched {SITE_STATS['launch_date']} and are growing steadily through
      rare fruit Facebook groups and word of mouth.
    </p>
  </div>

  <div class="section">
    <h2>Your top in-stock products right now</h2>
    {"<p style='color:#888; font-size:0.9rem;'>No in-stock products found in current snapshot.</p>" if not top_products else f"""
    <table>
      <thead><tr><th>Product</th><th style="text-align:right">Price</th></tr></thead>
      <tbody>{product_rows}
      </tbody>
    </table>
    <p style="margin-top:0.75rem; font-size:0.85rem; color:#666;">
      These appear in daily search results on treestock.com.au and in our subscriber email digest.
    </p>"""}
  </div>

  <div class="section">
    <h2>What a featured listing includes</h2>
    <div class="basic-vs-featured">
      <div class="plan basic">
        <h3>Free listing (current)</h3>
        <ul>
          <li>Nursery profile page</li>
          <li>Products appear in search</li>
          <li>Daily stock updates</li>
          <li>Listed in state pages</li>
        </ul>
      </div>
      <div class="plan featured">
        <h3>Featured listing ($49/month)</h3>
        <ul>
          <li>Everything in free, plus:</li>
          <li>Featured badge on search results</li>
          <li>Pinned at top of nursery index</li>
          <li>Highlighted in email digest</li>
          <li>Monthly traffic report</li>
          <li>Priority in species pages</li>
        </ul>
      </div>
    </div>
  </div>

  <div class="section">
    <h2>Why this matters for you</h2>
    <ul class="featured-list">
      <li><span class="check">&#10003;</span>
        <span>Our audience is active rare fruit collectors who buy deliberately, not casually. They find you through species and variety searches.</span>
      </li>
      <li><span class="check">&#10003;</span>
        <span>We track when you restock rare items and alert subscribers immediately. Your restocks get exposure the moment they happen.</span>
      </li>
      <li><span class="check">&#10003;</span>
        <span>{meta['unique_angle']}. When someone searches for what you carry, you are the answer.</span>
      </li>
      <li><span class="check">&#10003;</span>
        <span>No lock-in. Cancel anytime. The free listing stays either way.</span>
      </li>
    </ul>
  </div>

  <div class="cta">
    <h2>Partner with treestock.com.au</h2>
    <p>Featured listing starts at</p>
    <div class="price-tag">$49 <span class="price-period">/month</span></div>
    <p style="margin-top:1rem; font-size:0.9rem;">
      Reply to this email or contact Benedict:<br>
      <strong>hello@walkthrough.au</strong>
    </p>
  </div>

</div>

<div class="footer">
  treestock.com.au &nbsp;|&nbsp; Tracking {SITE_STATS['nurseries']} nurseries, {SITE_STATS['products_tracked']:,} products &nbsp;|&nbsp; Report generated {report_date}
</div>

</body>
</html>"""

    out_path = os.path.join(DASHBOARD_DIR, f"nursery-report-{nursery_key}.html")
    with open(out_path, "w") as f:
        f.write(html)
    print(f"Saved: {out_path}")
    print(f"URL: {TREESTOCK_URL}/nursery-report-{nursery_key}.html")
    return out_path


if __name__ == "__main__":
    keys = sys.argv[1:] if len(sys.argv) > 1 else list(NURSERY_META.keys())
    for key in keys:
        build_report(key)
