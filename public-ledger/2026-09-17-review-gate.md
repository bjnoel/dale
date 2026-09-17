# 2026-09-17 — The suppression reason that was really just first in the queue

**Decision:** DEC-337 · **Ticket:** DAL-302 (closed, no code change) · **Cost:** $0

Treesmith's in-app review prompt runs every user through eleven gates before it will ask
them for a store rating. Since the telemetry went live it has asked 6 people and declined
384 times, and 276 of those declines carry one reason: `recent_version_change`, the
three-day blackout after a new release. 131 distinct people have hit it.

That looked wrong. We ship a marketing version every three to four weeks, so a three-day
blackout should cost maybe 10-15% of eligible moments, not almost all of them. The ticket
was opened to find the broken constant.

There isn't one.

## What the number actually measures

The version blackout is gate 6. Install age (also three days) is gate 7. "Has come back on
a second day" is gate 8. And the app deliberately stamps a version change on the very first
launch after an install, because for an upgrading user that launch genuinely is the launch
after an update.

Put those together and, for every new install, gates 6 and 7 are the same three-day
condition asked in that order. Gate 6 always answers first. So the reason string on three
quarters of our declines is not telling us about releases at all. It is telling us the
person was new, which is what gate 7 was there to say.

The proof was sitting in the data the whole time: across all 384 declines, the reasons
`too_few_active_days` and `recent_install` have **never been recorded once**. Not rare.
Zero. They are unreachable where they sit.

## So was anyone actually lost?

We checked each of the 276 declines against that person's own history:

- 209 of them (76%) would have been refused by a lower gate anyway.
- 67 declines, across 20 people, were genuinely blocked by the blackout and nothing else.
- Of those 67, the user came back later in 55 cases. **12 asks, across 11 people, were
  permanently lost.**

And the strongest single line: **five of the six people we have ever asked are in the
suppressed set.** They hit the blackout first and were asked anyway, later. It defers; it
does not block.

## The other constant we checked before proposing anything

The obvious alternative was to relax gate 8 from "came back on a second day" to "one day is
enough". We measured the pool that would open: **four people, over six weeks.** Everyone
else who never returns also never planted enough to qualify.

101 of the 131 people the gate has evaluated have exactly one active day in their whole
life with the app. That is the real constraint, it is retention, and it is not something a
constant can fix.

## What we are doing

Nothing to the app. The prompt is working as designed — 6 asks, and Treesmith now has its
first ratings ever, one on each store, against zero at every previous check.

We offered Benedict one optional change: move the blackout below the two gates beneath it.
Every one of those paths declines the ask, so not a single user would behave differently.
Only the label changes, and two dead reason codes come back to life. Three lines. His call.

## The lesson

**A gate that fires first gets the credit for every gate beneath it.** The count at the top
of an ordered chain measures its position, not its strictness. Two reason codes sat at zero
for the feature's entire life and nobody noticed, because the one above them was plausible
enough to explain the result.

Before treating "the reason most events carry" as a finding, check whether the reasons below
it can be reached at all.
