# The review prompt asked one person in 24 days

*2026-08-27*

The in-app "would you rate TreeSmith?" prompt has been live on real devices since 3 August.
Nobody had checked what it actually did, so today we did.

| event | count | people |
|---|---|---|
| prompt suppressed | 126 | 48 |
| prompt actually shown | **1** | **1** |

One ask. 26 August, iOS, from someone who had added three or more plants. The cooldown that
stops us asking again fired correctly the next day, so the feature works end to end. It simply
never gets to run.

## Why

Every gate that declined records which gate it was. The tally: 81 "a version changed recently",
29 "something went wrong for this user recently", 14 "they just restored a backup", 2 "we asked
them already".

What is missing is the interesting part. Not a single decline for "too few active days", "too
new an install" or "no qualifying moment". Those gates sit below the version check, so in three
and a half weeks the prompt has reached the question it exists to ask exactly once.

The version check keys on the build number, not the release. Going from build 61 to build 62 of
the same version counts as a new version and starts a fresh three-day quiet period. We shipped
builds 55, 56, 57, 58, 59, 60, 61 and 62 between 28 July and 17 August, a median of about three
days apart, against a three-day quiet period. Each device restarts its own clock the day it takes
the update.

The one person who was asked proves the mechanism rather than contradicting it: they took build
62 on 21 August, the quiet period ran to the 24th, and the prompt fired on the 26th. It is the
first stretch in the whole series where a device sat on one build longer than the blackout.

The fix is one line, returning the release version without the build number. It is app code, so
it is Benedict's to take rather than ours to ship.

## What the stores tell us about ratings: nothing

Worth stating plainly, because it shapes what we can ever measure. Neither Apple nor Google
reports back. Both review APIs return nothing at all: we are not told whether the sheet appeared,
whether anyone rated, or what they gave. All we can read is the public total, and on both stores
that total is still zero.

## The honest limit

People who opted out of analytics send no events but are still eligible to be asked, so one ask
is a floor rather than a fact. 48 people show up in this data against 75 who opened the app since
3 August; most of that gap is devices still on older builds that never carried the feature.

The lesson we are keeping: a gate that fires on our own release cadence rather than on the user
looks exactly like a gate that is working. 126 events, a plausible spread of reasons, and the
feature had never once got to the question.
