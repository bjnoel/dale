# 2026-08-27 — The blocker was made of nothing

**Decision:** DEC-329 · **Ticket:** DAL-248 · **Cost:** $0

We had exactly one ticket ready to work, and it said it was blocked. An earlier
session today checked why, found that Benedict had not yet sent an overdue reply to
Daleys, and correctly declined to pile more drafts on top of an email already waiting
in his queue. Good reasoning.

The reply he was waiting to send did not exist.

The register had been telling him to send
`deliverables/daleys-reply-2026-08-27.txt`. That file was never written. Not on disk,
not in git, not in a Linear comment. The top item in his queue pointed at nothing he
could open, and our only actionable ticket sat blocked behind it. Our own validator
said the register was fine the whole time, because it checks that a record is well
formed, not that an instruction can be followed.

## Why it was always going to happen

Two of our own conventions disagree. Deliverables are supposed to live in Linear,
because Benedict triages on his phone and a file path in a git repo is useless there.
The nursery register's convention is to name a file. A deliverable written under the
first rule can never satisfy a pointer written under the second.

## What we did

The draft now exists, in Linear, on the ticket it unblocks. The register links to
that comment instead of naming a file. And `validate` now fails any outstanding
action that names a repo path which is not on disk.

We proved that rule fails before trusting it to pass: run it against the Daleys text
verbatim and it fires. We also gave it something good to stay quiet about, an action
citing a document that does exist, because a check that cannot stay silent on a
correct case is a check that gets switched off inside a month.

It only looks at outstanding actions, not at the history. An older Ross Creek record
cites a draft that is also gone, but that email was sent and nobody is waiting on it.
Failing on dead paperwork would bury the failure that matters.

## Checking the facts again rather than copying them

Everything the email says was re-pulled rather than carried forward from the morning.
Daleys' feed still disagrees with itself on exactly two rows. Their out-of-stock
normalisation is complete, 2,949 rows, none left in the old spelling. And our own
almond page still ranks a $9.75 grafting stick above every real tree on it, which is
our bug and the email says so plainly.

One thing changed on the re-check. The note we had written said to compare that
$9.75 against a $44.99 almond. That $44.99 belongs to a different nursery. Quoting
one nursery's price at another to illustrate our own mistake is a bad trade, and it
is the reverse of a rule we applied a fortnight ago when we kept Daleys' sales
figures out of five other nurseries' emails. Daleys' own $59.00 tree of the identical
cultivar sits seven rows below their own stick on the same page. Better number, and
theirs to see.

## The lesson

An instruction nobody can follow looks exactly like a blocker, and it gets reported
to you as one. We concluded we were waiting on a person when we were waiting on
ourselves. The check that tells the two apart takes one command: before recording
that you are blocked on somebody, open the thing you are asking them to act on and
confirm it is there.
