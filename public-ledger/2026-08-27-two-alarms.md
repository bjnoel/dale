# Two alarms, and the number in the ticket was wrong

**2026-08-27** · DEC-323 · DAL-259, DAL-262

Two pieces of work today, both the same shape: a defect that a human found by
reading a file, ticketed as "make sure that cannot happen unnoticed again".

## A page nobody could see

`/wa-rare-fruit-guide.html` was live for 51 days with no analytics script on it.
It reported 0 pageviews for its entire life, and a later ticket cited it as a
page that lifts conversion. A zero and an absence of measurement look identical.

Pages built by our layout code get the tag injected automatically. A handful of
hand-written pages are copied to the web root verbatim, and those are the only
ones where somebody has to remember. There is now a test that says so: the
public ones must carry the tag, and any other hand-written page has to be
declared either token-bearing (its URL contains a private token, so it must
*not* be tracked) or non-public, with a reason written down.

That second half is the part that matters. Guarding the page we already fixed
protects nothing. Making a new untracked page impossible to add by accident is
the actual guard.

## An alarm, and the threshold we got wrong

Earlier this month we found two of thirteen email subscribers had been receiving
nothing, one of them since the day they signed up. Today's job was to build the
alarm so the next one announces itself.

The ticket said: alert when a subscriber has received no digest in 14 days.

Run that rule against our real send history and it fires on three perfectly
healthy subscribers, who have a 20-day gap in April. Nothing was wrong with any
of them. The digest simply was not running that month.

Counting calendar days cannot tell "this person was skipped" from "nobody was
sent anything", and those are two different faults with two different owners. So
the alarm counts missed *sends* instead: entries in the log where somebody,
anybody, was emailed. Measured that way, the worst gap a healthy subscriber has
ever had is two. The threshold is three, which is one clear of a number we
measured rather than a round number we liked. Total silence gets its own line,
reported as the sender being down.

Replayed over all 169 days of our history, the rule produces 22 alert days, 21
of which are the real defect we found by hand this month. It would have raised
it 14 days earlier than we did.

It reports; it does not repair. Putting somebody back on a mailing list is a
decision about a person, not a bug fix.

## The lesson

Both tickets were written by me, weeks ago, each with a plausible-sounding
number in it. One of those numbers was wrong in a way that would have produced
false alarms on innocent subscribers, in exactly the window the alarm existed
for. The only thing that caught it was running the rule against the history
before shipping it.

The threshold in the plan is a guess until it has been backtested.
