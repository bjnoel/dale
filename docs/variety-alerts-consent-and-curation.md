# treestock variety alerts: consent, abuse protection, icons, manage page, variety curation

## Context

DEC-294 (2026-08-15) made per-variety alerts the product: the digest signup is hidden
site-wide, every result row naming a cultivar carries an inline alert control, and watched
varieties fire on price drops as well as restocks. It works, 103 watches across 90 people,
but it was built for conversion and never for consent, abuse, or honesty about what a
watch does.

Benedict raised seven things. Verified against the code and the live data, they resolve to
eight defects (the last found while mapping the surfaces), two of which are more serious
than they look from the outside:

1. **Anyone can subscribe anyone.** `POST /api/watch-variety` (`subscribe_server.py:569`)
   takes a valid-looking email and inserts a live watch. No token, no confirmation, no rate
   limit, no captcha, no cap, no body-size limit, `Access-Control-Allow-Origin: *`. Nothing
   sits between a script and 90 real inboxes.
2. **The client-supplied variety title is echoed to every watcher.** `send_variety_alerts.py:517`
   takes `watchers[slug][0]["variety_title"]` and interpolates it unescaped into the subject
   and HTML sent to everyone watching that slug. With (1), a third party controls copy in
   mail we send. The same value reaches an `onclick` attribute at `subscribe_server.py:1073`
   escaped for only `"` and `<`.
3. **The site's "Manage email alerts" link is a dead end for most recipients.**
   `/manage.html` posts to `/api/request-manage-link`, which only looks in `subscribers.json`
   (`subscribe_server.py:534`). The ~83 watch-only people are told "a link is on its way" and
   get nothing. The in-email footer link works; the site link does not.
4. **Nobody is told they subscribed.** No email at the moment a watch is created, so first
   contact can be weeks later.
5. **The manage page leads with the wrong thing.** Digest settings render first and "Variety
   alerts" is last (`subscribe_server.py:1230-1272`), on the page reached from the alert that
   is now the product.
6. **The two triggers are indistinguishable.** No icons anywhere in the alert email; restock
   and price drop differ by wording only.
7. **Variety identity is broken in both directions.** Junk gets buttons and real cultivars do
   not, and worse, one cultivar fragments across several slugs.
8. **A dead bell on every species page** (found while mapping the surfaces, not reported).
   `build_species_pages.py:512` emits `🔔 Alerts` linking to `#subscribeBox` for out-of-stock
   rows it cannot parse into a cultivar, but that anchor only renders when
   `DIGEST_SIGNUP_ENABLED` is true (`:561`), and DEC-294 set it to false. The link goes
   nowhere.

The two findings worth stating as numbers, because they change the priority:

- **Fragmentation is silently breaking alerts today.** 241 base slugs have 343 longer
  siblings that are the same cultivar. **13 of the 84 watched slugs are affected right now.**
  Someone watching `avocado-shepard` gets nothing when `avocado-shepard-type-b`,
  `avocado-shepard-b`, `avocado-shepard-b-type` or
  `avocado-shepard-persea-americana-type-b-fruit-tree` restocks. Same for
  `persimmon-hachiya` vs `persimmon-hachiya-astringent`, `avocado-wurtz` vs `avocado-wurtz-a`.
  DEC-294's central promise is that a watch means "buyable somewhere"; fragmentation
  quietly breaks that for 15% of subscribers.
- **The existing `skipped` lists cannot be used as a deny list.** `variety_descriptions/*.json`
  carry 1,324 skipped slugs, which looks like ready-made curation, but 24 of the 84 watched
  slugs sit on one, including `blueberry-ob1` (4 watchers), `fig-pingo-de-mel`,
  `pomegranate-parafanka`, `white-sapote-vista`. `skipped` means "no blurb written", not
  "not a real variety". Using it directly would silently kill 24 live watches.

Intended outcome: an alert you can trust. Consent recorded and acknowledged when given, an
abuse ceiling that makes list-bombing pointless, every email saying at a glance which of the
two things happened, a manage page that leads with the alerts, and one cultivar meaning one
alert.

## Decisions taken

| Question | Decision |
|---|---|
| Consent | **Single opt-in plus an immediate notice email.** Watch goes live at once; a "You're now watching X" email lands with a one-click stop and a link to all their alerts. Throttled so it cannot become a flood. Preserves the one-tap second watch DEC-294 built for. |
| Icons | **Email and site pills both**, watch stays untyped (no alert-type schema change). Bell for back in stock, falling chart for price drop, subject line included. Copy becomes honest that one watch covers both triggers. |
| Curation | **Parser fixes plus a curated override file** (deny + alias), surfaced in /admin. |
| Sequencing | **One change, one deploy.** |

## Baseline

`.venv/bin/python -m unittest discover tests/` is green: 2,488 tests, 1 skipped. Any red
after this work is ours.

---

## 1. Consent: the notice email

New sender `tools/scrapers/send_watch_notice_email.py`, modelled on the existing
`send_manage_link_email.py` / `send_confirmation_email.py` pattern (both are launched
`subprocess.Popen` from the server so the HTTP response returns immediately).

Content: what they are now watching, an explicit statement that one alert covers **both**
triggers, a one-click "stop watching this" and a "see all my alerts" link. Reuse the token
and URL shapes already proven in `send_variety_alerts.inject_unsubscribe()` (`:417`):
`/stop-watching.html?email=&token=&variety=&title=` and `/api/preferences?email=&token=`.
Both are already Caddy-routed, so **no new Caddy entry is needed** (the live Caddyfile has
drifted from the tracked one, so avoiding new routes is deliberate).

**Throttling is the anti-abuse mechanism, not a nicety.** At most one notice email per
address per hour; watches added inside that window are batched into the next one. Reuse the
exact shape of `MANAGE_LINK_RATE_LIMIT_SECONDS` + `manage_link_sends.json`
(`subscribe_server.py:53`, `:520-532`) with a sibling log so the two cannot interfere. This
caps a victim at 24 emails/day even under sustained attack, versus unbounded today.

## 2. Abuse protection on `/api/watch-variety`

The server is single-threaded stdlib `HTTPServer`, so every control must be cheap.

- **Body-size cap** before `json.loads`, mirroring `subscribe_server.py:440`.
- **Per-address watch cap** (suggest 50). Not spoofable, and it bounds the blast radius of
  a single forged address.
- **Per-IP rate limit** on watch creation. Caddy passes headers through unmodified, and
  treestock.com.au is orange-clouded (verified: `cf-ray` present), so `CF-Connecting-IP` is
  available; fall back to `X-Forwarded-For` then the peer address. **State this honestly in
  the code: the origin is reachable directly, so this header is spoofable.** It raises the
  cost of casual abuse; the per-address cap and the notice-email throttle are the controls
  that actually hold.
- **Honeypot field** in the inline form, rejected server-side. Free, catches naive bots.
- **Tighten CORS** on state-changing routes (`subscribe_server.py:1386`, `:896`), but do not
  count it as abuse protection: CORS is enforced by browsers and ignored entirely by a
  script, and these endpoints carry no cookie auth for a malicious site to ride. It is
  hygiene, not a control.
- **Cloudflare Turnstile: build the hook, leave it off.** There is no Turnstile secret in
  `/opt/dale/secrets/` (verified), and creating the keys is Benedict's job. Implement
  verification behind a config flag that is a no-op until `TURNSTILE_SECRET` appears in
  `app.env`, so enabling it later is a secret plus a flag, not a code change.

Rate-limit state goes in a new table in the existing `variety_watches.db` rather than a new
JSON file: it is already open on this path, it gives cheap pruning with a `DELETE WHERE
ts < ?`, and it avoids a second file to keep consistent.

**Also close the wishlist back door.** `/api/wishlist` (`subscribe_server.py:637-657`)
silently writes voters into `subscribers.json` with no double opt-in and fires a welcome
email, which both bypasses the digest's own consent flow and contradicts DEC-294. The table
has 0 rows, so removing the auto-subscribe is a no-risk one-liner.

## 3. Killing the injection: server-owned variety titles

Stop trusting the client's `variety_title` entirely.

- `build_variety_pages.py` already computes canonical titles into `index_entries`
  (`:348-357`). Emit a `variety-index.json` of `{slug: title}` from the same loop. It takes
  `<data_dir> <output_dir>` (`:300-306`), so write it to the **data dir**
  (`/opt/dale/data/variety-index.json`) next to the other server-read state, not the web
  root. Include grandfathered slugs, which are excluded from the browsable index at `:345`
  but must still resolve for their existing watchers.
- `subscribe_server.py` reads it (lazily, with an mtime cache) to **reject unknown slugs**
  at `/api/watch-variety` and to store the canonical title, ignoring whatever the client
  sent. Do **not** import `cultivar_parsing` into the server: it is heavy and would add a
  module to the `server_modules_sum()` restart list in `tools/deploy.sh`. A JSON index keeps
  the server dumb. Note the JSON file itself will not trigger the restart checksum, hence
  the mtime cache.
- `send_variety_alerts.py` reads the same index for the display title instead of
  `watchers[slug][0]["variety_title"]` (`:517`, `:536`), and HTML-escapes it regardless.
- Fix the `onclick` at `subscribe_server.py:1073` to use a data attribute and a delegated
  listener rather than string interpolation, and escape titles properly.
- **Existing 103 rows**: backfill `variety_title` from the index where the slug is known;
  leave the row (but escape on render) where it is not, so nobody's watch is dropped.

This also fixes a cosmetic bug worth having: `dashboard.js:398` sends the **raw nursery
title**, so a homepage watch stores things like `Advanced Lemon 'Eureka Seedless'
400mm/45Ltr Pot (PICK UP ONLY)`, which would become the email's subject line.

## 4. Manage: make the site link work, and lead with alerts

- **`/api/request-manage-link`** (`subscribe_server.py:502-566`): after the `subscribers.json`
  lookup fails, check `_get_variety_watches(email)` and send the manage link to watch-only
  addresses too. Keep the uniform-200 enumeration safety and the 1/hour limit exactly as they
  are.
- **`send_preferences_page()`** (`:1145-1357`): move the "Variety alerts" block (`:1265-1272`)
  above the digest form, and suppress the digest block when the address is not a digest
  subscriber (already true via `send_watch_only_page`) **and** when its `frequency` is `off`.
  The 12 real digest subscribers must still be able to reach their settings, so suppression
  is a collapsed section, not a deletion.
- Reword `manage.html` away from "the email you used to subscribe" (it now serves watchers
  too), and fix its em dash at line 53.

## 5. Icons

- **Email**: emoji in the subject line and beside the heading, because inline SVG is
  unreliable across mail clients and there is no plain-text part to fall back to.
  **🔔 for back in stock, 📉 for price drop**, exactly as Benedict described them. 📉 is
  already the site's price-drop glyph (`daily_digest.py:426-428`), so half of this is
  existing vocabulary. The digest uses ✅ rather than 🔔 for back-in-stock, but that is a
  category pill in a different context; use the bell here as asked. Keep the ` -- `
  separator in subjects, pinned by `tests/test_variety_alerts.py:283`.
- **Site pills**: inline SVG in `dashboard.js:393-414` with CSS in `build-dashboard.py:760-772`,
  so they inherit the pill colour and stay crisp. Same two glyphs.
- **Copy honesty**: the success message becomes "Alert set. We'll email you when it's back in
  stock or drops in price." Apply the same to `variety_page.html.j2:162-164` and the
  `build_variety_pages.py:218-222` headings.
- **Fix the dead bell** at `build_species_pages.py:512`: the `#subscribeBox` fallback for
  unparseable out-of-stock rows points at an element DEC-294 stopped rendering. Species pages
  do not load `dashboard.js`, so there is no inline control to redirect it to and no
  per-variety target exists for those rows by definition. **Drop the link on that branch**
  rather than invent a destination. The bell glyph here is already `&#128276;`, so species
  pages are the one surface already using the icon Benedict asked for.
- Fix the em dashes at `variety_page.html.j2:139` and `:170` while in there (repo rule 4).

## 6. Parser fixes (`tools/scrapers/cultivar_parsing.py`)

All three land in functions both parser paths already funnel through, so the relaxed-only
deny lists stop being the only line of defence.

- **(a) Bidirectional dash.** `_strict_parse:565` splits `A - B` and assigns left=species
  unconditionally, so `Tropical - Sapodilla` becomes species "Tropical" and the taxonomy gate
  drops it. Try the reverse orientation when the left side fails `canonicalize_species` and
  the right side succeeds. `Sapodilla Grafted - Krasuey` is unaffected because its left side
  resolves.
- **(b) Comma is a separator.** `_variety_ok:223` rejects on `[-–—/|:;]` but not `,`, which is
  why `Sapodilla, Chiko, Chikoo, Chico, Naseberry, Nispero` becomes a cultivar. Adding the
  comma also fixes `avocado-hass-persea-americana-type-a-fruit-tree` and
  `mango-kensington-pride-mangifera-indica-bowen-mango-fruit-tree`.
- **(c) A never-a-cultivar vocabulary in `_clean_cultivar_parts:503`**, which is the one
  function both paths reach and which already does reject-if-nothing-real at `:511-515`.
  Strip trailing `a` / `b` / `type a` / `a type` / `pbr` / `tm` and words like `plant`,
  `tree`, `cultivar`, `male`, `female`, `rootstock`, `pollinating`, `pair`, `thornless`.
  This clears 34 pure-noise slugs (`almond-pair`, `coffee-plant`, `kiwifruit-male`,
  `soursop-tree`, `bunya-nut-tree`) and folds **57 of the 343 fragmenting siblings**
  automatically.

Risk: `tests/test_parsing.py` pins ~50 parse cases and `tests/test_golden.py` pins builder
HTML. Every change here moves slugs.

## 7. The override file

`tools/scrapers/variety_overrides.json`, alongside `fruit_species.json` and
`nursery_categories.json` so it rsyncs to the server for free with no `deploy.sh` change.

```json
{
  "deny":  ["almond-pair", "strawberry-melba-pbr-mega-tube"],
  "alias": {"avocado-shepard-type-b": "avocado-shepard",
            "persimmon-hachiya-astringent": "persimmon-hachiya"}
}
```

- Applied in `canonical_cultivar` (`:829`), so every consumer inherits it: the builders, the
  dashboard gate, and `send_variety_alerts`. `alias` resolves before `deny` is checked.
- Interaction with `GRANDFATHERED_VARIETY_SLUGS` (`:654`): grandfathering wins over `deny`,
  because that set exists precisely to keep existing watchers' alerts alive.
- **Denying a slug someone watches must not silently drop them.** Before any slug leaves the
  dataset, migrate affected watches with `migrate_variety_watch_slugs.py` (alias case) or
  leave the watch and the page in place and only remove the *button* (deny case). Note
  `build_variety_pages.py:362-367` deletes orphan pages, so a slug that stops being generated
  takes its page with it and would 404 a live watcher's alert link.
- **/admin**: a new `/admin/varieties` tab (`ADMIN_PAGES` at `admin_view.py:1014`; `/admin/*`
  is already Caddy-routed) listing unadjudicated slugs and the 286 sibling pairs that need
  human judgement, as copy-pasteable JSON. Deliberately read-only, matching the rest of
  /admin, so no write endpoint has to sit behind Cloudflare Access.

Do **not** auto-fold siblings by prefix. `avocado-hass-lamb` is Lamb Hass, a different
cultivar; `guava-thai-pink`, `orange-valencia-delta` and `finger-lime-green-sapphire` are all
real. 57 are mechanically safe; the other 286 are a review queue, not a script.

Explicitly out of scope: changing `slugify` (`:108`) so apostrophes elide
(`apple-bick-s-green` → `apple-bicks-green`). It would move a large number of slugs for
cosmetic gain.

## 8. Rollout, one deploy

Order matters because slugs move and the alert sender runs nightly at 22:00 UTC.

1. Land code + tests; `.venv/bin/python -m unittest discover tests/` green.
2. Regenerate goldens with `GOLDEN_UPDATE=1` and **review the diff** before accepting.
3. Commit, then `tools/deploy.sh`. Never scp.
4. Run the individual builders (`build_variety_pages.py` first, so `variety-index.json`
   exists before the server needs it). **Never `run-all-scrapers.sh`, it emails subscribers.**
5. `migrate_variety_watch_slugs.py` dry-run, review, then apply on the server. **Steps 4 and
   5 must be adjacent**: the build deletes orphan pages (`build_variety_pages.py:362-367`),
   so between them a watcher's alert link can 404.
6. **Assert every watched slug resolves.** `SELECT DISTINCT variety_slug FROM watches` must
   be a subset of the generated pages plus `GRANDFATHERED_VARIETY_SLUGS`. 12 watched slugs
   are already absent from live stock today, so establish that baseline before the change
   and require the number not to grow. This is the check that would catch a missed migration
   before a subscriber does.
7. Verify with `send_variety_alerts.py --dry-run`, then `--redirect-to b@bjnoel.com` for a
   real rendered email. `--redirect-to` deliberately does not record sends, so a later real
   run still fires.
8. Confirm no alert fired as a side effect: `sends` count should be unchanged (47 at the time
   of writing) until the next scheduled run.

Deploy while no autonomous session is running, or the hourly runner trips the breaker.

## 9. Tests

- `tests/test_parsing.py` — new cases for the dash reversal, the comma separator, and the
  never-a-cultivar tails. Update pinned cases the changes legitimately move.
- `tests/test_variety_alerts.py` — icons present per trigger, canonical title used instead of
  the watcher-supplied one, escaping of a hostile title, subject still uses ` -- ` and no em
  dashes.
- New `tests/test_watch_abuse.py` — body cap, per-address cap, per-IP limit, honeypot,
  unknown-slug rejection, notice-email throttle and batching.
- New `tests/test_variety_overrides.py` — deny/alias application, alias-before-deny,
  grandfathered slugs surviving a deny, malformed file failing loudly rather than silently
  disabling curation.
- `tests/test_golden.py` — regenerate; expect churn on species, variety, dashboard and
  compare pages.
- `tests/test_deploy_restart_list.py` — must stay green; it will fail if the server gains a
  new local module import, which is a reason to keep the JSON-index approach.
- `tests/test_no_forking.py` — must stay green; put anything shared in `stocklib`.

## Risks

- **Slug movement is the big one.** Parser fixes plus aliases move slugs, and watches, pages,
  sitemap entries and SEO URLs all key off them. The migration script exists and must run;
  the orphan-deletion step at `build_variety_pages.py:362` is what turns a missed migration
  into a 404 for a real subscriber.
- **One deploy means one large diff** across the parser, the server, the sender, the builders
  and the front end. That was Benedict's call; the mitigations are the golden diff review at
  step 2, the watched-slug assertion at step 6, and the dry-run at step 7. If the golden diff
  at step 2 looks larger than expected, that is the moment to split the parser work out, not
  after deploying.
- **The IP rate limit is spoofable** while the origin is directly reachable. Do not let it
  create false confidence; the per-address cap and email throttle are the real ceiling.
