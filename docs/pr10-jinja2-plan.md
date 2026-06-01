# PR10 plan: de-fork the layout + adopt Jinja2 autoescape

Final piece of the treestock `stocklib` scalability refactor. Written for a fresh
session with no memory of the refactor work. Read the Context section first.

## Context (what already exists)

The refactor landed 12 PRs (main `dca73b4` .. `45e0b11`, 2026-06-01). The shared
package is **`tools/scrapers/stocklib/`** with: `model`, `snapshots`, `registry`,
`taxonomy`, `classify`, `changes`, `email_footer`. Conventions are in CLAUDE.md
under "Shared code (stocklib)". It ships via the existing rsync deploy (no infra
change); top-level `tools/scrapers/` scripts import it for free, `tools/scrapers/bee/`
scripts add the parent dir to `sys.path` first (see how `bee_daily_digest.py`
does it).

The risky **logic** fork (the daily-digest comparison engine) is already removed
(PR7) and shared in `stocklib.changes`. What remains for PR10 is **presentation**:
the `beestock_layout.py` fork, and un-escaped HTML interpolation across the page
builders. This is polish, not correctness-critical, so it was deferred to its own
session because Part B below changes every page's bytes.

Two independent goals, best shipped as separate PRs:
- **PR10a (low risk, byte-stable):** de-fork the layout. Share head/header into
  `stocklib/layout.py` via a `SiteConfig`; delete most of `beestock_layout.py`.
- **PR10b (output-changing):** adopt Jinja2 `autoescape` for the ~16 page builders
  so untrusted nursery titles are HTML-escaped. Changes output (entity-escaping),
  so it is SEO-sensitive and needs per-page review + live browser checks.

## Infrastructure to use (already in place)

- **Golden SEO net:** `tests/test_golden.py` (a `GOLDEN_CASES` table) + `tests/golden_runner.py`
  (runs a builder against `tests/golden/fixture/nursery-stock/`, normalises dates,
  compares to `tests/golden/expected/`). Regenerate after an intended change:
  `GOLDEN_UPDATE=1 python3 tests/test_golden.py`. Currently covers dashboard,
  variety, compare, location, species_state. **Add the builder you are migrating to
  `GOLDEN_CASES` and capture its baseline BEFORE migrating it.**
- **Anti-drift:** `tests/test_no_forking.py` -- extend it once de-forked (assert
  `render_head` / `render_footer` are defined only in `stocklib/layout.py`).
- **All tests:** `python3 -m unittest discover tests/` (stdlib unittest, no pytest).
- **Real-data smoke:** run builders against `/Users/bjnoel/Projects/dale/data/nursery-stock/`
  (the live gitignored snapshots, ~9,883 products) into a temp dir; confirm sane page
  counts and no crash.
- **Browser verify (recipe that worked for PR3):**
  `python3 -m http.server 8127 --directory <built-output-dir>`, then Chrome MCP:
  `tabs_context_mcp` -> `tabs_create_mcp` -> `navigate("http://localhost:8127/")`
  (the user must approve the navigate permission prompt) -> `javascript_tool`
  (e.g. count `#results` children, drive the `#search` input) + `read_console_messages(onlyErrors=true)`.
  Copy `static/dashboard.js` into the served dir; styles.css is optional (unstyled
  but functional). Verify titles with special chars (e.g. "Diggers' Club", "Fig & Olive")
  render as text, not raw entities.
- **Deploy:** commit -> hourly `dale-runner` does `git pull --ff-only` + `deploy.sh`
  rsync -> daily `run-all-scrapers.sh` builds. **Jinja2 must be `pip install`ed in the
  VPS build environment** (Part B) -- coordinate with Benedict; add to a requirements
  file if one exists.

## PR10a -- de-fork the layout (byte-stable, no Jinja2 needed)

The layout interpolates **trusted** values (site name, nav, canonical URL), so
autoescape adds little here; keep f-strings and aim for byte-identical output.

Findings -- how the two modules differ (this is why a plain "swap a constant"
share does not work; carry these in `SiteConfig`):

| | `treestock_layout.py` (311 ln) | `bee/beestock_layout.py` (206 ln) |
|---|---|---|
| SITE_NAME/URL | treestock.com.au | beestock.com.au |
| TAILWIND_CSS | `/styles.css?v=YYYYMMDD` (cache-buster) | `/styles.css` (none) |
| PLAUSIBLE_SCRIPT | outbound-links script | different (pa script + init) |
| NAV_ITEMS | Search, Species, Nurseries, Varieties, ... | Search, Categories, Retailers, ... |
| LOGO_SVG | tree (green #065f46/#22c55e) | hexagon (brown #92400e/#f59e0b) |
| favicon | `/favicon.svg` (file `<link>`) | `FAVICON_DATA_URI` (base64 data-uri) |
| footer | state-links + Treesmith promo + `extra_text` | simpler, none of those |
| default max_width | `max-w-3xl` | `max-w-5xl` |
| functions | render_head/header/breadcrumb/footer + render_treesmith_promo + render_page | render_head/header/breadcrumb/footer only |

Steps:
1. `stocklib/layout.py`: a `@dataclass SiteConfig` holding all the variation above
   (site_name, site_url, tailwind_href, plausible_script, nav_items, logo_svg,
   favicon_html, base_style, default_max_width, and footer pieces).
2. Move `render_head`, `render_header`, `render_breadcrumb` into `stocklib/layout.py`,
   taking a `SiteConfig`. Keep them f-strings (byte-stable).
3. `treestock_layout.py` -> `TREESTOCK = SiteConfig(...)` plus `render_head/header/breadcrumb`
   bound to it, so existing `from treestock_layout import render_head` keeps working
   for all builders. Keep `render_footer`, `render_treesmith_promo`, `render_page`
   treestock-side (the footer differs structurally).
4. `beestock_layout.py` -> `BEE = SiteConfig(...)` + bound `render_*`; keep bee's footer.
   ~206 lines collapse to ~30 of config.
5. **Verify byte-stable:** treestock via the golden net (regenerate; expect NO diff).
   bee via a before/after characterisation (render a bee page with a bee builder
   before the change, save HTML, after the change re-render, `diff` -- identical).
   See the PR7b commit for the before/after characterisation pattern.
6. Extend `test_no_forking.py`: `render_head`/`render_header` only in `stocklib/layout.py`.
7. Browser-verify a treestock page and a beestock page render correctly.

Decision: footers differ structurally. Simplest is to keep `render_footer` per-site
(still de-forks the head/header bulk). Optionally parameterise the footer via
SiteConfig later.

## PR10b -- Jinja2 autoescape for the body builders (output-changing)

The win: nursery titles (untrusted) are interpolated into HTML today **without
escaping** -- an `&`, `<`, or quote in a title produces invalid/broken markup or a
broken attribute. Jinja2 `autoescape` fixes that. It **changes output** (adds
entity-escaping), so treat the golden diff as "review", not "must be identical".

Steps (one builder at a time, simplest first):
1. Add Jinja2 (pure-Python). Build a Jinja2 `Environment(autoescape=True,
   trim_blocks=True, lstrip_blocks=True, loader=FileSystemLoader(stocklib/templates/))`.
2. Order: lowest-traffic / least-untrusted-data first (`build_companion_guide`,
   `build_treesmith_page`, `build_sample_digest`), then medium (`build_nursery_pages`,
   `build_compare_pages`), **SEO-critical last** (`build_species_pages`,
   `build_variety_pages`, `build_location_pages`, `build_species_state_pages`).
3. Per builder:
   a. Ensure it is in `GOLDEN_CASES`; capture the baseline on the PRE-migration code.
   b. Convert its body f-string to a `stocklib/templates/<name>.html.j2` rendered with
      the same context.
   c. Regenerate the golden; the diff will show entity-escaping of interpolated values.
   d. **Confirm the diff is escaping-only** (no content/structure change). Automated
      check: `import html; html.unescape(new) == html.unescape(old)` over the page --
      if equal, only escaping changed. Then eyeball it.
   e. **Watch for double-escaping:** if the builder already escaped some value
      manually (`html.escape`, or literal `&amp;`), autoescape will double it
      (`&amp;amp;`). Remove the now-redundant manual escaping.
   f. Browser-verify the page renders (special-char titles show as text, not entities).
4. `build-dashboard.py` is LOW priority for Jinja2: its interactive body is the
   external `static/dashboard.js` (PR3) and its data goes through a JSON island (not
   HTML interpolation), so the escaping risk there is small. Do it last or skip.
5. Once builders render via Jinja2 templates that `{% include %}` the shared layout
   (from PR10a), the layout itself can become Jinja2 base templates (optional).

## Gotchas

- Jinja2 whitespace handling differs from f-strings. Use `trim_blocks`/`lstrip_blocks`;
  expect minor whitespace diffs; decide per builder whether to match exactly or
  regenerate + accept (golden shows them).
- `tests/golden_runner.py` already normalises `?v=YYYYMMDD`, `Updated YYYY-MM-DD`, and
  `"1 June 2026"`. Extend `_NORMALISERS` if a builder uses another volatile token.
- bee builders import `stocklib` only after `sys.path.insert(0, parent.parent)`.
- autoescape is the point -- do NOT disable it to force byte-stability. Accept the
  escaping diffs and verify they are escaping-only.
- The `\s` SyntaxWarning in build-dashboard.py / build_bee_dashboard.py is pre-existing
  (an unescaped regex in the embedded JS); orthogonal to PR10.

## Per-PR verification checklist

- `python3 -m unittest discover tests/` green.
- Golden regenerated; diffs confirmed escaping-only (`html.unescape` equality) + eyeballed.
- Real-data smoke build against the live snapshots; sane page counts; no crash.
- Browser: serve built output, Chrome MCP, confirm render + (dashboard) search/filter,
  no console errors, special-char titles correct.
- `test_no_forking.py` updated for any newly shared symbols.

## Suggested breakdown

- **PR10a:** layout de-fork (head/header shared via `SiteConfig`; bee fork deleted;
  byte-stable).
- **PR10b-1 .. PR10b-n:** Jinja2 autoescape, a few builders per PR, simplest ->
  SEO-critical, each golden + browser verified.
- **PR10c (optional):** layout as Jinja2 base templates once builders are on Jinja2.
