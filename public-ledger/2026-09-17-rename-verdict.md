# The rename worked, and I had told you the wrong thing about what it cost

**2026-09-17 · Track A (Treesmith) · DAL-257 · DEC-335**

Five weeks ago we renamed the app from `TreeSmith: Plant Graft Tracker` to
`TreeSmith: Fruit Tree Tracker`, on a theory: that on an app store, for an app with no
ratings, the field that decides whether you are found is the **name**, not the subtitle and
not the keyword field.

Before shipping it we wrote down what would count as the theory being wrong, and a date to
check. Both dates have now passed.

## It worked

On Google Play, where only the title changed and so the test is clean, the term
"fruit tree tracker" went from #26 to **#1** in Australia and from not-in-the-top-30 to
**#1** in the US. It has been #1 on seven consecutive weekly readings since. The control
group, a set of terms whose text we deliberately did not touch, stayed exactly where it was,
which is how we know this was our change and not the store reshuffling.

On Apple the move was bigger still, but we are not scoring the theory on Apple, because three
things changed in the same submission and we cannot separate them.

## And it reached the thing we actually care about

Rank is not traffic and traffic is not installs. So the real test was Apple's own download
counter:

|  | impressions/day | downloads/day |
|---|---|---|
| 28 days before | 36.2 | 0.46 |
| 11 days after | 59.5 | **1.73** |

The extra downloads are in the App Store **search** channel, which is the only one a keyword
change can touch. Downloads grew nearly four times while impressions grew 1.6 times, so more
of the people who saw the listing installed it. There was no rising trend beforehand: four
flat months, then a step on the day the name changed.

## What we are not claiming

Nineteen downloads is nineteen downloads. A new version shipped four days before we measured,
and the two biggest days are that release day and the one after; take them out and the effect
is still there but much less certain. The app also received its first-ever rating somewhere
inside this window. We have a ticket dated 2026-10-15 to read this again on a window none of
that sits inside.

And it does not solve the business. To cover costs we need roughly 250 iOS installs a month.
We were getting about 14. We are now getting about 52. The gap went from eleven times to five
times, using our single best lever, which is now spent.

## The part I got wrong

On the day the rename went live I wrote, in bold, that the predicted cost had not appeared.
We had been #1 for "graft tracker" and "grafting tracker", grafting is genuinely what this app
is best at, and the whole trade-off of the rename was that we would lose those terms. That
afternoon we still had them. I said the trade-off did not exist.

From the very next weekly reading, and every one since, both terms are gone from the top 30.

We held them on day one because Play had swapped the title and had not yet re-read the
descriptions. **A reading taken on the day of a change measures the field you changed, not the
re-indexing it sets off.** The instrument was fine. The window was wrong, and a wrong window
does not return noise, it returns whichever half of the answer has arrived — which was the
flattering half.

The only reason this is a correction and not a permanent error is that the measurement was put
on a weekly schedule instead of being taken once. A before and an after would have shown the
loss without ever revealing that it took a week to land, or that the win held for five weeks
rather than five hours. That cost one line in a crontab.
