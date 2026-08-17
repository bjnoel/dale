"""
Page lifecycle ledger: the memory the nightly builders never had.

Both page families decide whether a page exists from what is in stock tonight,
and they fail in opposite directions. `build_variety_pages.py` unlinks any slug
it did not generate, so a nursery delisting a product deletes a URL that Google
ranks (1,546 delete/recreate events in 165 days, 1,312 of them a page gone for
exactly one night). `build_species_state_pages.py` never deletes, so a combo
page that falls under its threshold serves a stale in-stock table forever.

One root cause: the builders cannot tell a delisting from a rename from a page
that should still exist but is empty today, because they have no record of what
they built last night. This module is that record, plus the state machine that
reads it. See docs/page-lifecycle-plan.md for the measurements and the rejected
alternatives (chiefly: deriving all this from availability.json, which is keyed
url|sku, carries no slug, and re-derives identity nightly under the current
parser, which is the bug class being fixed).

Four states. A page is born `live` and can only reach the others from there:

    live       generated tonight, renders normally
    tombstone  no longer generated, URL kept alive with last-known rows
    redirect   its products moved to another slug, serves a redirect stub
    retired    left the taxonomy; the only state where a URL is allowed to die

Two properties do most of the safety work:

- **Opt-in by flag.** A builder with no `--ledger` never constructs one, so it
  stays stateless and every golden case is byte-identical. That is what makes
  "this change is inert without the flag" checkable rather than asserted.
- **Tombstoning is reversible.** observe() resurrects any state the moment the
  slug is generated again, so a bad night self-heals. Only `retired` and the
  below-entry-guard delete remove a file, and both sit behind `allow_delete`.

Usage from a builder, once per night:

    ledger = PageLedger.load(path, family=FAMILY_VARIETY)
    for slug, data in tonight:
        ledger.observe(slug, today=today, rows=rows, title=...)
    plan = decide_night(ledger, tonight_slugs, today=today,
                        untrusted=untrusted_nurseries(today))
    # render plan.tombstoned / plan.redirected, unlink plan.removals
    ledger.save(path)
"""
from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Iterable, Sequence

SCHEMA = 1

LIVE = "live"
TOMBSTONE = "tombstone"
REDIRECT = "redirect"
RETIRED = "retired"
STATES = (LIVE, TOMBSTONE, REDIRECT, RETIRED)

FAMILY_VARIETY = "variety"
FAMILY_SPECIES_STATE = "species-state"

# Last-known rows kept per page, for the tombstone table. A variety page lists
# one cultivar at a handful of nurseries; a combo page lists up to 60 products
# spanning many cultivars, matching that page's own render cap.
ROW_CAP = {FAMILY_VARIETY: 12, FAMILY_SPECIES_STATE: 60}
DEFAULT_ROW_CAP = 12

# Fields a row may carry. Anything else the builder holds is not the ledger's
# business, and pinning the set stops a passing-through builder from growing the
# file without noticing.
ROW_KEYS = frozenset({
    "nursery_key", "nursery_name", "title", "price", "available",
    "url", "states", "type_label",
})

# Lifecycle fields observe() owns. A builder passing one of these as metadata is
# a bug (it would hand-edit the state machine), so say so loudly.
RESERVED_FIELDS = frozenset({
    "state", "first_seen", "last_seen", "live_days", "in_stock_days",
    "last_in_stock", "since", "rows", "rows_as_of", "redirect_to",
    "retired_reason", "absent_nights", "see_also",
})

# Nights a page must be absent before anything happens to it. Measured: N=2
# suppresses 1,312 of 1,546 variety events (85%) and 45% of combo ones, for one
# day of latency. Both families landed on the same knee independently.
EXIT_GUARD_NIGHTS = 2

# A page must have earned its URL before we keep it forever. Both conditions are
# required: a pure consecutive-nights rule breaks on the pipeline's own missed
# nights, of which there were two in the last month, and a pure span rule would
# keep a page seen twice a month apart.
ENTRY_GUARD_LIVE_DAYS = 7
ENTRY_GUARD_SPAN_DAYS = 7

# Global circuit breaker. Tonight's page count collapsing means the pipeline
# broke, not that the country sold out.
GLOBAL_FLOOR_RATIO = 0.85

# Bounds a bug in the three guards above to one constant. A normal night
# tombstones single digits; the worst measured night deleted 62 pages.
MAX_TOMBSTONES_PER_NIGHT = 150

# Share of a page's last-known product URLs that must reappear under one other
# slug before we call it a rename and assert a single successor.
RENAME_MAJORITY = 0.5

# A -> B -> C chains get re-resolved nightly. The cap is a backstop against a
# cycle the visited-set somehow misses; real chains are 1 or 2 deep.
REDIRECT_DEPTH_CAP = 8

LEDGER_DIRNAME = "page-ledger"

# Every generated page declares its own state in a meta tag, and the sitemap
# builder excludes by reading it. Rejected: having the sitemap read the ledger
# (it would couple that builder to a file it does not own, and break its
# hand-built test fixture) and a sidecar exclusion list (two sources of truth
# for one fact). Carrying the state as a *value* rather than a bare marker is
# also what makes the rollback lever "stop listing tombstones" a one-line
# change.
STATE_META_NAME = "treestock-page-state"

# The sitemap reads only the head of each file. render_head() appends
# extra_head last, just before </head>, and a real variety page's head measures
# 3,754 bytes (the Open Graph block, the Plausible snippet and the style block
# are most of it), so the 1KB this was first specified at would never have seen
# the tag. 8KB leaves room for the head to grow and still costs well under a
# second across every page on the site.
STATE_META_SCAN_BYTES = 8192

_STATE_META_RE = re.compile(
    rf'<meta\s+name="{STATE_META_NAME}"\s+content="([a-z-]+)"')


def page_state_meta(state: str) -> str:
    """The state declaration for a page's <head>.

    Emitted for live pages too, not just tombstones. A marker that appears only
    on the unusual pages tells you nothing about a page that lacks it: it could
    be live, or it could predate the change.
    """
    if state not in STATES:
        raise ValueError(f"unknown page state {state!r}")
    return f'<meta name="{STATE_META_NAME}" content="{state}">'


def read_page_state(path: Path | str, default: str = LIVE) -> str:
    """The state a generated page declares, read from its first bytes.

    Defaults to `live`, which is the honest reading of a page with no tag: every
    page on the site predates this change, and none of them are tombstones.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(STATE_META_SCAN_BYTES).decode("utf-8", "ignore")
    except OSError:
        return default
    match = _STATE_META_RE.search(head)
    return match.group(1) if match else default


def default_ledger_dir() -> Path:
    """`page-ledger` under DALE_DATA_DIR (or /opt/dale/data).

    The data dir, not the output dir: /opt/dale/dashboard is the web root and is
    globbed by the sitemap builder, so a ledger written there would be published
    and, worse, would look like a page.
    """
    return Path(os.environ.get("DALE_DATA_DIR", "/opt/dale/data")) / LEDGER_DIRNAME


def ledger_path(family: str, ledger_dir: Path | str | None = None) -> Path:
    """Conventional path for a family's ledger (`variety.json`)."""
    base = Path(ledger_dir) if ledger_dir else default_ledger_dir()
    return base / f"{family}.json"


def _trim_rows(rows: Iterable[dict], cap: int) -> list[dict]:
    """Keep the caller's order (in-stock first, cheapest first), capped, with
    only the known keys. Order is the caller's because the builder has already
    sorted for display and the tombstone renders these rows as they are."""
    trimmed = []
    for row in rows:
        trimmed.append({k: v for k, v in row.items() if k in ROW_KEYS})
        if len(trimmed) >= cap:
            break
    return trimmed


def _days_between(start: str | None, end: str | None) -> int:
    """Whole days from `start` to `end`, or 0 if either is missing/unparseable.

    Returning 0 on a bad date is deliberate: it fails the entry guard, and
    failing an entry guard means "not yet", never "delete it".
    """
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except (TypeError, ValueError):
        return 0


def new_entry(today: str) -> dict:
    """A page seen for the first time tonight.

    `last_seen` starts empty rather than at `today`: observe() counts a night
    by comparing against it, so pre-filling it would swallow the page's own
    first night and leave every page's `live_days` one short of the truth for
    the rest of its life. The entry guard reads that count.
    """
    return {
        "state": LIVE,
        "first_seen": today,
        "last_seen": None,
        "live_days": 0,
        "in_stock_days": 0,
        "last_in_stock": None,
        "since": today,
        "seeded": False,
        "title": "",
        "species": "",
        "species_slug": "",
        "variety": "",
        "rows": [],
        "rows_as_of": None,
        "redirect_to": None,
        "retired_reason": None,
        "see_also": [],
        "absent_nights": 0,
    }


class PageLedger:
    """One family's page states, loaded from and saved to a JSON file.

    Entries are plain dicts on purpose: the file *is* the schema, it gets read
    by hand during an incident, and a serialisation layer is one more place for
    the two to drift.
    """

    def __init__(self, family: str, pages: dict | None = None, *,
                 updated: str | None = None, skipped_nights: int = 0,
                 review: list | None = None, row_cap: int | None = None,
                 missing: bool = False, corrupt: bool = False):
        self.family = family
        self.pages: dict[str, dict] = pages if pages is not None else {}
        self.updated = updated
        self.skipped_nights = int(skipped_nights or 0)
        self.review: list[dict] = review if review is not None else []
        self.row_cap = row_cap or ROW_CAP.get(family, DEFAULT_ROW_CAP)
        self.missing = missing
        self.corrupt = corrupt
        # Slugs observe() brought back tonight. Not persisted: it is a report of
        # what happened during this run, and the states it describes are already
        # in `pages`.
        self.resurrected: list[str] = []

    # -- loading and saving ------------------------------------------------

    @classmethod
    def load(cls, path: Path | str, family: str, *, log=print) -> "PageLedger":
        """Read a ledger. A missing or unreadable file yields an empty one
        flagged `seeding`, never an exception: night one has no file, and a
        builder that dies because of that is a worse outcome than a builder that
        rebuilds its memory from tonight's output.
        """
        path = Path(path)
        if not path.exists():
            log(f"LEDGER MISSING at {path}, seeding from tonight's output")
            return cls(family, missing=True)
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict) or not isinstance(data.get("pages"), dict):
                raise ValueError("no pages object")
        except (OSError, ValueError) as e:
            # Loud, because the *silent* half of this is the dangerous half: a
            # corrupt ledger reseeds, and a reseeded ledger tombstones nothing
            # for a week. Better to know on the night it happens.
            log(f"ERROR: LEDGER CORRUPT at {path} ({e}), seeding from tonight's "
                f"output and leaving the .prev backup alone")
            return cls(family, corrupt=True)

        if data.get("schema") != SCHEMA:
            log(f"WARNING: ledger schema {data.get('schema')!r} != {SCHEMA} at {path}")
        pages = {
            slug: entry for slug, entry in data["pages"].items()
            if isinstance(entry, dict)
        }
        return cls(
            family,
            pages=pages,
            updated=data.get("updated"),
            skipped_nights=data.get("skipped_nights", 0),
            review=list(data.get("review") or []),
        )

    @property
    def seeding(self) -> bool:
        """True when there was no usable file to load, so tonight is a rebuild
        of the memory rather than a night we can reason about."""
        return self.missing or self.corrupt

    def to_dict(self, today: str | None = None) -> dict:
        return {
            "schema": SCHEMA,
            "family": self.family,
            "updated": today or self.updated,
            "skipped_nights": self.skipped_nights,
            # Newest 500 notes. This is a queue of things to look at, not an
            # audit log, and an uncapped one grows the file a builder rewrites
            # nightly without anyone ever reading the old end of it.
            "review": self.review[-500:],
            "pages": dict(sorted(self.pages.items())),
        }

    def save(self, path: Path | str, today: str | None = None) -> Path:
        """Write atomically, rotating the previous file to `<name>.prev` first.

        Not rotated when the load found the file corrupt: `.prev` is the copy an
        incident gets recovered from, and overwriting it with the corrupt one is
        how a recoverable night becomes an unrecoverable one.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not self.corrupt:
            try:
                _atomic_write(path.with_name(path.name + ".prev"), path.read_bytes())
            except OSError as e:
                print(f"WARNING: could not rotate ledger backup: {e}")
        payload = json.dumps(self.to_dict(today), indent=1, sort_keys=True)
        _atomic_write(path, payload.encode("utf-8"))
        return path

    # -- reading -----------------------------------------------------------

    def live_count(self) -> int:
        return sum(1 for e in self.pages.values() if e.get("state") == LIVE)

    def slugs_in_state(self, state: str) -> list[str]:
        return sorted(s for s, e in self.pages.items() if e.get("state") == state)

    def note(self, slug: str, reason: str, today: str | None = None, **extra) -> None:
        """Append to the review list. Every classification that was not obvious
        lands here, because the alternative is finding out from Search Console
        two months later."""
        entry = {"slug": slug, "reason": reason, "date": today}
        entry.update(extra)
        self.review.append(entry)

    # -- tonight's observations --------------------------------------------

    def observe(self, slug: str, *, today: str, rows: Sequence[dict] = (),
                in_stock: bool | None = None, **meta) -> dict:
        """Record that `slug` was generated tonight, and resurrect it if needed.

        Resurrection is the whole reason the delete path can be simple: a real
        page overwrites its own tombstone or stub at the same path, so a slug
        coming back needs no cleanup and cannot race. A generated slug always
        wins.

        Idempotent within a day. `rebuild_pages_email_safe.sh` re-runs builders
        on the same date, and a second run must not double-count the day toward
        the entry guard.
        """
        bad = RESERVED_FIELDS & set(meta)
        if bad:
            raise ValueError(
                f"observe() owns {sorted(bad)}; pass page metadata "
                f"(title, species, variety, ...), not lifecycle state")

        entry = self.pages.get(slug)
        if entry is None:
            entry = new_entry(today)
            self.pages[slug] = entry

        if in_stock is None:
            in_stock = any(r.get("available") for r in rows)

        if entry.get("state") != LIVE:
            # Back from the dead. first_seen is kept: it is the age of the page,
            # not of its current run, and the entry guard reads it.
            self.note(slug, f"resurrected from {entry.get('state')}", today,
                      was=entry.get("state"))
            self.resurrected.append(slug)
            entry["state"] = LIVE
            entry["since"] = today
            entry["redirect_to"] = None
            entry["retired_reason"] = None
            entry["see_also"] = []

        first_tonight = entry.get("last_seen") != today
        if first_tonight:
            entry["live_days"] = int(entry.get("live_days") or 0) + 1
            if in_stock:
                entry["in_stock_days"] = int(entry.get("in_stock_days") or 0) + 1
        entry["last_seen"] = today
        entry["absent_nights"] = 0
        if in_stock:
            entry["last_in_stock"] = today

        if rows:
            entry["rows"] = _trim_rows(rows, self.row_cap)
            entry["rows_as_of"] = today
        entry.update({k: v for k, v in meta.items() if v is not None})
        return entry

    def seed(self, slug: str, *, today: str, **fields) -> dict:
        """Create an entry for a page that already exists on disk.

        Night one with an empty ledger would otherwise hold every existing page
        below the entry guard for a week. Seeding backdates `first_seen`,
        `live_days`, `in_stock_days` and `last_in_stock` from availability
        history and marks the entry, so genuinely old pages satisfy the guard
        immediately and genuinely new ones still do not.
        """
        entry = self.pages.get(slug) or new_entry(today)
        entry.update({k: v for k, v in fields.items() if v is not None})
        entry["seeded"] = True
        entry.setdefault("state", LIVE)
        self.pages[slug] = entry
        return entry

    # -- redirect chains ----------------------------------------------------

    def resolve_redirects(self, today: str | None = None) -> dict[str, str]:
        """Terminal target for every redirect entry, following A -> B -> C.

        Re-resolved nightly so a stub whose target itself moved is rewritten
        rather than pointing at another stub. Cycle-safe and depth-capped; both
        dead ends leave the stub pointing where it already pointed, which still
        serves a 200 while the review note gets looked at.
        """
        targets = {}
        for slug in self.slugs_in_state(REDIRECT):
            seen = {slug}
            target = self.pages[slug].get("redirect_to")
            hops = 0
            while target and hops < REDIRECT_DEPTH_CAP:
                if target in seen:
                    self.note(slug, "redirect cycle", today, target=target)
                    target = self.pages[slug].get("redirect_to")
                    break
                seen.add(target)
                nxt = self.pages.get(target)
                if not nxt or nxt.get("state") != REDIRECT or not nxt.get("redirect_to"):
                    break
                target = nxt["redirect_to"]
                hops += 1
            else:
                if target:
                    self.note(slug, "redirect depth cap", today, target=target)
            if target and target != self.pages[slug].get("redirect_to"):
                self.note(slug, "redirect retargeted", today,
                          was=self.pages[slug].get("redirect_to"), target=target)
                self.pages[slug]["redirect_to"] = target
            if target:
                targets[slug] = target
        return targets


def _atomic_write(path: Path, data: bytes) -> None:
    """Write via a temp file in the same directory and os.replace.

    A reader (the server, the sitemap, a browser) sees either the whole old file
    or the whole new one. Neither builder writes atomically today, which
    self-heals nightly while files are disposable; once a page is permanent so
    is a truncated one.
    """
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".page-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        # mkstemp hardcodes 0600, and os.replace carries the temp file's mode to
        # the destination, so an atomic write quietly makes every page owner-only.
        # Caddy serves these as another user and answers 403 for them. Match the
        # file being replaced, or fall back to what a plain open() would have
        # produced under the current umask.
        try:
            os.chmod(tmp, stat.S_IMODE(os.stat(path).st_mode))
        except FileNotFoundError:
            umask = os.umask(0)
            os.umask(umask)
            os.chmod(tmp, 0o666 & ~umask)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# Public name for the all-or-nothing write above. `admin_decisions` writes a
# file the nightly reads, and a half-written one would be read as "no decisions"
# on exactly the night the decisions mattered, so it needs the same guarantee
# rather than its own copy of it.
atomic_write = _atomic_write


def write_page(path: Path | str, html: str | bytes) -> bool:
    """Write a page atomically, skipping the write when the bytes are unchanged.

    Returns True if the file was written. Skipping matters once tombstones are
    re-rendered nightly from fixed ledger data: without it every tombstone's
    mtime churns nightly and its sitemap `<lastmod>` keeps claiming a change
    that did not happen.
    """
    path = Path(path)
    data = html.encode("utf-8") if isinstance(html, str) else html
    try:
        if path.read_bytes() == data:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, data)
    return True


# -- the nightly decision --------------------------------------------------

@dataclass
class NightPlan:
    """What the builder should do about the pages it did not generate tonight.

    The ledger has already been updated to match; this is the render/unlink work
    list, so the two cannot disagree about what happened.
    """
    tombstoned: list[str] = field(default_factory=list)
    redirected: dict[str, str] = field(default_factory=dict)
    retired: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    held: dict[str, str] = field(default_factory=dict)
    skipped: bool = False
    seeding: bool = False

    @property
    def removals(self) -> list[str]:
        """Slugs whose file should be unlinked. Only ever non-empty when
        decide_night() was called with allow_delete."""
        return sorted(self.retired + self.deleted)

    def summary(self) -> str:
        if self.seeding:
            return "ledger seeding: no page states changed"
        if self.skipped:
            return "SKIPPED: tonight's page count below the ledger floor"
        return (f"{len(self.tombstoned)} tombstoned, {len(self.redirected)} redirected, "
                f"{len(self.retired)} retired, {len(self.deleted)} deleted, "
                f"{len(self.held)} held")


def rename_target(rows: Sequence[dict], url_to_slug: dict[str, str], *,
                  threshold: float = RENAME_MAJORITY) -> tuple[str | None, list[str]]:
    """Where a page's last-known products are listed tonight.

    Returns (single successor or None, all successors seen). A successor is only
    asserted when *one* slug carries the products and it accounts for at least
    `threshold` of the rows we knew about. Two successors returns None with both
    listed: a redirect asserts a single successor, and a genuine split is better
    served by a tombstone saying "now listed as X and Y" than by picking one.

    The denominator is every stored row with a URL, not the matched ones, so a
    page whose products mostly just vanished cannot be redirected on the
    strength of the one that moved.
    """
    urls = [r.get("url") for r in rows if r.get("url")]
    if not urls:
        return None, []
    hits = Counter(url_to_slug[u] for u in urls if u in url_to_slug)
    if not hits:
        return None, []
    found = sorted(hits)
    if len(found) > 1:
        return None, found
    slug, count = hits.most_common(1)[0]
    if count / len(urls) >= threshold:
        return slug, found
    return None, found


def decide_night(ledger: PageLedger, tonight_slugs: Iterable[str], *, today: str,
                 untrusted: Iterable[str] = (),
                 url_to_slug: dict[str, str] | None = None,
                 retired_check: Callable[[str, dict], str | None] | None = None,
                 allow_delete: bool = False,
                 max_tombstones: int = MAX_TOMBSTONES_PER_NIGHT) -> NightPlan:
    """Classify every page in the ledger that was not generated tonight.

    Applies the decision to the ledger and returns the work list. The order of
    the guards is the order of their blast radius, widest first: no path through
    here can mass-unlink, and only the last two remove anything at all.

    `url_to_slug` maps tonight's product URLs to the slug that carried them,
    which is what makes rename detection possible without this module knowing
    anything about parsing (variety only; combo keys come from taxonomy, so
    combos pass nothing and skip the branch).

    `retired_check(slug, entry)` returns a reason string when the page has left
    the taxonomy, else None. It lives in the builder because the answer needs
    `cultivar_parsing`, which imports stocklib and so cannot be imported here.
    """
    plan = NightPlan()
    tonight = set(tonight_slugs)
    untrusted = set(untrusted)
    url_to_slug = url_to_slug or {}

    if ledger.seeding:
        # Nothing to compare against, so nothing can be classified. No page can
        # be tombstoned until the ledger has a week of history behind it, which
        # is the entry guard working rather than a bug.
        plan.seeding = True
        return plan

    live_count = ledger.live_count()
    if live_count and len(tonight) < GLOBAL_FLOOR_RATIO * live_count:
        # The pipeline broke. Record the night, change nothing.
        ledger.skipped_nights += 1
        ledger.note("*", f"global floor: {len(tonight)} generated vs {live_count} live",
                    today)
        plan.skipped = True
        return plan

    tombstone_budget = max_tombstones
    for slug in sorted(set(ledger.pages) - tonight):
        entry = ledger.pages[slug]
        if entry.get("state") != LIVE:
            continue  # already settled; only observe() moves it back to live

        rows = entry.get("rows") or []

        # 1. Scrape-health gate. If everything we knew about this page came from
        #    nurseries we do not trust tonight, its absence is not evidence.
        #    Deliberately before the exit guard: an untrusted night must not
        #    count toward it either.
        if rows and all(r.get("nursery_key") in untrusted for r in rows):
            plan.held[slug] = "untrusted nurseries"
            continue

        # 2. Exit guard. 85% of disappearances reverse within 24 hours.
        absent = int(entry.get("absent_nights") or 0) + 1
        entry["absent_nights"] = absent
        if absent < EXIT_GUARD_NIGHTS:
            plan.held[slug] = f"absent {absent} of {EXIT_GUARD_NIGHTS} nights"
            continue

        # 3. Entry guard. A page that never established itself is not a URL
        #    worth keeping forever, and keeping it is how the tombstone set
        #    fills with one-night parser noise.
        live_days = int(entry.get("live_days") or 0)
        span = _days_between(entry.get("first_seen"), entry.get("last_seen"))
        if live_days < ENTRY_GUARD_LIVE_DAYS or span < ENTRY_GUARD_SPAN_DAYS:
            if not allow_delete:
                plan.held[slug] = "below entry guard, delete not allowed"
                continue
            plan.deleted.append(slug)
            del ledger.pages[slug]
            continue

        # 4. Rename. Variety only: a combo's key comes from taxonomy, so its
        #    products cannot reappear under a different combo key.
        target, found = rename_target(rows, url_to_slug) if url_to_slug else (None, [])
        if target:
            entry["state"] = REDIRECT
            entry["since"] = today
            entry["redirect_to"] = target
            entry["see_also"] = []
            plan.redirected[slug] = target
            continue
        if found:
            # Split or weak overlap. Tombstone, and say where the products went
            # rather than asserting one successor.
            entry["see_also"] = found
            ledger.note(slug, "split or partial rename", today, targets=found)

        # 5. Retired. The variety left the taxonomy (the DEC-195 gate, or a deny
        #    in variety_overrides.json). The only case where a URL may die.
        reason = retired_check(slug, entry) if retired_check else None
        if reason:
            if not allow_delete:
                plan.held[slug] = f"retired ({reason}), delete not allowed"
                continue
            # The entry stays even though the file goes: it is the record of
            # why a URL was allowed to die, and it lets the page come back
            # whole if the taxonomy gate or the deny list changes its mind.
            entry["state"] = RETIRED
            entry["since"] = today
            entry["retired_reason"] = reason
            plan.retired.append(slug)
            continue

        # 6. Otherwise, tombstone.
        if tombstone_budget <= 0:
            plan.held[slug] = "nightly tombstone cap reached"
            ledger.note(slug, f"tombstone cap {max_tombstones} reached", today)
            entry["absent_nights"] = absent - 1  # reconsider tomorrow, unpenalised
            continue
        tombstone_budget -= 1
        entry["state"] = TOMBSTONE
        entry["since"] = today
        plan.tombstoned.append(slug)

    return plan
