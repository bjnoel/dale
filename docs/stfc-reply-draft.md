# Draft reply to Sheryl (STFC)

**Status:** draft for Benedict to review and send, from his own address.

**Context:** she asked whether Benedict has built other sites like the one he is
proposing. Plan: `docs/stfc-rebuild-plan.md`. Decision: DEC-234.

**Preview URL:** <https://stfc-preview.pages.dev>

---

Subject: Re: the website

Hi Sheryl,

Rather than send you a list of links, I built you a piece of it. Worth opening on
your phone:

**https://stfc-preview.pages.dev**

That is your content, not a mockup. All 473 entries from the current site,
rebuilt. There are two versions, with a switch at the top of every page to flip
between them.

Two things worth your attention.

The library page. At the moment /articles is around 500 blue links with nothing
to tell them apart, so you can only find something if you already know its name.
On the preview you type "fruit fly" or "grafting" and get answers as you type.

And the thing you raised about the next-article links. You were right, and it is
worse than you said. Air Layering / Marcotting is currently followed by "Visiting
Nguon & Han Kov". That is not anyone's fault, it is just WordPress ordering by
when things were added. The preview gives you Grafting Tips and Mango
Propagation instead.

The closest thing to this that I have built is treestock.com.au, which I run.
About 3,000 pages tracking fruit tree stock across 27 Australian nurseries, with
search, filters and per-state growing guides. Same problem as yours: a lot of
good content that is worthless unless people can find the bit they want. You may
also know rfcarchives.org.au, which I took on to keep the Rare Fruit Council's
back catalogue online.

Two questions when you have a minute:

1. **A or B?** I lean towards B, the quieter one. Your real strength is 500
   articles of actual growing knowledge, and B makes that the easiest to read.
   Happy to build A if the committee prefers it.
2. **Do Articles and Tips need to stay separate?** You have 261 and 175, and I
   cannot work out what decides which is which.

No rush on any of it.

Benedict

PS. A few things I noticed while I was in there, none of them urgent. Your
articles have no dates, authors or tags at all. About 140 URLs have a stray "-2"
on the end from an old import. And 23 articles are quietly published twice under
two different sections, Air Layering being one of them, which is why it turns up
with two different "next article" links. All fixable without breaking a single
existing link.

---

## Notes for Benedict (do not send)

- **Steer to B is in there** (question 1), phrased as a lean rather than a
  verdict, and it gives the committee an easy out if they disagree. The preview
  itself is neutral: A is listed first and neither is marked recommended.
- Numbers are all checked: 473 entries, 261 Articles, 175 Tips, 142 `-2` URLs
  (120 cleanable to a bare slug), 23 duplicates, 27 nurseries, ~3,000 treestock
  pages (3,178 today).
- The prev/next example is on `/articles/air-layering-marcotting-2/`, the copy
  you reach from the Articles list. The other copy, `/about/air-layering-marcotting/`,
  gives "Membership" and "Mango - Drying". If she checks that one and sees
  different links, that is the duplication point, not a mistake.
- Deliberately **not** leading with bjnoel.com or treesmith.app. Brochure sites,
  and they undersell you to someone worried about a 500 article library.
- rfcarchives is one clause, framed as standing rather than design work. It is a
  static 1980s-2002 newsletter archive last touched in 2013.
- No price, no retainer, no trade terms. This email's only job is to answer the
  portfolio question and get an A/B answer. Terms come after she likes one.
- The preview is `noindex` with a robots.txt disallow, so it cannot compete with
  stfc.org.au in search.
- 2026-07-28: stfc.org.au was briefly unreachable. Not us. The harvest made 9
  requests in total, rate limited to one a second, and the site answers normally
  from Benedict's connection.
