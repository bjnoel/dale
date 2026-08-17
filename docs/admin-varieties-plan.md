# /admin/varieties: oversight of the catalogue, and a place to approve things

Asked for 2026-08-17: "I want to be able to edit/approve mappings and have better oversight
of WHAT all my variety pages are."

Both are possible. They are different enough that they should not be the same screen.

---

## 1. What the page is today

`admin_view.render_varieties_html` renders four blocks: the index size, two alarms
(denied-but-watched, watched-slugs-with-no-page), the contents of `variety_overrides.json`,
and the sibling review queue.

Two things limit it.

**It cannot see the ledger.** `load_variety_curation` reads exactly two files: the canonical
title index and the override file. Everything the page knows is derived from slug strings.
Since 2026-08-17 there is a much richer source sitting next to it,
`/opt/dale/data/page-ledger/variety.json`, holding per-page history: first seen, days live,
days in stock, nights absent, last known nurseries and prices, state, and the reason for
every state change. Nothing reads it.

**The review queue has no memory.** It lists every slug that is a prefix of a longer slug:
319 groups, 493 suggested alias lines, regenerated identically every night. There is no way
to record "I looked at this pair and they are different plants", so the queue cannot be
worked down. It is the same disease the page builders had before the ledger, and it has the
same cure. A queue that never shrinks is a queue nobody opens.

Read-only was a deliberate choice, and the stated reason was "no write endpoint has to sit
behind Cloudflare Access". Worth being precise about that now, because it is the thing this
plan changes: `verify_cf_access` is not edge trust. It pulls Cloudflare's JWKS, verifies the
RS256 signature, checks audience and issuer, and fails closed on any missing config, missing
token, or error. A direct-to-origin request without a valid token gets a 403. The read-only
posture was a convenience, not a security boundary, and writes can be added without weakening
anything, provided section 5 is honoured.

---

## 2. What the data can already answer

Measured against the live ledger and index on 2026-08-17, so these are queue sizes, not
estimates.

| | |
|---|---|
| Variety pages, all `live` | 2,570 |
| Species with at least one page | 112 (Mango 182, Apple 161, Plum 126) |
| Species with exactly one variety | 16 |
| Pages backed by a single product at a single nursery | **1,512 (59%)** |
| Pages never once seen in stock | **685** |
| Pages absent tonight (would tombstone in 2 nights) | 0 |
| Slugs still carrying listing noise (`-potted`, `-pome`, `-tm`, `-dwf`) | **92** |
| Sibling groups / suggested alias lines | 319 / 493 |
| ...of those lines, noise-only / spelling variant / real judgement | 48 / 1 / 445 |
| Dead URLs recovered by task R1, awaiting approval | **126 renames, 68 retired** |

Two of those are findings in their own right. **59% of the catalogue is one nursery selling
one product**, which is worth knowing before deciding what the site is for. And **685 pages
have never had a buyable product**, which is a different problem from being out of stock
today.

---

## 3. Shape: two pages, not one

### `/admin/varieties`: what the catalogue *is*

Answers "what are my variety pages" and nothing else. No decisions on it.

```
Varieties                                    2,570 live · 126 redirect · 0 tombstone

┌ Attention ─────────────────────────────────────────────────────────────────┐
│  0    absent tonight        685  never in stock     92  noisy slugs        │
│  1,512 single-product       16   one-variety species                       │
└────────────────────────────────────────────────────────────────────────────┘

Search  [ hass________________ ]                         Species ▾   State ▾

Species                 Varieties  In stock  Single-product  Never stocked
Mango                        182        61              98             41
Apple                        161        84              77             30
Plum                         126        52              81             36
...                                                                  (112)
```

Clicking a species expands its varieties in place:

```
Avocado (34)
  slug                        state     nurseries  in stock  first seen   watch
  avocado-hass                live              6       yes  2026-03-05      2
  avocado-hass-type-a         redirect →  avocado-hass         2026-08-17    ·
  avocado-shepard             live              3       yes  2026-03-05      ·
  avocado-wurtz-a             redirect →  avocado-wurtz        2026-08-17    ·
```

The state column is the point. It is the first surface anywhere that shows a redirect and a
tombstone as first-class things rather than as absences.

**Size.** The ledger is 3.1MB and `/variety/index.html` is already 1.4MB, so the full table
must not be inlined. Same trick the main site uses after the PageSpeed work: a compact
`varieties.json` (slug, species, state, counts, flags, roughly 250KB) fetched once, filtered
client-side. Species rows render server-side so the page is useful before any JS runs.

### `/admin/varieties/review`: what needs a person

Everything that is a decision, in one place, ordered by how much thought it takes.

```
Review                                     126 pending · 493 candidates · 2 alarms

┌ Alarms ─────────────────────────────────────────────────────────────────────┐
│  Nothing denied-but-watched.  0 watched slugs with no page.                 │
└─────────────────────────────────────────────────────────────────────────────┘

Recovered URLs (126)                                   [ Approve all clean ]
  Dead since 2026-08-17, verified against the 2,717 pages scraper.log recorded.

  ☑  avocado-hass-type-a          →  avocado-hass          3 products   0 watching
  ☑  olive-bambalina-pbr          →  olive-bambalina       2 products   0 watching
  ☑  apple-pink-lady-pome-fruit   →  apple-pink-lady-pome  1 product    0 watching
                                        ⚠ target slug is itself noisy
  ...                                                    [ Approve ] [ Reject ]

Retired, no successor (68)                             [ Tombstone all ] [ Leave 404 ]
  kiwifruit-male, kiwifruit-female, lemon-thornless, olive-tree, macadamia-nut ...
  These were never cultivars. A redirect would be a lie; the choice is tombstone or 404.

Sibling candidates (493, obvious ones first)
  ▸ Listing noise only (48)          almond-all-in-one-potted → almond-all-in-one
  ▸ Spelling variants (1)            almond-...-papershell → almond-...-paper-shell
  ▸ Needs judgement (445)            apple-anna-trixzie-miniature vs apple-anna
```

**Tiering helps less than it looks like it should.** Measured: only 48 of the 493 differ from
their base purely by tokens the parser already strips elsewhere, and exactly one pair is a
spelling variant. 445 need someone who knows the plants. Sorting them is still worth doing,
because 49 quick wins is 49, but it is not the answer.

The answer is that **most of those 445 are probably correct**. `abiu-e4-pointed` really may
be a different fruit from `abiu-e4`, and the right action is "these are distinct", recorded
once and never asked again. A queue of 445 judgements that shrinks every time it is opened is
a backlog. The same 445 regenerating nightly is a wall. Persisted dismissals are the change
that matters here; tiering is a convenience on top of it.

---

## 3a. Editing what already exists

Asked for 2026-08-17: "can I edit the slug/redirects that already exist if they're wrong?"

Yes for redirects. Not for live slugs, and the reason matters.

**A redirect is data and is editable.** `redirect_to` is a field in the ledger, nothing derives
from it, and `resolve_redirects` already follows chains and is cycle-safe and depth-capped. So
retargeting `a -> b` to `a -> c` is a one-field write that the next build renders. Same for
converting between states:

| Now | Can become | How |
|---|---|---|
| `redirect` | a different target | write `redirect_to` |
| `redirect` | `tombstone` | write `state`, drop `redirect_to` |
| `tombstone` | `redirect` (a successor turned up) | write both |
| `retired` | `tombstone` or `redirect` | write both |
| `live` | **nothing** | see below |

**A live slug cannot be renamed from a browser, and should not be.** The slug is not stored
anywhere to edit: `canonical_cultivar` computes it from the nursery's product title on every
run, so a hand-edit would be recomputed away the same night. `apple-pink-lady-pome` is wrong
because the parser produced it, and the fix is an alias in `variety_overrides.json`, which is
the git-tracked configuration path in section 5.

The good part is what happens next, automatically. Alias it and its products start appearing
under the target tonight. Two nights later the exit guard releases the old slug, `rename_target`
sees a single successor carrying its products, and `decide_night` turns it into a redirect
without anyone asking. **Fixing a bad slug produces its own redirect**, which is the behaviour
the whole lifecycle change existed to get.

So the UI has two verbs that look similar and are not: *retarget this redirect* (instant,
operational, reversible) and *this live slug is wrong* (queues an alias, lands in git, takes two
nights, changes parsing everywhere). Section 6's "blast radius" rule applies: they must not look
alike.

One thing had to change in the code for this to work. A stub only ever displays two titles, so
seeding a redirect never needed the species. A tombstone does: without it there is no breadcrumb
and no sibling offer. Since a reviewer converting a redirect to a tombstone is exactly what this
section enables, and the pre-merge parser is the only other place that species could be
recovered from, `species` and `variety` are now carried through the proposal onto the entry.

## 4. Decisions have to stick

The single change that makes the review page worth opening twice.

New server-owned file, `/opt/dale/data/variety-decisions.json`:

```json
{
  "siblings": {
    "avocado-hass|avocado-hass-lamb": {
      "decision": "distinct", "by": "b@bjnoel.com", "at": "2026-08-17T04:11:00Z"
    }
  },
  "redirects": {
    "avocado-hass-type-a": {"decision": "approve", "target": "avocado-hass", "by": "...", "at": "..."}
  },
  "curation_pending": [
    {"kind": "alias", "from": "almond-all-in-one-potted", "to": "almond-all-in-one", "by": "...", "at": "..."}
  ]
}
```

A pair marked `distinct` never appears in the queue again unless one of its slugs changes.
That is the whole difference between a queue and a wall.

---

## 5. Two kinds of decision, two destinations

This is the part that needs deciding before any code is written, because getting it wrong
means a write that a deploy silently reverts.

**Redirect approvals are operational state.** Which dead URL points where affects no parsing
and no other surface. It belongs in `/opt/dale/data`, the server owns it, and
`build_variety_pages.py --seed-redirects` already consumes exactly that shape. The UI can own
this end to end today.

**Deny and alias are configuration.** `variety_overrides.json` is applied inside
`canonical_cultivar`, so every consumer inherits it: the builders, the alert gate, the alert
sender. It is git-tracked and `deploy.sh` rsyncs it, which means a browser writing it on the
server gets clobbered on the next deploy. Three options:

1. **Queue and promote** (recommended). The UI appends to `curation_pending`. A small
   `promote_curation.py` turns the queue into an edit to `variety_overrides.json`, runs the
   suite, commits and pushes. Benedict decides in the browser; Dale does the mechanical part.
   Git stays the single source of truth and the decision is reviewable in a diff.
2. **Layer a server file over the git one.** Fastest, and creates a second place curation
   lives. This codebase has consistently refused that trade.
3. **Copy-pasteable JSON**, as today. Honest, and demonstrably never gets done.

Option 1 also gives the audit trail for free: the commit message names who approved what.

---

## 6. What writes actually require

Authentication is already correct and is not the risk. The risks are these, and each needs
verifying rather than assuming:

- **CSRF.** `_extract_cf_token` falls back to the `CF_Authorization` cookie, so a POST
  authenticated by cookie alone is forgeable from another origin. Fix: on POST, require the
  `Origin` header to equal `https://treestock.com.au` and reject anything else, plus a
  per-render token bound to the JWT subject. **Check how Cloudflare sets `SameSite` on
  `CF_Authorization` before relying on any part of this**. Do not take the mitigation on
  trust, including this description of it.
- **Stale writes.** Two tabs, or a proposal file regenerated between render and submit. Every
  form carries the generation stamp it was rendered from; a POST whose stamp does not match
  is refused with a re-read, not merged.
- **Blast radius.** Approving a redirect touches one URL. Approving an alias changes parsing
  for every surface. They should not look alike: the alias action gets a confirm step naming
  the watch count and the pages affected.
- **Nothing irreversible from a browser.** No deletes, ever. Approving produces a ledger
  entry or a queued config change, both of which a later night can undo. `--allow-delete`
  stays where it is, on the nightly, off the web.

### Bulk actions have to be hard to do by accident

Asked for 2026-08-17: a loud warning on any approve-all or reject-all.

Three layers, because a modal on its own is something people learn to click through.

1. **Friction scaled to the count.** Ten rows or fewer gets an ordinary confirm. More than ten
   requires typing the number into the dialog, so the hand cannot finish the action without the
   eye reading the count. Same principle as ordering the night's guards by blast radius: the
   cost of a gesture should track what the gesture can break.
2. **The dialog says what changes, not "are you sure".** Name the count, the action, and the
   rows that are least safe, which the tool already flags: 4 of the current 126 point at a
   target whose own slug still carries listing noise. The confirm button restates the action
   (`Approve 126 redirects`), never `OK`. Rejecting is also a decision and it also persists, so
   it gets the same dialog rather than being treated as the harmless direction.
3. **Say when it becomes real, because it is not immediate.** An approval writes to a file the
   nightly reads. Nothing on the site changes until the 00:00 UTC build, and that window is the
   strongest safety property available here. It belongs in the confirmation text rather than
   buried: *"126 approved. Nothing changes on the site until tonight's build. You can still
   change your mind."*

**Wiring still needed.** `run-all-scrapers.sh` line 242 does not pass `--seed-redirects`, so an
approval currently reaches nothing. Adding that flag to the nightly is what makes any of this
true, and it should land in the same phase as the approve button rather than before it.

---

## 7. Phases

**Phase 1: read the ledger (no writes).** Rebuild `/admin/varieties` as the inventory:
state counts, species drill-down, the six attention queues, client-side search. This is most
of the value Benedict asked for and carries no new risk at all. Move the existing curation
and alarm blocks to `/admin/varieties/review` unchanged.

**Phase 2: approve redirects.** The narrowest, best-understood write: a POST that flips
`approved` on rows of the proposal file, plus the CSRF and staleness work from section 6, the
bulk-action confirmation, and `--seed-redirects` wired into the nightly. 126 real rows are
already waiting, so it ships with its own test case.

**Phase 2a: retarget existing entries.** Editing a redirect that turned out wrong, and
converting between redirect and tombstone. Same write plumbing as phase 2 and the same file
format, over the ledger instead of the proposal file, so it is small once phase 2 exists.

**Phase 3: sibling decisions.** Persisted `distinct` dismissals first, then tiering, then
`curation_pending` with `promote_curation.py`. That order is deliberate: dismissals are what
turn 493 into a backlog that drains, and the tiering only clears 49 of them. Depends on phase
2's write plumbing being proven.

Phase 1 is worth doing whether or not 2 and 3 ever happen.

---

## 8. Deliberately not doing

- **No auto-folding by prefix.** `avocado-hass-lamb` is Lamb Hass. The tiering in section 3
  sorts candidates; it never applies them.
- **No editing product data.** This is oversight of pages, not a catalogue editor. The
  nurseries own their titles.
- **No general CMS.** Four verbs: approve a redirect, reject a redirect, mark a pair
  distinct, queue an alias or deny. If a fifth is wanted, it needs its own argument.
- **No `noindex` anywhere** (DEC-266).
