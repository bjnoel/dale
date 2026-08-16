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

    def __init__(self, nursery: str, health_dir: Path | str | None = None):
        self.nursery = nursery
        self.health_dir = health_dir
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
               ok: bool | None = None) -> dict:
        """Write the record. ok defaults to: errors are tolerable as long as
        we still got products; zero products with an error means the run
        failed. Pass ok=False explicitly on a crash path."""
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
        try:
            append_record(record, self.health_dir)
        except OSError as e:
            print(f"  WARNING: could not write scrape-health record: {e}")
        return record
