"""
Scrape-health records: one JSONL line per nursery per scraper run.

Today a scraper that fails, returns zero products, or gets blocked (403/429)
is invisible: the snapshot just doesn't get written and nothing downstream
notices. Every scraper (shopify, woocommerce, bigcommerce, ecwid, daleys)
creates a ScrapeHealth per nursery run and finishes it whether the run
succeeded or not, appending a record to data/scraper-health/YYYY-MM-DD.jsonl:

    {ts, nursery, ok, products, in_stock, duration_s, http_403, http_429, error}

detect_scrape_anomalies.py reads these to alert Benedict, the /admin panel
renders the per-nursery health grid from them, and untrusted_nurseries() below
turns them into the "do not believe tonight's absences from this nursery" set
the page-lifecycle ledger gates on. Recording never raises into the scrape
itself: a health-write failure prints a warning instead of killing a scrape
that otherwise worked.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

HEALTH_DIRNAME = "scraper-health"

# untrusted_nurseries() tuning. A nursery is untrusted when tonight's product
# count is below TRUNCATION_RATIO of its median over the previous
# HEALTH_WINDOW_DAYS days, which needs at least MIN_HISTORY_DAYS of history to
# mean anything. 0.6 is deliberately loose: normal night-to-night movement is a
# few percent, and a 40% drop is a truncated feed rather than a nursery selling
# out. Judging a nursery on one or two prior days would make the first week
# after a deploy the most dangerous week.
HEALTH_WINDOW_DAYS = 7
TRUNCATION_RATIO = 0.60
MIN_HISTORY_DAYS = 3


def count_priced(products) -> int:
    """How many of these products carry a usable price.

    Recorded alongside the product count because a nursery can be scraped
    perfectly and still yield no prices, and nothing noticed. PlantNet reported
    price "0" on 79 of its 110 SKUs (it is a wholesale breeder's retail arm, so
    most of its catalogue is "find a stockist"); that became $0.00, then null,
    then a blank cell on the homepage, and no validator or alarm saw it:
    model.validate_snapshot accepts 0.0 as a non-negative price and
    detect_scrape_anomalies had no price rule at all.

    Handles both snapshot dialects: min_price (Shopify/Woo/Wix/BigCommerce/CSV)
    and the flat price key (Ecwid).
    """
    n = 0
    for p in products or ():
        price = p.get("min_price")
        if price is None:
            price = p.get("price")
        try:
            if price is not None and float(price) > 0:
                n += 1
        except (TypeError, ValueError):
            continue
    return n


def default_health_dir() -> Path:
    """data/scraper-health under DALE_DATA_DIR (or the repo data dir),
    resolved at call time so tests can set the env var."""
    base = Path(os.environ.get(
        "DALE_DATA_DIR", Path(__file__).resolve().parents[3] / "data"))
    return base / HEALTH_DIRNAME


def append_record(record: dict, health_dir: Path | str | None = None) -> Path:
    """Append one record to today's JSONL file. Returns the file path."""
    health_dir = Path(health_dir) if health_dir else default_health_dir()
    health_dir.mkdir(parents=True, exist_ok=True)
    path = health_dir / f"{date.today().isoformat()}.jsonl"
    with open(path, "a") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def read_records(day: str, health_dir: Path | str | None = None) -> list[dict]:
    """Read all records for a YYYY-MM-DD day. [] if the file is missing.
    Skips lines that don't parse (a torn write must not kill a reader)."""
    health_dir = Path(health_dir) if health_dir else default_health_dir()
    path = health_dir / f"{day}.jsonl"
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def latest_by_nursery(records: list[dict]) -> dict[str, dict]:
    """Last record per nursery for a day (a re-run appends, last one wins)."""
    latest = {}
    for rec in records:
        nursery = rec.get("nursery")
        if nursery:
            latest[nursery] = rec
    return latest


def untrusted_nurseries(day: str, health_dir: Path | str | None = None, *,
                        window: int = HEALTH_WINDOW_DAYS,
                        ratio: float = TRUNCATION_RATIO,
                        min_history: int = MIN_HISTORY_DAYS) -> set[str]:
    """Nurseries whose `day` scrape must not be read as "these products are gone".

    Three ways to land in here, in increasing subtlety:

    - `ok=false`. The run failed and said so.
    - No record at all, for a nursery seen in the window. Every scraper writes a
      record on the failure path too, so a missing one means the scraper never
      ran (crashed before the recorder, or was not invoked). That is exactly the
      case where the snapshot is stale and every one of its products would read
      as delisted.
    - A count far below its own recent median. The dangerous scrape is the one
      that *succeeds* truncated: `latest.json` covers a failed scrape by keeping
      yesterday's data, but a paginator that quietly stops at page 3 writes a
      real snapshot missing two thirds of the catalogue. Ladybird alone is about
      two thirds of everything we track.

    Deliberately silent when there is no history to judge against: a fresh
    install has no medians, and the ledger's global floor is the backstop there.
    """
    day_date = date.fromisoformat(day)
    today = latest_by_nursery(read_records(day, health_dir))

    history: dict[str, list[int]] = {}
    for back in range(1, window + 1):
        prior = (day_date - timedelta(days=back)).isoformat()
        for nursery, rec in latest_by_nursery(read_records(prior, health_dir)).items():
            if rec.get("ok"):
                history.setdefault(nursery, []).append(int(rec.get("products") or 0))

    untrusted = set()
    for nursery in set(history) | set(today):
        rec = today.get(nursery)
        if rec is None or not rec.get("ok"):
            untrusted.add(nursery)
            continue
        counts = sorted(history.get(nursery, []))
        if len(counts) < min_history:
            continue
        median = counts[len(counts) // 2]
        if median > 0 and int(rec.get("products") or 0) < median * ratio:
            untrusted.add(nursery)
    return untrusted


class ScrapeHealth:
    """Per-nursery run recorder. Create at the start of a nursery's scrape,
    note fetch errors as they happen (thread-safe: ecwid fetches
    concurrently), and call finish() exactly once at the end -- on the
    failure path too, so failures leave a record instead of a gap."""

    def __init__(self, nursery: str, health_dir: Path | str | None = None,
                 source: str | None = None):
        self.nursery = nursery
        self.health_dir = health_dir
        # Which scraper produced this run ("shopify", "feed", "plant_list", ...).
        # Taken at construction rather than at finish() so the FAILURE paths
        # carry it too: every scraper calls finish(ok=False) from at least one
        # except branch, and a failure record that cannot say which scraper was
        # running is the one you most want to read.
        self.source = source
        self.http_403 = 0
        self.http_429 = 0
        self.error: str | None = None
        self._lock = threading.Lock()
        self._start = time.monotonic()

    def note_http_error(self, code: int, url: str = "") -> None:
        """Record an HTTP error from a fetch handler (403/429 are counted)."""
        with self._lock:
            if code == 403:
                self.http_403 += 1
            elif code == 429:
                self.http_429 += 1
            self.error = f"HTTP {code}" + (f" {url}" if url else "")

    def note_error(self, message: str) -> None:
        """Record a non-HTTP error (network failure, parse crash, ...)."""
        with self._lock:
            self.error = str(message)

    def finish(self, products: int = 0, in_stock: int = 0,
               ok: bool | None = None, priced: int | None = None) -> dict:
        """Write the record. ok defaults to: errors are tolerable as long as
        we still got products; zero products with an error means the run
        failed. Pass ok=False explicitly on a crash path.

        `priced` is the count of products carrying a usable price, from
        count_priced(). Optional so a failure path need not supply it."""
        if ok is None:
            ok = products > 0 or self.error is None
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "nursery": self.nursery,
            "ok": bool(ok),
            "products": int(products),
            "in_stock": int(in_stock),
            "duration_s": round(time.monotonic() - self._start, 2),
            "http_403": self.http_403,
            "http_429": self.http_429,
            "error": self.error,
        }
        if priced is not None:
            record["priced"] = int(priced)
        if self.source:
            record["source"] = self.source
        try:
            append_record(record, self.health_dir)
        except OSError as e:
            print(f"  WARNING: could not write scrape-health record: {e}")
        return record


# --- Dormancy -------------------------------------------------------------
#
# untrusted_nurseries() answers "should I believe tonight's absences". This
# answers the slower question: has this nursery gone dark for good, for now?
#
# A seasonal bare-root nursery closes its store between seasons. Heritage Fruit
# Trees shut online sales for 2026 on 2026-08-24 ("Online plant sales for 2026
# have finished") and will be a wall of HTTP 503 until the 2027 season. The
# scraper has no retry or backoff, so it walked ~240 product URLs into that wall
# every night, and would have kept doing it for six months. Scraping a closed
# store thousands of times is wasteful and it is rude to a nursery we have a
# relationship with; scraping already cost goodwill once (Beewise, DEC-198).
#
# So: after DORMANT_AFTER_FAILURES consecutive failed runs, drop to one probe a
# week. Self-healing in both directions. No record is written on a skipped day,
# which untrusted_nurseries() already reads as "do not believe this nursery's
# absences today", and the moment a probe succeeds the streak resets to 0 and
# nightly scraping resumes on its own. Nothing to un-flip by hand.
#
# Five, not three, because of the only real outage we can measure. Heritage
# 503ed on 08-12, 08-13 and 08-14 2026 and came back on the 15th: a threshold of
# three would have declared that recoverable blip dormant and then sat out the
# recovery until the next Monday. The cost of waiting is two more nights of
# wasted requests; the cost of going early is losing days of a live catalogue.
DORMANT_AFTER_FAILURES = 5
PROBE_WEEKDAY = 0  # Monday
DORMANCY_LOOKBACK_DAYS = 400

# A closed store does not have to 503 at you. On 2026-08-26 Heritage started
# answering HTTP 200 again with its whole catalogue intact and every single
# product reading OutOfStock with the price withdrawn: 378 products, 0 in
# stock, 1 priced. That is a success by every measure the recorder had, so the
# streak above reset to 0 and nightly scraping resumed against a store that
# had not reopened. The runs got LONGER, not shorter (432s on the last real
# day, then 1235s and 1245s), because 503s fail fast and 200s do not.
#
# So a run is judged on whether it yielded anything, not on whether the HTTP
# layer stayed quiet. Both conditions are required, and the second is the load
# bearing one: a nursery that is genuinely sold out but still trading keeps its
# prices on the page, so it reads ~100% priced and is never called unproductive.
# Withdrawing the prices as well is what distinguishes "closed" from "sold out",
# and it protects the restock alerts that are the point of scraping daily.
#
# Measured base rate before shipping: across 27 nurseries and 200 days of health
# records, `ok` runs with products > 0 and in_stock == 0 happened exactly twice,
# both of them Heritage on 08-26 and 08-27. No healthy nursery has ever been in
# this state, and Heritage sits at 0.3% priced against a 10% threshold.
UNPRODUCTIVE_PRICED_SHARE = 0.10


def is_unproductive(rec: dict, *,
                    priced_share: float = UNPRODUCTIVE_PRICED_SHARE) -> bool:
    """True when a run succeeded but returned a catalogue with nothing to sell.

    Everything out of stock AND the prices withdrawn. Either alone is normal:
    a nursery can sell out and keep trading, and some feeds price lazily. A
    store showing hundreds of products, none buyable and none priced, is shut
    whatever its status code says.

    Records written before `priced` was recorded cannot be judged and are
    treated as productive, so this can never retroactively rewrite history.
    """
    if not rec.get("ok"):
        return False
    products = int(rec.get("products") or 0)
    if products <= 0 or int(rec.get("in_stock") or 0) > 0:
        return False
    priced = rec.get("priced")
    if priced is None:
        return False
    return int(priced) / products < priced_share


def consecutive_failures(nursery: str, day: str,
                         health_dir: Path | str | None = None, *,
                         lookback: int = DORMANCY_LOOKBACK_DAYS) -> int:
    """How many of this nursery's most recent runs yielded nothing, from `day` back.

    Counts failed runs and runs that succeeded into an empty catalogue
    (`is_unproductive`) as the same thing, because for the question this answers
    -- is it worth scraping tonight -- they are. A store that answers 200 with
    nothing buyable and nothing priced costs more per night than one that 503s.

    Days carrying no record for the nursery are skipped rather than counted:
    a skipped probe is an absence of evidence, not a failure. That is what lets
    the streak survive the weekly-probe regime it triggers, instead of decaying
    to zero on the six days a week nothing runs.
    """
    day_date = date.fromisoformat(day)
    streak = 0
    for back in range(0, lookback + 1):
        rec = latest_by_nursery(read_records(
            (day_date - timedelta(days=back)).isoformat(), health_dir)).get(nursery)
        if rec is None:
            continue
        if rec.get("ok") and not is_unproductive(rec):
            return streak
        streak += 1
    return streak


def is_dormant(nursery: str, day: str, health_dir: Path | str | None = None, *,
               after: int = DORMANT_AFTER_FAILURES) -> bool:
    """True when the nursery has failed `after` runs in a row and is presumed shut."""
    return consecutive_failures(nursery, day, health_dir) >= after


def should_probe(nursery: str, day: str, health_dir: Path | str | None = None, *,
                 after: int = DORMANT_AFTER_FAILURES,
                 weekday: int = PROBE_WEEKDAY) -> bool:
    """Whether to actually run this nursery's scrape on `day`.

    Always true until a nursery is dormant, so a nursery having one bad night
    (or three) is never quietly dropped to weekly without having earned it.
    """
    if not is_dormant(nursery, day, health_dir, after=after):
        return True
    return date.fromisoformat(day).weekday() == weekday


def last_success_day(nursery: str, day: str,
                     health_dir: Path | str | None = None, *,
                     lookback: int = DORMANCY_LOOKBACK_DAYS) -> str | None:
    """The most recent day at or before `day` that yielded a real catalogue, else None.

    Same bar as `consecutive_failures`, so the skip message cannot report a
    "last good scrape" of last night while skipping the nursery as dormant.
    """
    day_date = date.fromisoformat(day)
    for back in range(0, lookback + 1):
        d = (day_date - timedelta(days=back)).isoformat()
        rec = latest_by_nursery(read_records(d, health_dir)).get(nursery)
        if rec is not None and rec.get("ok") and not is_unproductive(rec):
            return d
    return None
