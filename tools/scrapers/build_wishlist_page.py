#!/usr/bin/env python3
"""
Build the community wishlist page for treestock.com.au.
Shows what species collectors most want to find, with live vote counts.
"""

import json
import sqlite3
from pathlib import Path

FRUIT_SPECIES = Path("/opt/dale/scrapers/fruit_species.json")
VARIETY_WATCHES_DB = Path("/opt/dale/data/variety_watches.db")
OUTPUT = Path("/opt/dale/dashboard/wishlist.html")


def get_wish_counts():
    if not VARIETY_WATCHES_DB.exists():
        return {}
    try:
        con = sqlite3.connect(VARIETY_WATCHES_DB)
        rows = con.execute(
            "SELECT species_slug, COUNT(*) as cnt FROM wishlist GROUP BY species_slug ORDER BY cnt DESC"
        ).fetchall()
        con.close()
        return {r[0]: r[1] for r in rows}
    except sqlite3.Error:
        return {}


def build():
    with open(FRUIT_SPECIES) as f:
        species_list = json.load(f)

    wish_counts = get_wish_counts()
    total_votes = sum(wish_counts.values())

    # Sort species by wish count descending, then alphabetically
    species_with_counts = [
        (s["slug"], s["common_name"], wish_counts.get(s["slug"], 0))
        for s in species_list
    ]
    species_sorted = sorted(species_with_counts, key=lambda x: (-x[2], x[1]))

    top_wanted = [s for s in species_sorted if s[2] > 0][:10]

    # Build species cards HTML
    species_cards = []
    for slug, name, count in species_sorted:
        count_label = f"{count} want this" if count > 0 else "Be first to vote"
        count_class = "text-green-700 font-semibold" if count > 0 else "text-gray-400"
        species_cards.append(f"""
    <div class="species-card border border-gray-200 rounded-lg p-3 flex items-center justify-between gap-2 hover:border-green-300 transition-colors" data-slug="{slug}">
      <div class="flex items-center gap-2 min-w-0">
        <a href="/species/{slug}.html" class="font-medium text-gray-900 hover:text-green-700 no-underline truncate">{name}</a>
      </div>
      <div class="flex items-center gap-2 flex-shrink-0">
        <span class="count-label text-xs {count_class}" data-slug="{slug}">{count_label}</span>
        <button class="vote-btn px-3 py-1 text-xs font-semibold rounded-full border border-green-600 text-green-700 hover:bg-green-50 transition-colors whitespace-nowrap" data-slug="{slug}" data-name="{name}">
          + I want this
        </button>
      </div>
    </div>""")

    species_cards_html = "\n".join(species_cards)

    # Top wanted section
    if top_wanted:
        top_items = []
        for i, (slug, name, count) in enumerate(top_wanted):
            medal = ["gold", "silver", "#cd7f32"][i] if i < 3 else "#6b7280"
            rank_label = ["1st", "2nd", "3rd"][i] if i < 3 else f"{i+1}th"
            top_items.append(f"""
        <div class="flex items-center gap-3 py-2 border-b border-gray-100 last:border-0">
          <span class="text-xs font-bold w-8 text-center" style="color:{medal}">{rank_label}</span>
          <a href="/species/{slug}.html" class="flex-1 font-medium text-gray-900 hover:text-green-700 no-underline">{name}</a>
          <span class="text-sm font-semibold text-green-700">{count} vote{"s" if count != 1 else ""}</span>
        </div>""")
        top_html = f"""
  <section class="mb-8">
    <h2 class="text-lg font-semibold text-gray-800 mb-1">Most wanted right now</h2>
    <p class="text-sm text-gray-500 mb-4">Community votes across all species.</p>
    <div class="bg-green-50 border border-green-200 rounded-lg p-4">
      {"".join(top_items)}
    </div>
  </section>"""
    else:
        top_html = f"""
  <section class="mb-8">
    <div class="bg-green-50 border border-green-200 rounded-lg p-4 text-center">
      <p class="text-green-800 font-medium mb-1">No votes yet.</p>
      <p class="text-sm text-gray-600">Be the first to tell us what you're looking for.</p>
    </div>
  </section>"""

    vote_summary = f"{total_votes} vote{'s' if total_votes != 1 else ''} from the community" if total_votes > 0 else "No votes yet. Be the first."

    species_js = json.dumps([{"slug": s[0], "name": s[1]} for s in species_sorted])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="Vote for the fruit tree species you most want to find in Australian nurseries. Community wishlist tracking demand for rare and popular varieties.">
<title>Most Wanted Species — treestock.com.au Community Wishlist</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link href="/styles.css" rel="stylesheet">
<script defer data-domain="treestock.com.au" src="https://data.bjnoel.com/js/script.outbound-links.js"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
  #nav-menu.open {{ display: flex; }}
  .vote-btn.voted {{ background: #d1fae5; border-color: #059669; color: #065f46; cursor: default; }}
  .vote-btn:disabled {{ opacity: 0.6; cursor: default; }}
  #voteModal {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 50; align-items: center; justify-content: center; }}
  #voteModal.open {{ display: flex; }}
</style>
</head>
<body class="bg-white text-gray-900">

<header class="border-b border-gray-200 bg-white sticky top-0 z-10">
  <div class="max-w-3xl mx-auto px-4 py-2">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <a href="/" class="flex items-center gap-2 no-underline flex-shrink-0">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" class="w-7 h-7 flex-shrink-0"><rect width="64" height="64" rx="12" fill="#065f46"/><path d="M32,12 C18,16 12,28 14,42 C16,38 20,34 26,32 C22,38 20,44 20,50 C28,44 38,34 40,20 C38,14 34,12 32,12Z" fill="#22c55e" opacity="0.9"/><path d="M32,14 C28,24 24,34 20,48" fill="none" stroke="#065f46" stroke-width="1.5" opacity="0.4"/><circle cx="44" cy="44" r="8" fill="#f59e0b"/><text x="44" y="48" text-anchor="middle" font-family="sans-serif" font-size="12" font-weight="bold" fill="#065f46">$</text></svg>
        <span class="text-lg font-bold text-green-800">treestock.com.au</span>
      </a>
      <nav id="nav-menu" class="hidden sm:flex sm:items-center sm:gap-4 text-sm
                                flex-col sm:flex-row gap-2 w-full sm:w-auto mt-2 sm:mt-0
                                border-t sm:border-0 border-gray-100 pt-2 sm:pt-0">
        <a href="/species/" class="hover:text-green-700 no-underline whitespace-nowrap text-gray-600">Species</a>
        <a href="/nursery/" class="hover:text-green-700 no-underline whitespace-nowrap text-gray-600">Nurseries</a>
        <a href="/variety/" class="hover:text-green-700 no-underline whitespace-nowrap text-gray-600">Varieties</a>
        <a href="/compare/" class="hover:text-green-700 no-underline whitespace-nowrap text-gray-600">Compare</a>
        <a href="/rare.html" class="hover:text-green-700 no-underline whitespace-nowrap text-gray-600">Rare Finds</a>
        <a href="/wishlist.html" class="hover:text-green-700 no-underline whitespace-nowrap text-green-800 font-semibold">Wishlist</a>
        <a href="/when-to-plant.html" class="hover:text-green-700 no-underline whitespace-nowrap text-gray-600">Planting Calendar</a>
      </nav>
      <button id="nav-toggle" class="sm:hidden p-1 text-gray-500 hover:text-gray-800" aria-label="Menu">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
        </svg>
      </button>
    </div>
  </div>
</header>
<script>
document.getElementById('nav-toggle').addEventListener('click', function() {{
  document.getElementById('nav-menu').classList.toggle('open');
}});
</script>

<main class="max-w-3xl mx-auto px-4 py-6">

  <nav class="text-xs text-gray-400 mb-4">
    <a href="/" class="hover:underline">Home</a> &rsaquo; Most Wanted
  </nav>

  <div class="mb-6">
    <h1 class="text-3xl font-bold text-green-900 mb-2">Most Wanted Species</h1>
    <p class="text-gray-600 mb-3">
      We track what's <em>in stock</em> across 19 Australian nurseries. But we also want to know
      what you're <em>looking for</em>. Vote for the species you want to find, and we'll
      notify you when they come into stock.
    </p>
    <div class="flex flex-wrap gap-3 text-sm">
      <span class="px-3 py-1 bg-green-50 text-green-800 rounded-full font-medium">50 species tracked</span>
      <span class="px-3 py-1 bg-gray-50 text-gray-600 rounded-full">{vote_summary}</span>
    </div>
  </div>

  {top_html}

  <section class="mb-6">
    <div class="flex items-center justify-between mb-3">
      <h2 class="text-lg font-semibold text-gray-800">All species</h2>
      <input type="search" id="speciesSearch" placeholder="Filter..." class="px-3 py-1 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500 w-32">
    </div>
    <div id="speciesGrid" class="flex flex-col gap-2">
{species_cards_html}
    </div>
    <p id="noResults" class="text-sm text-gray-400 mt-4 hidden">No species match your search.</p>
  </section>

  <section class="mt-8 p-4 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-600">
    <p class="font-medium text-gray-700 mb-1">Why vote?</p>
    <ul class="list-disc list-inside space-y-1">
      <li>Get notified when your wanted species comes into stock</li>
      <li>Help us prioritise which nurseries to add next</li>
      <li>Show nurseries where the demand is</li>
    </ul>
  </section>

</main>

<footer class="mt-12 border-t border-gray-100 py-6 text-xs text-gray-400">
  <div class="max-w-3xl mx-auto px-4 flex flex-wrap gap-4">
    <a href="/" class="hover:text-gray-600 no-underline">Home</a>
    <a href="/species/" class="hover:text-gray-600 no-underline">Species</a>
    <a href="/nursery/" class="hover:text-gray-600 no-underline">Nurseries</a>
    <a href="/wishlist.html" class="hover:text-gray-600 no-underline">Wishlist</a>
    <a href="/when-to-plant.html" class="hover:text-gray-600 no-underline">Planting Calendar</a>
    <span class="text-gray-300">|</span>
    <span>Updated daily. Data from 19 Australian nurseries.</span>
  </div>
</footer>

<!-- Vote modal -->
<div id="voteModal" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
  <div class="bg-white rounded-xl shadow-xl max-w-sm w-full mx-4 p-6">
    <h2 id="modalTitle" class="text-lg font-semibold text-gray-900 mb-1">I want <span id="modalSpeciesName"></span></h2>
    <p class="text-sm text-gray-500 mb-4">
      Enter your email to vote and get notified when this species comes into stock.
    </p>
    <form id="voteForm" class="flex flex-col gap-3">
      <input type="email" id="voteEmail" placeholder="your@email.com" required
        class="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500">
      <div class="flex gap-2">
        <button type="submit" id="voteSubmitBtn" class="flex-1 bg-green-700 text-white font-semibold py-2 rounded-lg text-sm hover:bg-green-800 transition-colors">
          Vote + notify me
        </button>
        <button type="button" id="voteCancel" class="px-4 py-2 border border-gray-300 text-gray-600 rounded-lg text-sm hover:bg-gray-50">
          Cancel
        </button>
      </div>
    </form>
    <p id="voteMsg" class="text-sm mt-3 hidden"></p>
    <p class="text-xs text-gray-400 mt-3">No spam. One email when your species comes into stock.</p>
  </div>
</div>

<script>
const SPECIES = {species_js};

// Update counts from live API
async function refreshCounts() {{
  try {{
    const resp = await fetch('/api/wishlist-counts');
    if (!resp.ok) return;
    const counts = await resp.json();
    document.querySelectorAll('.count-label').forEach(el => {{
      const slug = el.dataset.slug;
      const count = counts[slug] || 0;
      el.textContent = count > 0 ? count + (count === 1 ? ' wants this' : ' want this') : 'Be first to vote';
      el.className = 'count-label text-xs ' + (count > 0 ? 'text-green-700 font-semibold' : 'text-gray-400');
    }});
  }} catch (e) {{ /* API unavailable, show pre-rendered counts */ }}
}}

// Vote modal logic
let currentSlug = '';
const modal = document.getElementById('voteModal');
const modalName = document.getElementById('modalSpeciesName');
const voteForm = document.getElementById('voteForm');
const voteMsg = document.getElementById('voteMsg');
const voteSubmitBtn = document.getElementById('voteSubmitBtn');
const voteCancel = document.getElementById('voteCancel');

// Load previous votes from localStorage
const voted = new Set(JSON.parse(localStorage.getItem('ts_wishlist_votes') || '[]'));
voted.forEach(slug => markVoted(slug));

function markVoted(slug) {{
  const btn = document.querySelector(`.vote-btn[data-slug="${{slug}}"]`);
  const label = document.querySelector(`.count-label[data-slug="${{slug}}"]`);
  if (btn) {{ btn.textContent = 'Voted'; btn.classList.add('voted'); btn.disabled = true; }}
}}

document.querySelectorAll('.vote-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    if (btn.disabled) return;
    currentSlug = btn.dataset.slug;
    modalName.textContent = btn.dataset.name;
    voteMsg.classList.add('hidden');
    voteMsg.textContent = '';
    document.getElementById('voteEmail').value = '';
    modal.classList.add('open');
    setTimeout(() => document.getElementById('voteEmail').focus(), 50);
  }});
}});

voteCancel.addEventListener('click', () => modal.classList.remove('open'));
modal.addEventListener('click', e => {{ if (e.target === modal) modal.classList.remove('open'); }});

voteForm.addEventListener('submit', async (e) => {{
  e.preventDefault();
  const email = document.getElementById('voteEmail').value.trim();
  if (!email) return;
  voteSubmitBtn.disabled = true;
  voteSubmitBtn.textContent = 'Saving...';
  try {{
    const resp = await fetch('/api/wishlist', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ email, species_slug: currentSlug }})
    }});
    const data = await resp.json();
    if (resp.ok) {{
      voteMsg.textContent = data.message + ' We will email you when ' + data.species_slug.replace(/-/g, ' ') + ' comes into stock.';
      voteMsg.style.color = '#065f46';
      voteMsg.classList.remove('hidden');
      // Update count display
      const label = document.querySelector(`.count-label[data-slug="${{currentSlug}}"]`);
      if (label && data.total) {{
        label.textContent = data.total + (data.total === 1 ? ' wants this' : ' want this');
        label.className = 'count-label text-xs text-green-700 font-semibold';
      }}
      markVoted(currentSlug);
      const votes = JSON.parse(localStorage.getItem('ts_wishlist_votes') || '[]');
      if (!votes.includes(currentSlug)) votes.push(currentSlug);
      localStorage.setItem('ts_wishlist_votes', JSON.stringify(votes));
      setTimeout(() => modal.classList.remove('open'), 2000);
    }} else {{
      voteMsg.textContent = data.error || 'Something went wrong.';
      voteMsg.style.color = '#dc2626';
      voteMsg.classList.remove('hidden');
    }}
  }} catch (err) {{
    voteMsg.textContent = 'Network error. Please try again.';
    voteMsg.style.color = '#dc2626';
    voteMsg.classList.remove('hidden');
  }}
  voteSubmitBtn.disabled = false;
  voteSubmitBtn.textContent = 'Vote + notify me';
}});

// Filter by search
const searchInput = document.getElementById('speciesSearch');
const cards = document.querySelectorAll('.species-card');
const noResults = document.getElementById('noResults');
searchInput.addEventListener('input', () => {{
  const q = searchInput.value.toLowerCase();
  let visible = 0;
  cards.forEach(card => {{
    const slug = card.dataset.slug;
    const name = card.querySelector('a').textContent.toLowerCase();
    const match = !q || name.includes(q) || slug.includes(q);
    card.style.display = match ? '' : 'none';
    if (match) visible++;
  }});
  noResults.classList.toggle('hidden', visible > 0);
}});

// Refresh counts on load
refreshCounts();
</script>
</body>
</html>
"""

    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Built wishlist.html ({total_votes} total votes, {len(species_list)} species)")


if __name__ == "__main__":
    build()
