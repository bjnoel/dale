"""A DEC number is an identifier, so two entries must not share one.

There is no allocator. A DEC id is a number somebody appends to a shared file,
which is fine with one writer and a race with several. On 2026-08-20 two
sessions working this repo in parallel both appended a DEC-307 on the same day,
and the collision was only noticed because one of them happened to read the
other's commit subject in passing.

That matters more than tidiness: DEC ids are cited from ledger entries, Linear
tickets, code comments and memory. "See DEC-307" resolving to two different
decisions makes the citation useless, and the wrong one is a plausible answer.

The eight duplicates below are historical, all from March 2026, and are left
alone deliberately. Renumbering a five-month-old decision breaks every citation
that already points at it, which is the exact harm this test exists to prevent.
"""

import re
import unittest
from collections import Counter
from pathlib import Path

LOG = Path(__file__).resolve().parents[1] / "decisions" / "decision-log.md"
HEADING = re.compile(r"^## DEC-(\d+)\b", re.MULTILINE)

# Collisions that predate this guard. Do NOT add to this list to make a failure
# go away: renumber the entry that landed second instead, the way DEC-308 was.
KNOWN_HISTORICAL_DUPLICATES = frozenset({50, 51, 83, 84, 85, 102, 103, 104})


def numbers():
    return [int(n) for n in HEADING.findall(LOG.read_text(encoding="utf-8"))]


class TestDecisionIdsAreUnique(unittest.TestCase):
    def test_no_new_duplicate_dec_number(self):
        counts = Counter(numbers())
        dupes = {n for n, c in counts.items() if c > 1}
        new = sorted(dupes - KNOWN_HISTORICAL_DUPLICATES)
        self.assertEqual(
            new, [],
            "DEC number(s) used twice: "
            + ", ".join(f"DEC-{n:03d}" for n in new)
            + ". Two sessions probably appended at once. Renumber the entry that "
              "landed SECOND (check `git log` order), and update anything citing "
              "it. Do not add it to KNOWN_HISTORICAL_DUPLICATES.",
        )

    def test_the_historical_list_does_not_grow(self):
        # It is an amnesty for what predates the guard, not a pressure valve.
        counts = Counter(numbers())
        still_duplicated = {n for n, c in counts.items() if c > 1}
        stale = sorted(KNOWN_HISTORICAL_DUPLICATES - still_duplicated)
        self.assertEqual(
            stale, [],
            "these are no longer duplicated, so drop them from "
            "KNOWN_HISTORICAL_DUPLICATES: "
            + ", ".join(f"DEC-{n:03d}" for n in stale),
        )

    def test_the_log_still_parses_as_a_decision_log(self):
        # If the heading shape ever changes, the guard above silently passes on
        # an empty list and stops guarding anything at all.
        found = numbers()
        self.assertGreater(len(found), 300, "no DEC headings parsed; format changed?")
        self.assertIn(308, found)


if __name__ == "__main__":
    unittest.main()
