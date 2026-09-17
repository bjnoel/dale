# 2026-09-17 — The recurring goal has no product behind it, and the one-time gap is half what we said

**Ticket:** DAL-276 · **Decision:** DEC-340 · **Cost:** $0

Treesmith's stated goal is "$100/month recurring". The only auto-renewing thing we sell is Cloud
Backup at A$9.99/yr, and it has never sold in production. This was the session that went and
checked whether that goal has a product behind it.

## Three findings

**It is 23 people, not 48.** We have been saying 48 people reached the cloud-backup paywall and none
of them bought. 48 was a count of *events*. Counted properly, by person, it is 23 people across 52
events. Zero sales to 23 people over four and a half months tells you almost nothing.

The test I had planned — split those people by whether they already owned Pro, which separates
"priced out" from "did not want it" — **cannot be run**. The property that would tell us is missing
on 18 of the 23. Reporting that as unanswerable rather than answering it from the five people who do
carry it.

**Cloud Backup genuinely has never sold, and it is not broken.** Our analytics showed five
cloud-backup purchases, which looked like sales our payment records were missing. They are all test
purchases from our own internal build era. The payment records' five sandbox rows total US$136.56
exactly, matching the known test set, and none is the backup product. Nothing to fix.

**The number we have been quoting for our sales conversion rate is about half what it should be.**
We had been saying 2.3% of iPhone installs buy. That divided real sales by an install count from a
system we had *already measured* to roughly double the true figure. Against Apple's own download
report, the rate is **5.9%** over a clean window (3 sales in 51 downloads), or somewhere in **4.0% to
5.9%** all time.

## What it means

At about US$17.50 kept per sale, $100/month is under 6 sales a month.

| conversion rate | installs/month needed | vs our current ~58 |
|---|---|---|
| 2.3% (the old, wrong figure) | 248 | 4.3x away |
| 4.0% | 143 | 2.5x away |
| 5.9% | 97 | 1.7x away |

So the gap to $100/month of **total** revenue is roughly **2x**, not the 5x we wrote this morning.
With honest error bars: that rests on 4 sales, and it could be 1x or 5x.

For **recurring** revenue nothing improves. Cloud Backup would need around 1,200 subscribers. It also
requires buying Pro first, so it is a second decision — and all four of our buyers bought on the day
they installed. Nobody has ever made a second decision about this app.

## The recommendation

Point the goal at $100/month of total revenue rather than recurring revenue. Not because the bar is
too high, but because it is currently aimed at the one product that cannot clear it. That is
Benedict's call and it is sitting with him.

## The lesson

**A rate is a ratio of two systems, and fixing one of them does not fix the ratio.** We correctly
established six weeks ago that one of our data sources inflates install counts. We never went back
and re-divided the numbers we had already computed from it. The corrected figure was sitting in our
own state file the entire time, in a different section, quietly disagreeing. Nothing compares two
findings to each other. When you correct an input, list what was computed from it.
