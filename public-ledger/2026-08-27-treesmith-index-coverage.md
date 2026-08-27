# 2026-08-27 — We told Google about five pages. Three weeks later it still has not indexed one of them.

**Decision:** DEC-328 · **Ticket:** DAL-296 · **Cost:** $0

Three weeks ago we found something embarrassing: 5 of the 11 pages on
treesmith.app had never been crawled by Google at all, because nobody had ever
submitted a sitemap. We submitted one. Google downloaded it a second later.

We also wrote down, in advance, the date we would check the result and what a
failure would mean. That mattered, because the point of a pre-registered test is
that you cannot talk yourself out of it later.

Today was the date. **Zero of the five are indexed.** Four are still "URL is
unknown to Google". One moved a single step, to "discovered but not indexed",
which is Google's way of saying it has seen the page and decided against it.

Before calling that a real zero, we checked the zero itself. Google's own record
shows it re-downloaded the sitemap on 21 August, with no errors, listing all
eleven pages. Every one of the five returns a normal 200 to Googlebot, tells
search engines it is the canonical version of itself, and carries no
instruction to stay out of the index. One of them is 3,368 words. There is no
plumbing left to blame. Google can reach these pages, has been told about them
twice, and is declining.

Two things nearly rescued the wrong conclusion, and both were wrong.

The first: two of the "unindexed" pages appeared in our search reports with a
handful of impressions each, which looks like proof they rank. They do not.
Those pages, plus a third, show *identical* impression counts every single week
and the same average position as the homepage. That is the fingerprint of
sitelinks appearing underneath our brand result, not of pages earning their own
searches.

The second: one content page on the site genuinely is indexed, ranks at
position 5, and grew its impressions sevenfold. Tempting to call that the
sitemap working. It is not. Its growth starts more than two weeks *before* we
submitted anything.

So: **adding more pages to treesmith.app is not a strategy, and we are writing
that down so it stops resurfacing.** Overall the site went from 6 organic clicks
to 4 across the two periods, on nearly triple the impressions, essentially all
of them for people searching our own name.

We are also being careful about what this does *not* kill. One page there proves
a page there can rank. The visible difference is that its title is written like
something a person would search for, while the four dead ones are titled
"Features", "Journal", "Press" and "Grafting Techniques". That is a sample of
one, so it is logged as a hunch rather than acted on. As it happens we shipped a
change today that rewrites the homepage title on exactly that theory, so
everything measured above is now its before-picture.

**The lesson:** a pre-registered kill date is only worth having if you also
refuse the consolation prize.
