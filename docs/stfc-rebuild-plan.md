# STFC (stfc.org.au) rebuild plan

**Status:** phases 0-4 executed 2026-07-28. Preview is live at
<https://stfc-preview.pages.dev>; reply drafted at `docs/stfc-reply-draft.md`,
awaiting Benedict's review before sending.
**Date:** 2026-07-28
**Repo:** `/Users/bjnoel/Projects/stfc-web` (separate from dale, see "Why a separate repo")

## What changed on execution

Three assumptions in this plan turned out to be wrong. Corrected in place below,
recorded here so the reasoning is not lost:

1. **No crawler was needed.** stfc.org.au exposes `/wp-json/wp/v2` publicly, so
   the whole library came across as structured records (title, slug, content,
   category, dates) in about fifteen seconds. Phase 0 became `tools/harvest.py`,
   an API client rather than an HTML crawler, and Phase 1 never had to strip
   theme cruft.
2. **There are 23 genuine duplicate pairs, not one.** The plan claimed only
   `propagating`/`propagating-2` was a real duplicate. In fact 23 entries are
   published twice, almost always the same text filed under two different
   sections (`/recipes/mango/` and `/articles/mango-2/`). Only
   `white-sapote`/`white-sapote-2` is a false pair. This is a stronger pitch
   point than the plan assumed, not a weaker one.
3. **Recipes is 42 entries, not 29**, and the `-2` suffix affects 142 URLs, not
   134. The original figures came from crawling section listings, which
   undercount.

One thing the plan worried about turned out to be a non-issue: image migration.
The entire corpus contains 63 images across 22 entries.

## The deal being pitched

Free/nominal rebuild, $20/month hosting and upkeep retainer, in exchange for permanent
treestock + Treesmith links and one club newsletter feature at launch. Full context in
the Dale memory file `project_stfc_rebuild.md`.

The immediate trigger: the STFC contact asked whether Benedict has built other sites like
what he is proposing. The answer is a working preview of *their* site, not a portfolio
link.

## Hard constraints

1. **No WordPress export.** They are not technical and we do not want to hassle them for
   admin access before they commit. Everything comes from crawling the public site.
2. **Nothing spent.** Crawl is free, Cloudflare Pages is free, tagging costs cents.
3. **No commitment from them yet.** Cap pre-commitment effort and keep everything built
   reusable if they say no.
4. **Benedict's time is the scarce resource.** His cost here should be reviewing a preview
   and sending one email.

## Inventory (crawled 2026-07-28)

Corrected against the WordPress API, 2026-07-28.

| Section | Entries | Notes |
|---|---|---|
| Articles | 261 | Median 774 words |
| Tips | 175 | Median 180 words. Same kind of thing as Articles, shorter |
| Recipes | 42 | |
| Pests | 7 | |
| Diseases | 2 | Holds a top-level nav slot for two entries |
| About | 10 | Includes one copy of the air-layering article |
| Links | 9 | A link directory, not entries |
| Videos, RFC | 1 each | |

507 posts plus 20 standalone pages. Empty robots.txt. WordPress, with both
Gutenberg and Elementor installed and legacy markup still in place on older
entries.

**142 URLs carry the meaningless `-2` suffix.** 120 are orphans that clean
straight to a bare slug. The remaining 22 collide with an existing slug, and in
all but one case (`white-sapote`) that is because the same article was published
twice. 23 duplicate pairs in total.

After merging duplicates and dropping the link directories, **473 canonical
entries**.

## Diagnosis of what is actually wrong

Verified, not assumed:

- **`/articles` is a wall of ~261 justified blue links.** The stretched word spacing is
  `text-align: justify` applied to a link list, a theme bug rather than a content problem.
  No grouping, no search, no filter, no per-article description. You can only find an
  article you can already name. Brutal on a phone.
- **Prev/next is meaningless.** "Air Layering / Marcotting" is followed by "Visiting Nguon
  & Han Kov". WordPress orders by post ID, so adjacency carries no information. This is
  the complaint the client raised unprompted.
- **No metadata anywhere.** Confirmed against the API: `wp/v2/tags` returns 0, 505 of
  507 posts sit under one login, and the publish dates are import timestamps (206 posts
  stamped 2023-10, 129 stamped 2020-04). Sources are raw inline text ("Texas A & M",
  "Ref: Oscar - Hawaii", "Ref: Joe Real").
- **Nav is 12 items over two rows in alphabetical order**, so section prominence bears no
  relation to section size (Diseases: 2 entries; Tips: 175).

The missing metadata is the opportunity, not a loss. Because there are no tags or excerpts
to migrate, we generate them, and that is exactly what makes a searchable, filterable,
related-articles index possible. It is the single biggest visible upgrade and it does not
depend on getting a WP export.

## Phases

### Phase 0 — Harvest (Dale, ~1-2h)

- Polite crawler in `stfc-web/tools/crawl.py`: identify in User-Agent, rate limit, cache
  every response to disk so re-runs cost nothing.
- Pull all ~474 entries plus the static pages, keeping raw HTML.
- Grab linked images from the WP uploads directory at whatever resolution is public.
- Output an inventory report (counts, URL map, orphan and duplicate detection).

The inventory report is itself a pitch artifact. "You have 261 articles, 175 tips, and 134
URLs with a broken suffix" is a concrete demonstration of attention before any design.

### Phase 1 — Content pipeline (Dale, ~2-3h)

- HTML to clean markdown, stripping WP theme cruft, shortcodes and inline styles.
- Land as Astro content collections: `articles`, `tips`, `recipes`, `pests-diseases`.
- **Generate tags** from title plus opening paragraph (propagation, pest control, citrus,
  variety notes, and per-fruit tags). Cheap model, run over all entries.
- **Generate a one-line excerpt** per entry for the index.
- Extract inline source references into structured frontmatter, mirroring the treestock
  `stocklib/citations.py` pattern.
- Build the old-URL to new-URL redirect map (the 134 `-2` slugs).

Everything generated is committed as data, so the rebuild stays a dumb renderer over
reviewable content. Same architecture as treestock's growing_guides and
variety_descriptions layers.

### Phase 2 — Astro build (Dale, 1-2 sessions)

Scaffold from scratch, skeleton lifted from treesmith-web rather than a marketing template.

Two pages only, because these are the two that prove the hard problems are solved:

1. **`/articles` index.** Search, topic filter, tag pills, one-line excerpt per entry, all
   261 entries real. This is the hero.
2. **The air-layering article page.** Proper typography, structured sources, and
   **tag-driven "More on propagation" replacing prev/next.** This directly answers the
   complaint she raised.

**Two design directions, not three.** Split on a meaningful axis so her pick settles the
information architecture rather than just a colour:

- **A, community club:** member photos, meetings, harvests, warmer, people-forward.
- **B, reference library:** clean, encyclopedic, typography-led, content-forward.

Three variants invites "the header from A with the body of C" and design-by-committee.

Skip the homepage. Everyone already knows what a homepage looks like, and it is the page
most likely to trigger committee opinions before the real work is judged.

### Phase 3 — Preview deploy (Dale, ~30m)

Cloudflare Pages preview URL, clickable on a phone. Not a claude.ai link and not image
attachments: a real site on real infrastructure reads as competence.

### Phase 4 — The reply (Benedict sends, Dale drafts)

One message that:

- Answers the portfolio question with **treestock.com.au** (~4,000 variety pages, species
  pages per state, 42 growing guides, live search, filters, citations). Do NOT lead with
  bjnoel.com or treesmith.app, they are brochure sites and undersell him to someone
  worried about a large content library.
- Mentions the RFCA archives for community standing only. It is a static 2013-era archive
  and must not be offered as a design reference.
- Quotes the prev/next example by name. Most credible line available.
- Links the preview and asks the two questions that matter: A or B, and whether Articles
  and Tips should merge.

## Explicitly NOT doing before they commit

- Keystatic setup. It is the right CMS, but it is post-commitment work and volunteers
  cannot use it until there is a repo they own.
- Image optimisation across all 474 entries.
- Membership forms, events, contact forms.
- DNS cutover or a full redirect implementation (build the map, do not deploy it).
- Video transcription. Validate that separately, once, on one real club video.
- Homepage, Links, Images, Membership, Contacts pages.

## After they commit

Keystatic on Keystatic Cloud free tier (volunteers sign in without GitHub accounts), full
content polish, images, remaining page types, redirect deployment, DNS cutover, then the
transcription pipeline as a separate priced piece.

## Why a separate repo

Keystatic turns every volunteer edit into a git commit. Club committee members must not be
committing into a repo that holds `financials/ledger.json`, `decisions/decision-log.md`,
`state/questions-for-benedict.md` and the paused Walkthrough prospect briefs. It is also
cleaner if STFC ever wants the repo handed over, and Cloudflare Pages wants its own root.

This planning document stays in dale because it is a business record. The site code does
not.

## Risks

| Risk | Mitigation |
|---|---|
| They say no after 2-3 Dale sessions of work | Everything built becomes a reusable template for the next club or nursery site. The retainer play was always "a few small sites", so the second one is much cheaper. |
| SEO loss on the 134 `-2` URLs | Build the 301 map in Phase 1, ship it at cutover. Never change a URL without a redirect. |
| Design-by-committee | Two directions only, and ask for a pick rather than feedback. |
| Copyright on reprinted articles (Texas A&M, California Rare Fruit Growers) | Migrate only what they already publish. Do not add, do not widen distribution. Their content, their existing decision. |
| Crawl misses metadata a WP export would have | There is almost none to miss: no dates, authors or tags exist. Ask for the export only once they commit, as a nice-to-have for images. |
| Generated tags are wrong | Committed as reviewable data files, not computed at build time. Fixing one is a one-line edit. |

## Effort estimate

Roughly 2-3 Dale sessions to a live preview URL. Benedict's cost: reviewing the preview
and sending one email. Out-of-pocket: $0, apart from cents of model usage for tagging.
