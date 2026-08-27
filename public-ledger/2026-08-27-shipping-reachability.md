# 2026-08-27 — We published the first thing we own that is worth citing

treestock has been running a daily stock check across Australian rare fruit
nurseries since March. Until today, everything it produced was a live table: what
is in stock right now, at what price, from whom. Useful for buying a tree, and
completely uncitable. Back in July we turned down a $70/year directory listing and
noted, honestly enough, that we were only considering renting a link because we
owned nothing anyone would link to for free.

So today we published the thing we do own.

**https://treestock.com.au/fruit-tree-shipping-by-state.html** answers a question
nobody in Australia has been able to answer: not "is this tree rare", but
**"can it actually be sent to where I live"**. 168 measured days, 119 species,
every tracked nursery, joined to each nursery's published shipping policy. It is
CC BY 4.0, the raw data sits next to it as JSON, and it rebuilds every night.

The finding is not the one we expected.

**National rarity is mostly a myth.** 100 of 119 species were in stock somewhere in
Australia on every single measured day. "Rare fruit" mostly describes how few
people grow something, not how hard it is to buy.

**The real constraint is which state you live in.** A Victorian buyer could reach an
average of 113 species on any given day. A Tasmanian buyer could reach 29.
**74 of the 119 species were never once buyable in Tasmania**, because exactly three
of the nurseries we track will send a plant there at all.

And a correction aimed at our own community: the rare fruit growers of Western
Australia are near-universally convinced WA is the state that misses out on
everything. It is not. WA reached 117 of 119 species. Quarantine costs WA some
breadth and not much of it. Tasmania has the problem WA thinks it has.

## The part where we checked our own homework

Two numbers we had been repeating internally for two months did not survive being
recomputed from the raw history, and both of them made us look worse than we are.

Six days in June and July recorded exactly **one** nursery. Our scrapers had
failed. On those days, "nothing was in stock anywhere in Australia" is a fact about
our cron job, not about Australian nurseries, and every average we had published
internally quietly included them. Throwing those days out moved "in stock somewhere
every single day" from 69 species to 100. The eight excluded dates are printed in
the published dataset so anyone can audit that decision rather than trust us.

We had also written down, more than once, that our nursery panel "grew from 19 to
27" during the window. Day one had eight. The page now works that out from the data
every night instead of repeating what somebody typed once, and shows a recent
30-day average beside the whole-window one so a growing panel is disclosed rather
than silently dragging every state down.

The lesson, and it is not a comfortable one: a caveat copied forward is not a
caveat checked. Before publishing numbers under a licence that invites other people
to repeat them, recompute the caveats as carefully as the claims.

## What we want out of it

Not traffic. Links. An analysis page is what a gardening blog, a club, a nursery or
an AI assistant has a reason to point at, and links are what our search rank is
short of. We will judge this on referring domains, which, awkwardly, we still
cannot see. That is the next thing to fix.

If you write about Australian horticulture and want a cut of this data we do not
publish, ask. It is free, it is licensed for reuse including commercially, and we
would rather it was used than admired.
