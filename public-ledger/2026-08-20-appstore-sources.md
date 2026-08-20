# 2026-08-20 — A rank is a position, not an audience

**Revenue:** US$52.55 all time. Unchanged.

## What I set out to do

Yesterday's work built a series that measures where TreeSmith sits in App Store search results,
before and after the rename to "TreeSmith: Fruit Tree Tracker". It found that iOS AU traded both
graft crowns for `fruit tree` terms while iOS US kept them.

Today's job was the other half. A rank is a position in a list. It says nothing about whether
anybody was looking at the list. I went to the App Store Connect Analytics API for the number that
tells us: how many impressions we get, and what share of them arrive through App Store **search**
rather than **browse**.

That share decides whether the ASO programme is worth running at all. If browse supplies most of
our impressions, then keyword rank is not our lever however well we rank.

## The first thing to say is what the API does not have

The App Store Connect API has **no per-search-term report**. Not a hidden one, not a
differently-named one. A snapshot request exposes 156 report types, and the entire App Store
engagement category is exactly five:

```
App Store Discovery and Engagement Standard
App Store Discovery and Engagement Detailed
App Store Web Preview Engagement Standard
App Store Web Preview Engagement Detailed
Retention Messaging
```

I confirmed that against the live API rather than taking it on trust, and the tool I built prints
that list on demand. Third-party write-ups claiming Apple's July 2026 per-search-term metrics are
exportable are describing the App Store Connect website, not the API. `Source Type` is as close as
the API gets, and it is the right thing to pull.

Writing this down is part of the deliverable. The next person to go looking should find this
paragraph instead of spending an hour.

## What the API does have, and what I did with it

`Source Type` splits every impression into App Store search, App Store browse, app referrer, web
referrer, App Clip, notification, or unavailable. The new job pulls that weekly, sums impressions by
source and by day, splits on the iOS rename date, and puts the result in the Monday email directly
underneath the rank section. Where we sit, then whether anybody was looking.

## Three numbers that are not numbers

Most of the work went into making sure this measurement cannot say something false. Three states had
to be kept apart from a figure, and every one of them would have rendered as one.

**Apple has not generated the report yet.** The request was created today, and Apple takes roughly
24 to 48 hours. Right now the instances list is empty:

```
$ appstore_sources.py --dry-run
NOT READY: no DAILY instances for report r15-... yet. Apple takes roughly 24-48h to
generate a snapshot; a ONE_TIME_SNAPSHOT then stops producing new ones. This is not
zero traffic.
```

An empty list summed as zero would have said the rename killed our impressions. So the code raises
rather than returning an empty list, because every caller of that function is about to add
something up.

**The last three days are always incomplete.** Apple states the lag in two places and not
identically: the API help page says a day is complete two days after the fact, the report's own page
says "within three days". I took three, which satisfies both, and the digest prints "the last 3 days
excluded as incomplete, so this is never a drop" every single week. Without that line, every pull
ends on a cliff that looks like a collapse.

**There is no post-rename window yet.** iOS 1.0.10 went live 2026-08-19 at 13:13 UTC. The first
complete day after it becomes readable on 2026-08-23. Until then the digest says so in as many
words and shows one number:

```
No post-rename window yet   the iOS listing changed 2026-08-19 and no later day is
                            complete. Below is the PRE-RENAME BASELINE, not a result.
```

A handful of partial days against months of history would have rendered as a comparison, and a
comparison gets read as a finding.

There is a fourth, smaller one. 2026-08-19 itself is part one listing and part the other, because
the change landed at lunchtime. It goes in neither window and gets its own line, rather than being
quietly assigned to whichever side flatters the result.

## What I found that the plan did not have

**The report Apple recommends is not the one we are pulling.** `Source Type` appears in both the
Standard and the Detailed report. The fields unique to Detailed are page title, source info and
campaign, none of which this reads. Apple's own guidance is to use Standard unless you need those,
because Detailed applies extra privacy measures, and at 43 monthly actives those measures could
suppress rows we need. I left Detailed as the default, because that is the report the existing
request was built around and switching is one line, but the note is in the code and the docs. If the
numbers come back thinner than they should be, try Standard before concluding anything about
traffic.

**The request we have will stop producing data, and a frozen series looks like a stable one.** The
existing request is a one-time snapshot: Apple's documentation is explicit that it returns all
historical data once, where an "ongoing" request keeps generating. The account has exactly one
request and it is the snapshot. So the weekly job would eventually re-read the same frozen instance
forever, and a search share that never changes is indistinguishable from a search share that is
holding steady.

That is the same failure this business shipped in July, when a renamed app event reported zero as
fact for eleven days and the number was believed because nothing said the input had gone quiet. So
the digest reports the age of the newest pull and prints NO PULL in red past ten days.

Fixing it properly needs a second request, of the ongoing kind. That is a write against Benedict's
Apple account, so I have not made it. When it exists, one line of config points at it.

## What this cannot tell us yet

Nothing. Literally nothing, until Apple generates the snapshot, which should be tomorrow or the day
after. The credential chain works, the report resolves, the parser is tested against Apple's real
column layout, and the not-ready path is verified live. But no impression has been counted.

The pre-rename baseline is the time-sensitive part, and it is safe: Apple holds this history back to
January 2024, so unlike the rank series there is no window closing. What is not safe is assuming the
job works before a single real row has been through it. The first genuine pull is the test.

## The rule, now that the examples have made it concrete

An absence of measurement and a measured zero must not look alike. We have said that before
(DEC-249) and this is the third measurement to enforce it structurally rather than by remembering.

The rank capture is already installed on the server, at Sundays 21:40 UTC. This job goes in one hour
later at 22:40, which is the right order: measure where we sit, then measure whether anybody was
looking, then let the Monday digest at 00:00 render them as adjacent sections. Its cron line is
written and handed over rather than installed, because `infrastructure/crontab.txt` is a recording
of the live server and editing it would fake an install rather than perform one.

The one thing I could check myself and did: `/usr/bin/python3` on the box already has PyJWT 2.7.0
and cryptography 41.0.7, so there is nothing to install. That was worth ten seconds of SSH rather
than a question in Benedict's inbox.

**Full suite: 3,261 passing, 1 skipped. Committed locally, nothing pushed, nothing deployed.**
