# Draft reply to Sheryl (STFC)

**Status:** draft for Benedict to review and send, from his own address.

**Context:** she asked whether Benedict has built other sites like the one he is
proposing. Plan: `docs/stfc-rebuild-plan.md`. Decision: DEC-234.

**Read this first.** Sheryl is not the one who needs convincing. She transferred
rfcarchives.org.au to Benedict, transferred WANATCA to him (he rewrote it in Hugo
and scanned the paper copies), and has said she likes treestock. She knows the
work. The portfolio question is her needing something to put in front of the STFC
committee. So this email does not pitch her. It hands her ammunition and offers
to write the committee paper.

**Preview URL:** <https://stfc-preview.pages.dev>

---

Subject: Re: the website

Hi Sheryl,

You already know my work better than most, and you handed me the RFCA and WANATCA
archives yourself, so I will not recite it all back at you. I am guessing the
harder job is giving the committee something solid enough to say yes to.

So here is that. Worth opening on your phone:

**https://stfc-preview.pages.dev**

It is STFC's own content, not a mockup. All 473 entries from the current site,
rebuilt, with two versions and a switch at the top of every page to flip between
them.

I built the two pages that carry the arguments a committee will want to hear.

**The library.** At the moment /articles is around 500 blue links with nothing to
tell them apart, so you can only find something if you already know its name. On
the preview you type "fruit fly" or "grafting" and get answers as you type.

**The next-article links you mentioned.** You were right, and it is worse than
you said. Air Layering / Marcotting is currently followed by "Visiting Nguon &
Han Kov", because WordPress just orders things by when they were added. The
preview gives you Grafting Tips and Mango Propagation instead.

**And the thing committees actually worry about: nothing breaks.** I have
generated 162 redirects, so every existing link and bookmark still works. Same as
when the 1,800 pages of RFCA moved across and nothing went missing.

Two questions for you:

1. **A or B?** I lean towards B, the quieter one. The club's real strength is 500
   articles of actual growing knowledge, and B makes that the easiest to read.
   Happy to build A if the committee prefers it.
2. **Do Articles and Tips need to stay separate?** There are 261 and 175, and I
   cannot work out what decides which is which.

And if it would help, say the word and I will write you a one-pager you can put
straight in front of the committee.

Benedict

PS. A few things I noticed while I was in there, none of them urgent. The
articles have no dates, authors or tags at all. About 140 URLs have a stray "-2"
on the end from an old import. And 23 articles are quietly published twice under
two different sections, Air Layering being one of them, which is why it turns up
with two different "next article" links.

---

## Notes for Benedict (do not send)

- **The framing changed** once you said she already knows treestock and
  transferred you RFCA and WANATCA. The earlier draft pitched her a portfolio,
  which would have read as not listening. This one assumes she is sold and needs
  committee ammunition instead.
- **The one-pager offer is the most useful sentence in the email.** Someone
  trying to move a committee wants a document, not a link. Say the word and I
  will draft it: what it costs, what changes, what breaks (nothing), who
  maintains it, and what the committee actually has to decide.
- **Not mentioned deliberately:** price, the retainer, trade terms. If the
  2026-07-23 terms email has not gone yet, the one-pager is the natural place for
  them, where the committee can read them properly.
- **Also not mentioned:** the RFCWA photo competition voting app
  (`rfcwa-photo-comp.pages.dev`). It is a good third proof point, bespoke club
  tooling on free hosting, but the email is already doing enough. Worth adding to
  the committee one-pager.
- **Careful with WANATCA phrasing** if the committee digs: it was founded by your
  father, and Sheryl transferred it to you. "I run it" is accurate. Anything that
  sounds like a competitive client win is not.
- Numbers all checked: 473 entries, 261 Articles, 175 Tips, 142 `-2` URLs (120
  cleanable to a bare slug), 23 duplicates, 162 redirects, RFCA 1,789 URLs live.
- The prev/next example is on `/articles/air-layering-marcotting-2/`, the copy you
  reach from the Articles list. The other copy, `/about/air-layering-marcotting/`,
  gives "Membership" and "Mango - Drying". If she checks that one and sees
  different links, that is the duplication point, not a mistake.
- The preview is `noindex` with a robots.txt disallow, so it cannot compete with
  stfc.org.au in search.
- 2026-07-28: stfc.org.au was briefly unreachable. Not us. The harvest made 9
  requests in total, rate limited to one a second, and the site answers normally
  from your connection with no VPN.
