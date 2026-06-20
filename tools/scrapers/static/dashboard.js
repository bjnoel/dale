// treestock.com.au dashboard client app.
// Extracted from build-dashboard.py (was embedded in a Python f-string -- the
// DEC-066 escaping hazard). The dataset is loaded from an external data.js
// (window.__DATA) with `defer` BEFORE this file, so it is available synchronously
// here -- defer preserves execution order. Keeping it out of the HTML shrinks the
// document ~70x for a faster FCP. Both files are static and browser-cacheable.

const _DATA = window.__DATA;
const P = _DATA.products;
// Variety-level availability across ALL nurseries. The variety watch fires
// globally (a row out of stock at one nursery but in stock at another is NOT
// a restock target), so the per-row CTA branches on this, not on p.a.
const VARIETY_IN_STOCK = {};
for (const _p of P) { if (_p.vs) VARIETY_IN_STOCK[_p.vs] = VARIETY_IN_STOCK[_p.vs] || !!_p.a; }
const N = _DATA.nurseries;
const SPECIES_SLUGS = _DATA.species_slugs;
const HARD_TO_FIND = new Set(_DATA.hard_to_find);
// Per-species category list (e.g. {"finger-lime":["fruit","bush_tucker"]}) for the
// result-row category badge and the Fruit / Bush Tucker filter.
const SPECIES_CATS = _DATA.species_cats || {};
const CAT_BADGE = { fruit: ['Fruit', 'cat-badge-fruit'], bush_tucker: ['Bush Tucker', 'cat-badge-bush'] };
const SLUG_TO_NAME = {};
Object.values(SPECIES_SLUGS).forEach(v => { SLUG_TO_NAME[v.slug] = v.name; });

// Tracks which species the user is currently viewing (for context-aware subscribe)
let currentWatchSlug = null;

const NURSERY_URLS = {
  'ross-creek': 'rosscreektropicals.com.au',
  'ladybird': 'ladybirdnursery.com.au',
  'fruitopia': 'fruitopia.com.au',
  'daleys': 'daleysfruit.com.au',
  'primal-fruits': 'primalfruits.com.au',
};

let displayCount = 50;
let currentResults = [];

// Build state→nursery shipping lookup
const SHIPS_TO = {};
const LOCAL_ONLY = {};
N.forEach(n => { SHIPS_TO[n.key] = n.st || []; if (n.lo) LOCAL_ONLY[n.key] = n.lo; });

// Populate nursery filter (featured nurseries first, then alphabetical)
const nurserySelect = document.getElementById('nurseryFilter');
const sortedN = [...N].sort((a, b) => (b.ft ? 1 : 0) - (a.ft ? 1 : 0) || a.name.localeCompare(b.name));
sortedN.forEach(n => {
  const opt = document.createElement('option');
  opt.value = n.key;
  opt.textContent = n.ft
    ? `* ${n.name} (${n.in_stock} in stock)`
    : `${n.name} (${n.in_stock} in stock)`;
  nurserySelect.appendChild(opt);
});

const totalProducts = P.length;
const totalInStock = P.filter(p => p.a).length;
const statsText = `${totalInStock.toLocaleString()} in stock across ${N.length} nurseries (${totalProducts.toLocaleString()} total)`;
document.getElementById('stats').textContent = statsText;
const sm = document.getElementById('statsSmall');
if (sm) sm.textContent = statsText;

// Search & filter
const searchInput = document.getElementById('search');
const inStockOnly = document.getElementById('inStockOnly');
const stateFilter = document.getElementById('stateFilter');
const changesOnly = document.getElementById('changesOnly');
const sortBy = document.getElementById('sortBy');
// Category filter (homepage only; absent on category landing pages).
const categoryFilter = document.getElementById('categoryFilter');
let activeSpeciesSlug = '';
let rareOnly = false;
// Progressive species pills: show SPECIES_DEFAULT pills, reveal SPECIES_TIER more each
// time the "Other" pill is clicked. Reset to default whenever a filter/search changes.
const SPECIES_DEFAULT = 16;
const SPECIES_TIER = 12;
let speciesShown = SPECIES_DEFAULT;

// Mirror the current filter state into the address bar so a filtered view can be
// shared/bookmarked. Only non-default params are written, keeping URLs short. Uses
// replaceState (not pushState): search() fires on every keystroke, so pushState
// would bury the back button under a history entry per character. syncURL() only
// reads state and writes the bar -- it never reads the URL or calls search(), and
// replaceState fires no popstate, so there is no loop. Called at the tail of search().
function syncURL() {
  const params = new URLSearchParams();
  // species + free-text are mutually exclusive (a pill mirrors its name into the box);
  // prefer species, matching search() which ignores q when a species is active.
  if (activeSpeciesSlug) {
    params.set('species', activeSpeciesSlug);
  } else {
    const q = searchInput.value.trim();
    if (q) params.set('q', q);
  }
  if (inStockOnly.checked) params.set('stock', '1');
  if (stateFilter.value) params.set('state', stateFilter.value);
  if (categoryFilter && categoryFilter.value) params.set('cat', categoryFilter.value);
  if (nurserySelect.value) params.set('nursery', nurserySelect.value);
  if (changesOnly.checked) params.set('changes', '1');
  // sortBy default is the string "relevance", not "" -- omit it explicitly.
  if (sortBy.value && sortBy.value !== 'relevance') params.set('sort', sortBy.value);
  if (rareOnly) params.set('rare', '1');
  const qs = params.toString();
  window.history.replaceState(null, '',
    window.location.pathname + (qs ? '?' + qs : '') + window.location.hash);
}

function search() {
  displayCount = 50;
  // A new filter/search view starts collapsed at the default tier. The "Other" pill click
  // handler calls updatePillCounts() directly (not search()), so it preserves speciesShown.
  speciesShown = SPECIES_DEFAULT;
  document.querySelector('.species-strip').classList.remove('expanded');
  const q = searchInput.value.toLowerCase().trim();
  const nursery = nurserySelect.value;
  const stockOnly = inStockOnly.checked;
  const st = stateFilter.value;
  const sort = sortBy.value;

  let results = P;

  const cat = categoryFilter ? categoryFilter.value : '';

  if (stockOnly) results = results.filter(p => p.a);
  if (st) results = results.filter(p => (SHIPS_TO[p.nk] || []).includes(st));
  if (changesOnly.checked) results = results.filter(p => p.ch);
  if (nursery) results = results.filter(p => p.nk === nursery);
  if (cat) results = results.filter(p => (SPECIES_CATS[p.sl] || []).includes(cat));
  if (activeSpeciesSlug) results = results.filter(p => p.sl === activeSpeciesSlug);
  if (rareOnly) results = results.filter(p => p.sl && HARD_TO_FIND.has(p.sl));

  if (q && !activeSpeciesSlug) {
    const terms = q.split(/\\s+/);
    results = results.filter(p => {
      const text = (p.t + ' ' + p.cat + ' ' + (p.ln || '') + ' ' + (p.cv || '')).toLowerCase();
      return terms.every(t => text.includes(t));
    });
    // Score by how early the match appears
    results = results.map(p => {
      const idx = p.t.toLowerCase().indexOf(terms[0]);
      return { ...p, _score: idx === -1 ? 999 : idx };
    });
  }

  // Sort
  if (sort === 'price-asc') {
    results.sort((a, b) => (a.p || 9999) - (b.p || 9999));
  } else if (sort === 'price-desc') {
    results.sort((a, b) => (b.p || 0) - (a.p || 0));
  } else if (sort === 'name') {
    results.sort((a, b) => a.t.localeCompare(b.t));
  } else if (q) {
    // Relevance with a search query: best title match first, then in-stock, then A-Z.
    results.sort((a, b) =>
      (a._score || 0) - (b._score || 0)
      || (b.a ? 1 : 0) - (a.a ? 1 : 0)
      || a.t.localeCompare(b.t));
  } else {
    // Relevance with no search query: "newest in stock first". There is no
    // text to score against, so rank by what changed recently: newly listed
    // and back-in-stock items first, then price drops, then other in-stock
    // items, with out-of-stock last (A-Z within each group).
    // Previously this fell through to a plain alphabetical sort, which made
    // "Relevance" identical to "Name: A-Z" on the default view.
    const relScore = p => {
      if (!p.a) return 3;
      if (p.ch === 'new' || p.ch === 'back') return 0;
      if (p.ch === 'down') return 1;
      return 2;
    };
    results.sort((a, b) => relScore(a) - relScore(b) || a.t.localeCompare(b.t));
  }

  // Featured nurseries bubble to top within current sort (only on default/name sort, not price sort)
  if (!sort || sort === 'name') {
    results.sort((a, b) => (b.ft ? 1 : 0) - (a.ft ? 1 : 0));
  }

  currentResults = results;
  render();
  updateSubCTA(q);
  updateActiveFilters();
  updatePillCounts();
  syncURL();
}

function updateSubCTA(q) {
  const ctaEl = document.getElementById('subCTA');
  if (!ctaEl) return;
  const floatInput = document.getElementById('floatEmail');
  const subBtn = document.getElementById('subBtn');
  const subState = document.getElementById('subState');

  if (!q) {
    currentWatchSlug = null;
    ctaEl.innerHTML = `<strong>Get the free WA Rare Fruit Guide + restock alerts</strong> \u2014 free daily email, unsubscribe any time. <a href="/wa-rare-fruit-guide.html" class="text-green-700 underline whitespace-nowrap">Preview the guide \u2192</a>`;
    if (floatInput) floatInput.placeholder = 'Get daily alerts (free)';
    if (subBtn) subBtn.textContent = 'Subscribe free';
    if (subState) subState.style.display = '';
    return;
  }

  // Check if query matches a known species (try longest match first)
  const words = q.split(/\s+/);
  let matched = null;
  for (let n = words.length; n >= 1; n--) {
    const candidate = words.slice(0, n).join(' ');
    if (SPECIES_SLUGS[candidate]) {
      matched = SPECIES_SLUGS[candidate];
      break;
    }
  }

  if (matched) {
    const name = matched.name;
    const slug = matched.slug;
    // Species-level watches were removed (variety watches only, see commit 3f89a09).
    // A species pill/search subscribes to the general daily digest (which includes this
    // species); the link points to the species page where the per-variety watches live.
    currentWatchSlug = null;
    ctaEl.innerHTML = `<strong>Get free daily restock and price alerts.</strong> Unsubscribe any time. <a href="/species/${slug}.html" class="text-green-700 underline whitespace-nowrap">See all ${name} &rarr;</a>`;
    if (floatInput) floatInput.placeholder = 'Get daily alerts (free)';
    if (subBtn) subBtn.textContent = 'Subscribe free';
    if (subState) subState.style.display = '';
  } else {
    currentWatchSlug = null;
    const displayQ = q.length > 20 ? q.slice(0, 20) + '...' : q;
    ctaEl.innerHTML = `<strong>Get alerted when "${displayQ}" prices change.</strong> Free daily email, unsubscribe any time. <a href="/sample-digest.html" class="text-green-700 underline whitespace-nowrap">See example &rarr;</a>`;
    if (floatInput) floatInput.placeholder = `"${displayQ}" price alerts (free)`;
    if (subBtn) subBtn.textContent = 'Subscribe free';
    if (subState) subState.style.display = '';
  }
}

function setupWatchForm(formId, emailId, msgId) {
  const form = document.getElementById(formId);
  if (!form) return;
  form.addEventListener('submit', async function(e) {
    e.preventDefault();
    const email = document.getElementById(emailId).value.trim();
    const species = form.dataset.species;
    const msg = document.getElementById(msgId);
    const btn = form.querySelector('button');
    btn.disabled = true;
    btn.textContent = 'Watching...';
    try {
      const resp = await fetch('/api/subscribe', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({email, action: 'watch', species}),
      });
      const result = await resp.json();
      msg.classList.remove('hidden');
      msg.classList.add('text-green-700');
      msg.textContent = result.message === 'Already watching'
        ? 'You are already watching this.'
        : 'Done! We will email you when it comes in stock.';
      form.querySelector('input').disabled = true;
      btn.classList.add('hidden');
    } catch(err) {
      msg.classList.remove('hidden');
      msg.classList.add('text-red-600');
      msg.textContent = 'Something went wrong. Please try again.';
      btn.disabled = false;
      btn.textContent = 'Watch this';
    }
  });
}

function render() {
  const results = currentResults;
  const showing = results.slice(0, displayCount);
  const container = document.getElementById('results');
  const countEl = document.getElementById('resultCount');
  const loadMoreEl = document.getElementById('loadMore');

  countEl.textContent = `${results.length} result${results.length !== 1 ? 's' : ''}`;

  if (showing.length === 0) {
    const q = searchInput.value.trim();
    if (q) {
      const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
      const slug = q.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
      container.innerHTML =
        '<div class="py-10 px-4">' +
        '<p class="text-center text-gray-500 mb-5">Nothing found for <strong class="text-gray-600">' + esc(q) + '</strong></p>' +
        '<div class="max-w-sm mx-auto bg-green-50 border border-green-200 rounded-xl p-5">' +
        '<p class="text-sm font-semibold text-green-800 mb-1">Watch <span class="text-green-900">' + esc(q) + '</span></p>' +
        '<p class="text-xs text-gray-500 mb-3">Get an email when it comes into stock at any monitored nursery. Free.</p>' +
        '<form id="watchForm" data-species="' + slug + '" class="flex gap-2">' +
        '<input type="email" id="watchEmail" placeholder="your@email.com" required class="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500">' +
        '<button type="submit" class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium whitespace-nowrap">Watch this</button>' +
        '</form>' +
        '<div id="watchMsg" class="mt-2 text-sm hidden"></div>' +
        '</div></div>';
      setupWatchForm('watchForm', 'watchEmail', 'watchMsg');
    } else {
      container.innerHTML = '<div class="text-center py-12 text-gray-500">No plants found matching your filters.</div>';
    }
    loadMoreEl.classList.add('hidden');
    return;
  }

  container.innerHTML = showing.map(p => {
    const price = p.p ? ('$' + p.p.toFixed(2)) : '';
    const stockBadge = p.a
      ? `<span class="stock-badge in-stock">${p.s ? p.s + ' left' : 'In stock'}</span>`
      : '<span class="stock-badge out-stock">Out of stock</span>';
    // Show shipping restriction warnings for WA/NT/TAS (skip for local-delivery nurseries)
    const localArea = LOCAL_ONLY[p.nk];
    const nShips = SHIPS_TO[p.nk] || [];
    const restricted = ['WA','NT','TAS'].filter(s => !nShips.includes(s));
    const _st = stateFilter.value;
    const shipsBadge = localArea ? ''
      : (_st && !nShips.includes(_st))
        ? `<span class="stock-badge restrict-badge">No ${_st}</span>`
        : (restricted.length > 0 && restricted.length < 3 && !_st)
          ? `<span class="stock-badge restrict-badge">No ${restricted.join('/')}</span>`
          : '';
    const localBadge = localArea ? `<span class="stock-badge local-badge">${localArea} only</span>` : '';
    const saleBadge = p.sale ? '<span class="stock-badge sale-badge">Sale</span>' : '';
    const latinName = p.ln ? `<span class="text-xs text-gray-500 italic ml-1">${p.ln}</span>` : '';
    const cultivar = p.cv ? ` '${p.cv}'` : '';

    // Change indicators
    let changeBadge = '';
    if (p.ch === 'new') changeBadge = '<span class="stock-badge new-badge">New</span>';
    else if (p.ch === 'back') changeBadge = '<span class="stock-badge back-badge">Back in stock!</span>';
    else if (p.ch === 'gone') changeBadge = '<span class="stock-badge out-stock">Just sold out</span>';

    let priceInfo = price;
    if (p.ch === 'down' && p.pp) priceInfo = `<span class="price-down">${price}</span> <span class="text-xs text-gray-500 line-through">${('$' + p.pp.toFixed(2))}</span>`;
    else if (p.ch === 'up' && p.pp) priceInfo = `<span class="price-up">${price}</span> <span class="text-xs text-gray-500">was ${('$' + p.pp.toFixed(2))}</span>`;

    const utm = p.u ? (p.u.includes('?') ? '&' : '?') + 'utm_source=treestock&utm_medium=referral' : '';
    const featuredClass = p.ft ? ' featured-row' : '';
    const nurseryTagClass = p.ft ? 'nursery-tag featured-tag' : 'nursery-tag';
    const featuredBadge = p.ft ? '<span class="featured-badge">Featured</span>' : '';
    const rareBadge = (p.sl && HARD_TO_FIND.has(p.sl)) ? '<span class="stock-badge rare-badge" data-rare="1" role="button" tabindex="0" title="Show only hard-to-find varieties">Hard to find</span>' : '';
    // Badge bush tucker only: Fruit is the default and would just be noise on the
    // mixed homepage feed. Homepage only (gated on categoryFilter existing): the
    // /bush-tucker/ landing is already category-scoped, so a badge there is redundant.
    const catBadges = (categoryFilter && (SPECIES_CATS[p.sl] || []).includes('bush_tucker'))
      ? `<span class="cat-badge ${CAT_BADGE.bush_tucker[1]}" data-catfilter="bush_tucker" role="button" tabindex="0" title="Show only bush tucker" style="cursor:pointer">${CAT_BADGE.bush_tucker[0]}</span>`
      : '';
    let notifyLink = '';
    if (!p.a && p.vs) {
      notifyLink = VARIETY_IN_STOCK[p.vs]
        ? `<a href="/variety/${p.vs}.html" class="notify-link">In stock elsewhere &rarr;</a>`
        : `<a href="/variety/${p.vs}.html" class="notify-link">Notify me when it's back in stock</a>`;
    }
    return `<div class="product-row-wrap">
      <a href="${p.u}${utm}" target="_blank" rel="noopener" class="product-row${featuredClass} flex items-center gap-3 py-3 px-2 block">
      <div class="flex-1 min-w-0">
        <div class="font-medium text-sm">${p.t}${latinName}</div>
        <div class="flex items-center gap-1.5 mt-0.5 flex-wrap">
          <span class="${nurseryTagClass}" data-nk="${p.nk}">${p.n}</span>
          ${featuredBadge} ${catBadges} ${rareBadge} ${stockBadge} ${shipsBadge} ${localBadge} ${saleBadge} ${changeBadge}
        </div>
      </div>
      <div class="text-right flex-shrink-0">
        <div class="font-bold text-sm">${priceInfo}</div>
      </div>
    </a>${notifyLink}</div>`;
  }).join('');

  // Watch CTA: show when search results all out of stock
  const q2 = searchInput.value.trim();
  if (q2 && results.length > 0 && results.every(p => !p.a)) {
    const esc2 = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    const slug2 = q2.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
    const banner =
      '<div class="bg-green-50 border border-green-200 rounded-xl p-4 mb-3" id="watchBannerWrap">' +
      '<p class="text-sm font-semibold text-green-800">All <span class="text-green-900">' + esc2(q2) + '</span> listings are currently out of stock</p>' +
      '<p class="text-xs text-gray-500 mt-0.5 mb-2">Get an email when any come back in stock.</p>' +
      '<form id="watchBannerForm" data-species="' + slug2 + '" class="flex gap-2">' +
      '<input type="email" id="watchBannerEmail" placeholder="your@email.com" required class="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500 min-w-0">' +
      '<button type="submit" class="px-3 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium whitespace-nowrap">Watch</button>' +
      '</form>' +
      '<div id="watchBannerMsg" class="mt-2 text-sm hidden"></div>' +
      '</div>';
    container.insertAdjacentHTML('afterbegin', banner);
    setupWatchForm('watchBannerForm', 'watchBannerEmail', 'watchBannerMsg');
  }

  if (results.length > displayCount) {
    loadMoreEl.classList.remove('hidden');
  } else {
    loadMoreEl.classList.add('hidden');
  }
}

function showMore() {
  displayCount += 50;
  render();
}

// Active filter chips
function updateActiveFilters() {
  const el = document.getElementById('activeFilters');
  if (!el) return;
  const chips = [];
  if (activeSpeciesSlug) {
    const pill = document.querySelector('.species-pill[data-sl="' + activeSpeciesSlug + '"]');
    const name = pill ? pill.getAttribute('data-q') : activeSpeciesSlug;
    chips.push({label: name, action: 'species'});
  } else if (searchInput.value.trim()) {
    chips.push({label: '"' + searchInput.value.trim() + '"', action: 'search'});
  }
  const nursery = nurserySelect.value;
  if (nursery) {
    const opt = nurserySelect.options[nurserySelect.selectedIndex];
    const name = opt ? opt.textContent.split('(')[0].replace('* ','').trim() : nursery;
    chips.push({label: name, action: 'nursery'});
  }
  const st = stateFilter.value;
  if (st) chips.push({label: st, action: 'state'});
  const cat = categoryFilter ? categoryFilter.value : '';
  if (cat) chips.push({label: cat === 'bush_tucker' ? 'Bush Tucker' : 'Fruit', action: 'category'});
  if (changesOnly.checked) chips.push({label: 'Changes only', action: 'changes'});
  if (rareOnly) chips.push({label: 'Hard to find', action: 'rare'});

  if (chips.length === 0) {
    el.style.display = 'none';
    return;
  }
  el.style.display = 'flex';
  el.innerHTML = chips.map(c =>
    `<span class="filter-chip">${c.label} <button data-action="${c.action}" aria-label="Remove filter">&times;</button></span>`
  ).join('');
}

document.getElementById('activeFilters').addEventListener('click', function(e) {
  const btn = e.target.closest('button[data-action]');
  if (!btn) return;
  const action = btn.getAttribute('data-action');
  if (action === 'species') {
    activeSpeciesSlug = '';
    searchInput.value = '';
    document.querySelectorAll('.species-pill.active').forEach(p => p.classList.remove('active'));
  } else if (action === 'search') {
    searchInput.value = '';
  } else if (action === 'nursery') {
    nurserySelect.value = '';
  } else if (action === 'state') {
    stateFilter.value = '';
  } else if (action === 'category') {
    if (categoryFilter) categoryFilter.value = '';
  } else if (action === 'changes') {
    changesOnly.checked = false;
  } else if (action === 'rare') {
    rareOnly = false;
  }
  search();
});

// Update species pills: re-rank by current filters so each nursery shows its own top species
function updatePillCounts() {
  const stockOnly = inStockOnly.checked;
  const st = stateFilter.value;
  const nursery = nurserySelect.value;
  const changes = changesOnly.checked;

  const cat = categoryFilter ? categoryFilter.value : '';

  // Get the base filtered set (all filters except species)
  let base = P;
  if (stockOnly) base = base.filter(p => p.a);
  if (st) base = base.filter(p => (SHIPS_TO[p.nk] || []).includes(st));
  if (changes) base = base.filter(p => p.ch);
  if (nursery) base = base.filter(p => p.nk === nursery);
  if (cat) base = base.filter(p => (SPECIES_CATS[p.sl] || []).includes(cat));

  // Count per species slug
  const counts = {};
  base.forEach(p => {
    if (p.sl) counts[p.sl] = (counts[p.sl] || 0) + 1;
  });

  // Rank species present in the current view (highest count first, then A-Z). Show the
  // first `speciesShown`; the rest collapse into a clickable "Other (N)" pill that reveals
  // the next tier on click. One render path for both filtered and unfiltered views.
  const ranked = Object.entries(counts)
    .filter(([, c]) => c > 0)
    .sort((a, b) => b[1] - a[1]
      || (SLUG_TO_NAME[a[0]] || a[0]).localeCompare(SLUG_TO_NAME[b[0]] || b[0]));

  const shown = ranked.slice(0, speciesShown);
  const remaining = ranked.slice(speciesShown);
  const remainingProducts = remaining.reduce((sum, [, c]) => sum + c, 0);

  const strip = document.querySelector('.species-strip');
  let html = shown.map(([sl, count]) => {
    const name = SLUG_TO_NAME[sl] || sl.replace(/-/g, ' ').replace(/\\b\\w/g, c => c.toUpperCase());
    const active = sl === activeSpeciesSlug ? ' active' : '';
    return `<a href="/species/${sl}.html" class="species-pill${active}" data-q="${name}" data-sl="${sl}">${name} <span class="count">${count}</span></a>`;
  }).join('');
  if (remaining.length > 0) {
    html += `<span class="species-pill other-pill" id="otherPill">Other <span class="count" id="otherCount">${remainingProducts}</span></span>`;
  }
  strip.innerHTML = html;

  // Re-bind pill click handlers after rebuild
  strip.querySelectorAll('.species-pill[data-sl]').forEach(function(pill) {
    pill.addEventListener('click', function(e) {
      e.preventDefault();
      const sl = this.getAttribute('data-sl');
      const q = this.getAttribute('data-q');
      const isActive = this.classList.contains('active');
      strip.querySelectorAll('.species-pill.active').forEach(p => p.classList.remove('active'));
      if (isActive) {
        activeSpeciesSlug = '';
        searchInput.value = '';
      } else {
        activeSpeciesSlug = sl;
        searchInput.value = q;
        this.classList.add('active');
      }
      search();
      const results = document.getElementById('results');
      if (results) results.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  // "Other" pill reveals the next tier of species and keeps the strip expanded.
  const otherPill = document.getElementById('otherPill');
  if (otherPill) {
    otherPill.addEventListener('click', function() {
      speciesShown += SPECIES_TIER;
      strip.classList.add('expanded');
      updatePillCounts();
    });
  }

  // Re-check toggle button: show it when the strip overflows OR is explicitly expanded
  // (via "Show all" or "Other"); label is derived from state so it never fights an expand.
  const btn = document.getElementById('toggleSpecies');
  if (btn) {
    const expanded = strip.classList.contains('expanded');
    const overflowing = strip.scrollHeight > strip.clientHeight;
    if (expanded || overflowing) {
      btn.style.display = 'inline';
      btn.innerHTML = expanded ? 'Show less &#9652;' : 'Show all &#9662;';
    } else {
      btn.style.display = 'none';
    }
  }
}

// --- Search autocomplete (species-only) ---------------------------------
// Suggestions are built once from data already in memory (P, SPECIES_SLUGS,
// SLUG_TO_NAME); there is no network call and the species list is ~100 entries, so
// the filter runs synchronously on each keystroke (a debounce would only add lag).
// Selecting a suggestion reuses the species-pill contract: set activeSpeciesSlug,
// mirror the value into the box, run search(), and scroll to results.
const suggestBox = document.getElementById('searchSuggest');
const SUGGEST = (() => {
  const inStockBySlug = {};
  for (const p of P) { if (p.sl && p.a) inStockBySlug[p.sl] = (inStockBySlug[p.sl] || 0) + 1; }
  // One record per unique species slug, plus a flat match list over every
  // searchable string (canonical common name + each synonym key in SPECIES_SLUGS)
  // so a synonym query resolves to the species while the row shows the real name.
  const bySlug = {};
  const matches = [];
  Object.entries(SPECIES_SLUGS).forEach(([term, v]) => {
    if (!bySlug[v.slug]) bySlug[v.slug] = { slug: v.slug, name: v.name, inStock: inStockBySlug[v.slug] || 0 };
    matches.push({ term, slug: v.slug, isSyn: v.name.toLowerCase() !== term });
  });
  return { bySlug, matches };
})();
let suggestItems = [];
let suggestActive = -1;

function suggestFor(raw) {
  const q = raw.toLowerCase().trim();
  if (q.length < 2) return [];
  const prefix = [], substr = [];
  for (const m of SUGGEST.matches) {
    const idx = m.term.indexOf(q);
    if (idx === 0) prefix.push(m);
    else if (idx > 0) substr.push(m);
  }
  // Prefix matches first; within each group rank by in-stock count, then prefer the
  // canonical name over a synonym match, then alphabetical.
  const rank = (a, b) => {
    const sa = SUGGEST.bySlug[a.slug], sb = SUGGEST.bySlug[b.slug];
    return sb.inStock - sa.inStock
      || (a.isSyn ? 1 : 0) - (b.isSyn ? 1 : 0)
      || sa.name.localeCompare(sb.name);
  };
  prefix.sort(rank); substr.sort(rank);
  const out = [], seen = new Set();
  for (const m of prefix.concat(substr)) {
    if (seen.has(m.slug)) continue;
    seen.add(m.slug);
    const s = SUGGEST.bySlug[m.slug];
    out.push({ slug: s.slug, name: s.name, inStock: s.inStock, viaSyn: m.isSyn ? m.term : null });
    if (out.length >= 8) break;
  }
  return out;
}

function renderSuggest(items) {
  suggestItems = items;
  suggestActive = -1;
  searchInput.removeAttribute('aria-activedescendant');
  suggestBox.innerHTML = '';
  if (!items.length) { closeSuggest(); return; }
  // Build rows as DOM nodes (textContent) so curated names can never inject markup.
  items.forEach((it, i) => {
    const li = document.createElement('li');
    li.setAttribute('role', 'option');
    li.id = 'suggest-' + i;
    li.dataset.i = i;
    const nameSpan = document.createElement('span');
    nameSpan.className = 'suggest-name';
    nameSpan.textContent = it.name;
    if (it.viaSyn) {
      const syn = document.createElement('span');
      syn.className = 'suggest-syn';
      syn.textContent = '(' + it.viaSyn + ')';
      nameSpan.appendChild(syn);
    }
    const countSpan = document.createElement('span');
    countSpan.className = 'suggest-count';
    countSpan.textContent = it.inStock > 0 ? it.inStock + ' in stock' : 'out of stock';
    li.appendChild(nameSpan);
    li.appendChild(countSpan);
    suggestBox.appendChild(li);
  });
  suggestBox.hidden = false;
  searchInput.setAttribute('aria-expanded', 'true');
}

function closeSuggest() {
  suggestBox.hidden = true;
  suggestBox.innerHTML = '';
  suggestItems = [];
  suggestActive = -1;
  searchInput.setAttribute('aria-expanded', 'false');
  searchInput.removeAttribute('aria-activedescendant');
}

function setSuggestActive(i) {
  const lis = suggestBox.querySelectorAll('li');
  lis.forEach(li => li.classList.remove('active'));
  if (i >= 0 && i < lis.length) {
    lis[i].classList.add('active');
    lis[i].scrollIntoView({ block: 'nearest' });
    searchInput.setAttribute('aria-activedescendant', 'suggest-' + i);
    suggestActive = i;
  } else {
    suggestActive = -1;
    searchInput.removeAttribute('aria-activedescendant');
  }
}

function selectSuggestion(i) {
  const it = suggestItems[i];
  if (!it) return;
  document.querySelectorAll('.species-pill.active').forEach(p => p.classList.remove('active'));
  searchInput.value = it.name;
  activeSpeciesSlug = it.slug;
  closeSuggest();
  search();
  const results = document.getElementById('results');
  if (results) results.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

searchInput.addEventListener('keydown', function(e) {
  if (suggestBox.hidden || !suggestItems.length) {
    if (e.key === 'Escape') closeSuggest();
    return;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    setSuggestActive((suggestActive + 1) % suggestItems.length);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    setSuggestActive((suggestActive - 1 + suggestItems.length) % suggestItems.length);
  } else if (e.key === 'Enter') {
    e.preventDefault();
    selectSuggestion(suggestActive >= 0 ? suggestActive : 0);
  } else if (e.key === 'Escape') {
    e.preventDefault();
    closeSuggest();
  }
});
searchInput.addEventListener('focus', function() {
  if (suggestBox.hidden) renderSuggest(suggestFor(searchInput.value));
});
searchInput.addEventListener('blur', function() {
  // Delay so a click on a suggestion (which blurs the input) still registers.
  setTimeout(closeSuggest, 150);
});
// mousedown (not click) + preventDefault keeps focus on the input and beats blur.
suggestBox.addEventListener('mousedown', function(e) {
  const li = e.target.closest('li[data-i]');
  if (!li) return;
  e.preventDefault();
  selectSuggestion(parseInt(li.dataset.i, 10));
});
suggestBox.addEventListener('mousemove', function(e) {
  const li = e.target.closest('li[data-i]');
  if (li) setSuggestActive(parseInt(li.dataset.i, 10));
});

// Event listeners
searchInput.addEventListener('input', function() {
  // Clear active pill and species filter when user types manually
  activeSpeciesSlug = '';
  document.querySelectorAll('.species-pill.active').forEach(p => p.classList.remove('active'));
  search();
  renderSuggest(suggestFor(searchInput.value));
});
inStockOnly.addEventListener('change', search);
stateFilter.addEventListener('change', function() {
  search();
  // Sync subscribe state dropdown with search filter
  const subState = document.getElementById('subState');
  if (subState && stateFilter.value) subState.value = stateFilter.value;
});
changesOnly.addEventListener('change', search);
nurserySelect.addEventListener('change', search);
sortBy.addEventListener('change', search);
if (categoryFilter) categoryFilter.addEventListener('change', search);

// Show/hide species pill toggle button + initial pill click binding
(function() {
  const strip = document.querySelector('.species-strip');
  const btn = document.getElementById('toggleSpecies');
  if (strip && btn) {
    if (strip.scrollHeight > strip.clientHeight) btn.style.display = 'inline';
    btn.addEventListener('click', function() {
      strip.classList.toggle('expanded');
      this.innerHTML = strip.classList.contains('expanded') ? 'Show less &#9652;' : 'Show all &#9662;';
    });
  }
  // Initial pill click binding (updatePillCounts rebinds after rebuilds)
  updatePillCounts();
})();

// Nursery tag click: filter by nursery; Hard-to-find badge click: toggle rare filter
document.getElementById('results').addEventListener('click', function(e) {
  const tag = e.target.closest('.nursery-tag[data-nk]');
  if (tag) {
    e.preventDefault();
    e.stopPropagation();
    nurserySelect.value = tag.getAttribute('data-nk');
    search();
    window.scrollTo({ top: 0, behavior: 'smooth' });
    return;
  }
  const catTag = e.target.closest('.cat-badge[data-catfilter]');
  if (catTag && categoryFilter) {
    e.preventDefault();
    e.stopPropagation();
    categoryFilter.value = catTag.getAttribute('data-catfilter');
    search();
    window.scrollTo({ top: 0, behavior: 'smooth' });
    return;
  }
  const rare = e.target.closest('.rare-badge[data-rare]');
  if (rare) {
    e.preventDefault();
    e.stopPropagation();
    rareOnly = !rareOnly;
    search();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
});

// Restore filter state from the URL so filtered views are shareable/bookmarkable.
// Runs before the initial search() below; that single search() renders AND
// re-canonicalises the URL via syncURL(). Order matters: set JS vars + DOM controls
// here, then let search() -> updatePillCounts() re-apply the species-pill .active class
// from activeSpeciesSlug. Setting searchInput.value by assignment does not fire 'input',
// so the autocomplete box stays closed and activeSpeciesSlug isn't clobbered.
(function restoreFromURL() {
  const params = new URLSearchParams(window.location.search);
  const get = k => params.get(k) || '';
  // Validate against real <option>s so a junk/stale param can't break a control.
  const optOk = (sel, v) => v && sel.querySelector(`option[value="${CSS.escape(v)}"]`);

  const speciesParam = get('species');
  if (speciesParam && SLUG_TO_NAME[speciesParam]) {
    activeSpeciesSlug = speciesParam;
    searchInput.value = SLUG_TO_NAME[speciesParam]; // mirror the pill-click contract
  } else if (params.has('q')) {
    searchInput.value = get('q');
  }
  if (get('stock') === '1') inStockOnly.checked = true;
  if (get('changes') === '1') changesOnly.checked = true;
  if (get('rare') === '1') rareOnly = true;

  if (optOk(stateFilter, get('state'))) {
    stateFilter.value = get('state');
    const subState = document.getElementById('subState'); // mirror the live change-listener
    if (subState) subState.value = get('state');
  }
  // categoryFilter is null on /bush-tucker/ -- guard (page is already category-scoped).
  if (categoryFilter && optOk(categoryFilter, get('cat'))) categoryFilter.value = get('cat');
  // nursery: keep backward-compatible with the old ?nursery= behavior.
  if (optOk(nurserySelect, get('nursery'))) nurserySelect.value = get('nursery');
  if (optOk(sortBy, get('sort'))) sortBy.value = get('sort');
})();

// Initial render (also re-canonicalises the URL through syncURL())
search();

// Subscribe form (context-aware: species watch or general daily alert)
document.getElementById('subscribeForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const email = document.getElementById('subEmail').value.trim();
  const stateEl = document.getElementById('subState');
  const state = stateEl ? stateEl.value : 'ALL';
  const msg = document.getElementById('subMessage');
  const btn = document.getElementById('subBtn');
  const watchSlug = currentWatchSlug;
  btn.disabled = true;
  btn.textContent = watchSlug ? 'Setting alert...' : 'Subscribing...';

  let payload;
  if (watchSlug) {
    payload = {email, action: 'watch', species: watchSlug};
  } else {
    payload = {email, state};
  }

  try {
    const resp = await fetch('/api/subscribe', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (resp.ok) {
      if (watchSlug && resp.status === 201) {
        const speciesName = SLUG_TO_NAME[watchSlug] || watchSlug;
        msg.textContent = `Watching ${speciesName} \u2014 we\u2019ll email you when any ${speciesName} variety comes back in stock.`;
      } else if (watchSlug && resp.status === 200) {
        const speciesName = SLUG_TO_NAME[watchSlug] || watchSlug;
        msg.textContent = `You\u2019re already watching ${speciesName}.`;
      } else if (resp.status === 202) {
        msg.textContent = `Check your email \u2014 we sent you a confirmation link.`;
        document.getElementById('subEmail').value = '';
      } else if (resp.status === 201) {
        msg.textContent = `Subscribed! You'll get tomorrow\u2019s changes in your inbox.`;
      } else {
        msg.textContent = data.message || 'You\u2019re already subscribed.';
      }
      msg.className = 'mt-2 text-sm text-green-600';
      if (resp.status === 201) {
        document.getElementById('subEmail').value = '';
        localStorage.setItem('ts_subscribed', '1');
      }
    } else {
      msg.textContent = data.error || 'Something went wrong. Try again.';
      msg.className = 'mt-2 text-sm text-red-600';
    }
    msg.classList.remove('hidden');
  } catch (err) {
    msg.textContent = 'Something went wrong. Try again later.';
    msg.className = 'mt-2 text-sm text-red-600';
    msg.classList.remove('hidden');
  }
  btn.disabled = false;
  btn.textContent = watchSlug ? `Watch ${SLUG_TO_NAME[watchSlug] || watchSlug}` : 'Subscribe free';
});

// Floating subscribe bar (mobile only — shows after scroll or timer)
(function() {
  if (localStorage.getItem('ts_subscribed')) return;
  // 3-day dismiss cooldown (not per-session, so returning visitors still see it)
  const dismissedUntil = localStorage.getItem('ts_bar_dismissed_until');
  if (dismissedUntil && Date.now() < parseInt(dismissedUntil, 10)) return;

  const bar = document.getElementById('floatBar');
  if (!bar) return;

  // Sync placeholder text with main CTA if it has been updated
  const subCTA = document.getElementById('subCTA');
  const floatInput = document.getElementById('floatEmail');
  if (subCTA && floatInput) {
    const ctaText = subCTA.innerText || '';
    if (ctaText.includes('Get alerted when') && ctaText.length < 80) {
      floatInput.placeholder = ctaText.replace('Get alerted when', 'Alert me when').replace(' — free daily email', '').trim().slice(0, 50) || 'Get daily alerts (free)';
    }
  }

  let shown = false;
  function showBar() {
    if (shown) return;
    shown = true;
    bar.classList.remove('translate-y-full');
    bar.classList.add('translate-y-0');
  }

  // Show after 150px scroll (was 300px — show sooner)
  window.addEventListener('scroll', function() {
    if (!shown && window.scrollY > 150) showBar();
  }, { passive: true });

  // Also show after 40 seconds even without scrolling (time-based fallback)
  setTimeout(showBar, 40000);

  document.getElementById('floatDismiss').addEventListener('click', function() {
    // 3-day cooldown — won't pester same-day, but will show to return visitors
    localStorage.setItem('ts_bar_dismissed_until', Date.now() + 3 * 24 * 60 * 60 * 1000);
    bar.classList.add('translate-y-full');
  });

  document.getElementById('floatForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    const email = document.getElementById('floatEmail').value.trim();
    const stateEl = document.getElementById('subState');
    const state = stateEl ? stateEl.value : 'ALL';
    const watchSlug = currentWatchSlug;
    const btn = e.target.querySelector('button[type=submit]');
    btn.disabled = true;
    btn.textContent = '...';

    let payload;
    if (watchSlug) {
      payload = {email, action: 'watch', species: watchSlug};
    } else {
      payload = {email, state};
    }

    try {
      const resp = await fetch('/api/subscribe', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      if (resp.status === 202) {
        bar.innerHTML = `<div class="flex items-center justify-center gap-2 py-3 px-4 text-sm text-white font-medium">Check your email \u2014 we sent a confirmation link.</div>`;
        setTimeout(function() { bar.classList.add('translate-y-full'); }, 4000);
      } else if (resp.status === 201 || resp.status === 200) {
        localStorage.setItem('ts_subscribed', '1');
        const confirmMsg = watchSlug
          ? `Alert set! We\u2019ll email when ${SLUG_TO_NAME[watchSlug] || watchSlug} is back in stock.`
          : `Subscribed! You\u2019ll get tomorrow\u2019s changes in your inbox.`;
        bar.innerHTML = `<div class="flex items-center justify-center gap-2 py-3 px-4 text-sm text-white font-medium">${confirmMsg}</div>`;
        setTimeout(function() { bar.classList.add('translate-y-full'); }, 3000);
      } else {
        btn.disabled = false;
        btn.textContent = 'Subscribe';
        document.getElementById('floatMsg').textContent = data.message || 'Try again';
        document.getElementById('floatMsg').classList.remove('hidden');
      }
    } catch(err) {
      btn.disabled = false;
      btn.textContent = 'Subscribe';
    }
  });
})();

