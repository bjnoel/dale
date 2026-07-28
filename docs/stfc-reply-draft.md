# Draft reply to Sheryl (STFC)

**Status:** draft for Benedict to review and send. Dale wrote it; Benedict sends
it from his own address in his own words.

**Context:** she asked whether Benedict has built other sites like the one he is
proposing. The plan is `docs/stfc-rebuild-plan.md`. Do not send this before
checking the preview yourself.

**Preview URL:** <https://stfc-preview.pages.dev>

---

Subject: Re: the website, and something to look at

Hi Sheryl,

Fair question, and rather than send you a list of links I thought it would be
more useful to just build you a piece of it.

Have a look at this on your phone: **https://stfc-preview.pages.dev**

That is your content, not a mockup. I pulled all 473 entries across from the
current site, so what you are looking at is the actual Articles, Tips, Recipes
and pest pages, just rebuilt. There are two versions to compare, and a switch at
the top of every page to flip between them.

Two things in there I would particularly like your opinion on.

The first is the library page. At the moment /articles is about 500 blue links
with nothing to tell them apart, so you can only find something if you already
know its name. On the preview you can type "fruit fly" or "grafting" and get
answers as you type, or tap a topic to narrow it down. That is the single
biggest change, and it is why I wanted you to see it with real content rather
than a demo.

The second is the thing you mentioned about the next-article links. You were
right, and it is worse than you described. On the current site, Air Layering /
Marcotting is followed by "Visiting Nguon & Han Kov". That is not anyone's
fault, it is just WordPress ordering by the order things were added. On the
preview, the bottom of that article gives you Grafting Tips, Mango Propagation,
and Propagating Fruit Trees from Seed instead.

A couple of other things I found while I was in there, none of them urgent:
your articles have no dates, no author names and no tags on them at all, so I
have generated summaries and topic tags. They are plain text you can correct.
About 140 of your URLs have a stray "-2" on the end from an old import, and
around 23 articles are quietly published twice under two different sections.
Air Layering is actually one of them, which is why it turns up twice with two
different "next article" links. All of that is fixable without breaking a single
existing link.

As for other work of mine, the closest thing is **treestock.com.au**, which I
built and run. It is about 3,000 pages tracking fruit tree stock across 27
Australian nurseries, with search, filters, per-state growing guides and proper
sources on everything. It is a much better comparison than my other sites,
because it has the same problem yours does: a lot of content that is worthless
unless people can find the bit they want.

You may also know **rfcarchives.org.au**. I took that on to keep the Rare Fruit
Council's back catalogue online. It is a plain archive rather than a piece of
design work, but it is probably the more relevant thing, in that a club trusted
me with their content and it is still there.

So, two questions when you have a minute:

1. **Version A or version B?** A is warmer and more club-like, B is quieter and
   more like a reference book. Either works, I would just rather build the one
   you actually like.
2. **Do Articles and Tips need to stay separate?** You have 261 Articles and 175
   Tips and I honestly cannot tell what decides which is which. Happy either
   way, it just changes how the menu works.

No rush on any of this.

Benedict

---

## Notes for Benedict (do not send)

- Every number above is checked: 473 entries, 261 Articles, 175 Tips, 142 `-2`
  URLs (120 of them cleanable to a bare slug), 23 duplicates, 27 nurseries,
  ~3,000 treestock pages (3,178 today).
- The prev/next example is real, and it is on
  `/articles/air-layering-marcotting-2/`, which is the copy you reach from the
  Articles list. The other copy of the same article, at
  `/about/air-layering-marcotting/`, gives you "Membership" and "Mango - Drying"
  instead. Both verified on the live site today. If she checks the /about/ one
  and sees different links, that is the duplication point, not a mistake.
- Deliberately **not** leading with bjnoel.com or treesmith.app. They are
  brochure sites and undersell you to someone worried about a 500 article
  library.
- rfcarchives is framed as standing, not as design work, because it is a static
  1980s-2002 newsletter archive last touched in 2013.
- No mention of price, the retainer or the trade terms. This email's only job is
  to answer the portfolio question and get an A/B answer. Terms come after she
  says she likes one.
- The preview is `noindex` and has a `robots.txt` disallow, so it cannot compete
  with stfc.org.au in search.
