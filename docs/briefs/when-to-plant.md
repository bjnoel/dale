# Brief: re-home and improve the "When to Plant" guide

## Status (verified 2026-05-31)

`treestock.com.au/when-to-plant.html` is LIVE (HTTP 200), built 2026-03-28 (DEC-100), titled
"When to Plant Fruit Trees in Australia". It already has good bones: an Australian climate-zones
section, a bare-root emphasis, a by-species planting calendar, an FAQ, an alerts CTA, and a
related-guides block.

It is, however, an ORPHANED static artifact:
- No builder in the repo regenerates it (grep finds references only in the sitemap, gsc_submit,
  nav and the companion guide; none write it). No build_when*/build_planting* script exists.
- It is not tracked in git as HTML, run-all-scrapers.sh does not rebuild it, and its file mtime
  has been frozen at Mar 28 ever since.
- It has zero external citations, references an unversioned /styles.css, and uses a few em dashes.

So this is an "improve and re-home", not a build-from-scratch, and NOT a 404 fix (an earlier
note wrongly said 404 before the URL was fetched).

## Goal

Recreate a maintainable builder that regenerates an improved, current version matching the
companion guide's quality bar, and wire it into the daily pipeline so it never goes stale again.
Keep the good existing structure (zones, bare-root, by-species calendar) and upgrade it.

## Template and quality bar

Read tools/scrapers/build_companion_guide.py (generated builder, evidence/honesty framing,
per-item citations, internal /species/ deep-links validated against fruit_species.json, FAQPage
JSON-LD, OG tags, no em dashes) and tests/test_companion_guide.py first; mirror them.

- Accuracy here is mostly about CLIMATE ZONES, not myth-busting: Australia spans tropical,
  subtropical, arid, warm-temperate/Mediterranean and cool/cold zones, and the right planting
  time varies hugely between them. Wrong-zone or wrong-frost advice kills plants, so zone
  correctness and frost/chill accuracy are the top priority (the analogue of "no bad info").
- Australia-wide, not WA-centric. No "ships to WA" badges. No em dashes (CLAUDE.md).
- Cite authoritative AU sources and link to relevant articles.

## First step: capture the current page

Before changing anything, fetch the live page (curl from the server to /tmp, the public URL
403s to bots) and record its current sections, facts and structure so the rewrite preserves
what already works and you can diff old vs new.

## Substance to cover (verify all of it, do not assume)

- Bare-root season: deciduous fruit (apple, pear, stone fruit, fig, mulberry, grape, persimmon,
  pomegranate) is sold and best planted bare-root in winter while dormant (~June to August in
  the south), cheaper and best establishment. This is the single most important timing fact and
  a natural treestock hook (nurseries release bare-root stock in winter, track restocks).
- Evergreen/subtropical/tropical (citrus, avocado, mango, lychee, banana) plant in spring into
  warming soil once frost risk passes, not into cold wet winter soil.
- A clear AU zone model (e.g. ABC Gardening Australia / BOM: tropical, subtropical, arid,
  temperate, cool) with planting timing per zone, ideally a zone x fruit-type matrix and/or a
  season-by-season view (the existing page's climate-zone framing is a good base).
- Frost / last-frost dates, chill-hour requirements for deciduous (tie to variety choice), soil
  temperature, establishment watering, and what to avoid (frost-tender stock before last frost,
  planting into hot dry midsummer without irrigation).

## Research (fan out agents, like the companion guide)

Run a workflow fanning out per climate zone and per fruit category (deciduous/bare-root, citrus,
subtropical, tropical), plus cross-cutting themes (bare-root handling, frost/chill, soil
temperature and spring planting, establishment). Gather and adversarially verify against AU
authorities: state ag/primary-industries departments (Agriculture Victoria, NSW DPI, DPIRD WA,
QLD DAF, PIRSA), ABC Gardening Australia, Sustainable Gardening Australia, Diggers Club, and
reputable AU nursery planting guides (Daleys, Yates, bare-root specialists). Prefer .gov.au and
extension; tag and down-weight community/forum sources. Synthesise into the page data, record
what you corrected, and verify every cited URL resolves.

## Engineering

- Create tools/scrapers/build_when_to_plant.py modelled on build_companion_guide.py, using
  treestock_layout (render_head/header/breadcrumb/footer; extra_head for FAQ JSON-LD;
  og_type="article"; og_image; this also fixes the unversioned styles.css link). Reproduce and
  upgrade the existing sections (climate zones, by-species calendar) and add per-item citations,
  a references section, and internal /species/ deep-links via load_valid_species_slugs()
  (validated, no 404s). Drop the em dashes.
- KEY FIX: register the builder in tools/scrapers/run-all-scrapers.sh (add a build step writing
  to the dashboard dir, like the companion guide) so the page regenerates daily instead of
  staying frozen. It is already in the sitemap, nav and gsc_submit, so no change needed there.
- Add tests/test_when_to_plant.py mirroring test_companion_guide.py (build runs, required keys,
  https sources, rel=noopener, no em/en dashes, internal /species/ links validated, FAQ JSON-LD
  parses). Keep `python3 -m unittest discover tests/` green.

## Process

- Another agent may be working this repo concurrently: work in an isolated git worktree on your
  own branch (see memory feedback_parallel_agent_worktree), stage only your files, and finish by
  pushing + merging rather than editing the shared working dir.
- Deploy like the companion guide: merge to main, then on the server (ssh dale-server) git pull,
  run tools/deploy.sh, run the new builder into /opt/dale/dashboard, and rebuild the purged
  Tailwind CSS:
    tailwindcss --input /opt/dale/scrapers/tailwind-input.css \
      --output /opt/dale/dashboard/styles.css \
      --content "/opt/dale/dashboard/**/*.html" --minify
  NEVER scp.
- Verify the live URL returns 200 with the new content and a FRESH file mtime (proving the
  builder ran), and that the nav and sitemap entries still resolve.

## Optional, related

The companion guide's third CTA was repointed from /when-to-plant.html to /rare.html on the
mistaken belief the page was a 404. Since the planting calendar is live and topically relevant,
consider restoring that CTA in build_companion_guide.py (the CTA block in build_page()).

Log a DEC entry and a public-ledger note when done.
