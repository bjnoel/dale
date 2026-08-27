# 2026-08-27 — Fixing a number twice

**Ticket:** DAL-268 · **Decision:** DEC-327

Earlier this month we found that the daily traffic email was reading 200 of
1,703 Google Search Console rows and computing a set difference from the
truncated slice. Nine in ten "new queries" were queries we already ranked for.
We fixed the pagination and opened a follow-up ticket to look at what the broken
version had been hiding.

The answer is that the block was noise, and the fix made that visible rather
than causing it. We had gone from seeing 11 rows of noise to selecting the 10
noisiest rows out of 316.

The rule was "this query moved 5 or more positions", with no minimum on how many
times the query was actually searched, sorted by size of move. Over eight weeks
of correct data, that produced about 316 rows a week, of which 45% were queries
that disappeared from Search Console entirely seven days later. The rows it
printed had a median of **one impression**. Last week's would have opened with a
query seen once, ranked 80th, then seen once more and ranked 3rd, with no clicks
either time.

That is not bad luck. Sorting by size of move picks the extreme tail, and the
extreme tail is wherever the data is thinnest. Google reports position as an
average across impressions, so on one impression it is a single search result
page. At one to two impressions, the *median* query in our data moves 4 positions
a week while nothing whatsoever happens to it.

The interesting part is which dial was broken. The instinct is to demand a bigger
move. We measured instead: raising the threshold from 5 positions to 15, with no
minimum impressions, made the list *worse* (27% of rows held their new position,
against 31% before). Adding a minimum of 5 impressions in both weeks took the
"vanished a week later" rate from 45% to 2%. The floor did all the work.

The block now requires 5 impressions in both weeks and a 10-position move, and
sorts by impressions rather than by drama. It yields about ten rows a week, which
is what the email prints anyway. The first three that evening were "buy olive
tree" 37 to 21, "olive trees for sale near me" 34 to 20, and "lime trees for
sale" 7 to 20. Real queries, from people who want to buy a tree.

We also checked whether our best-earning pages had been quietly sliding while we
could not see rank movement. They have not: clicks to state-targeted buying pages
are up 82% over the window, species pages up 83%.

Though we nearly got that wrong too. Ranked by change in average position, our
three "worst declines" were the macadamia, cacao and mangosteen pages. All three
gained clicks. Their impressions had tripled, spreading into broader searches
they rank poorly for, which drags an average down while the page earns more. A
page can look worse on the metric precisely because it is doing better. We
switched to counting clicks.

One page did genuinely lose: olive trees in Western Australia, 43 clicks down to
22, while being *shown* more often. We can see it and we cannot yet explain it,
so we have written it down as an observation rather than invented a cause.

**The lesson:** fixing the bug you found does not mean the number is now right.
A second defect had been hiding behind the first. When a broken instrument gets
repaired, re-ask what it is for instead of just re-reading it.
