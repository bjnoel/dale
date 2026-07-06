"""
Snapshot coverage guard: drop broken/partial scrape days.

A date is a real data day only when a normal number of nurseries produced a
snapshot for it. A day whose nursery count is far below its NEIGHBOURS' is a
broken or partial scrape, not a real market move: the 2026-07-04 disk-full
incident left six days with a single nursery (vs ~22), which drew a phantom
crash on every species' trend sparkline and blanked out the change list on the
history page around those dates.

The comparison is LOCAL (against nearby days), not global, on purpose: the site
grew from 8 nurseries in March 2026 to ~25, so early history legitimately has low
coverage. A global-median guard would wrongly drop those early days; a local one
keeps a day whose coverage matches its neighbours and drops only a day that
collapses relative to them.

Used by build_species_trends.py and build_history.py (both aggregate or diff
across nurseries by date). Pure functions apart from nursery_coverage's directory
scan, so the guard is unit-testable.
"""
from pathlib import Path

# A day survives when its coverage is at least this fraction of the local median.
COVERAGE_FRACTION = 0.5
# Neighbouring days (each side) whose median defines "normal" coverage locally.
COVERAGE_WINDOW = 10


def nursery_coverage(data_dir, dates) -> dict:
    """Return {date: number of nurseries with a snapshot file that day}."""
    cov = {d: 0 for d in dates}
    for nursery_dir in Path(data_dir).iterdir():
        if not nursery_dir.is_dir():
            continue
        for d in dates:
            if (nursery_dir / f"{d}.json").exists():
                cov[d] += 1
    return cov


def usable_dates(dates, coverage, fraction: float = COVERAGE_FRACTION,
                 window: int = COVERAGE_WINDOW) -> list:
    """Drop dates whose coverage falls far below their local neighbours' median.

    The input order is preserved. Neighbours are the nearest `window` dates on
    each side by position (temporal adjacency), so this is robust to gradual
    coverage growth over the site's history: only a day that collapses relative
    to the days around it is dropped. A date with no positive-coverage neighbours
    (a degenerate window) is kept.
    """
    order = list(dates)
    n = len(order)
    kept = []
    for i, d in enumerate(order):
        lo = max(0, i - window)
        hi = min(n, i + window + 1)
        neigh = sorted(
            coverage.get(order[j], 0)
            for j in range(lo, hi)
            if j != i and coverage.get(order[j], 0) > 0
        )
        if not neigh:
            kept.append(d)
            continue
        local_median = neigh[len(neigh) // 2]
        if coverage.get(d, 0) >= local_median * fraction:
            kept.append(d)
    return kept
