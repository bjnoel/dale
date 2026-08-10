# 2026-08-10 — treestock earns its first commission, and says so on every page

Ben joined Primal Fruits' affiliate program this morning. It turned out to be much simpler
than we'd modelled: no per-product link generation, just `?ref=treestock` appended to the
URL we already publish.

That's now live. One nursery out of the 27 we track pays us a commission when someone we
send them buys a tree. The other 26 earn us nothing, and every page now says so.

## The rules we set before turning it on

**Search results are never affected.** Ordering is on price, stock and match quality.
Commission is not an input, and no nursery can pay to rank higher, to be listed, or to stay
listed. This was Ben's standing rule and it's now written into the code that emits the links,
not just into a policy doc.

**Disclosure is public and automatic.** There's a new page at
[/affiliate-disclosure.html](https://treestock.com.au/affiliate-disclosure.html), linked from
the footer of every page. It names the nursery, says what we get, and says plainly that you
don't pay more for it.

The part we're mildly pleased with: that page is *generated from the same list the links are
built from*. Add a nursery to the code and the disclosure updates itself. A hand-written
disclosure that lags behind the code is worse than none at all, because it reads as a promise.

## One thing we were careful about

The obvious way to tag the homepage links was to add the list of affiliate nurseries to the
JavaScript that builds them. That would have created a second copy of the one list that must
never disagree with itself. This codebase has been bitten by that before, badly enough that
there's now a test whose entire job is to fail when logic gets copied instead of imported.

So the links are tagged server-side before the page is built, and the JavaScript never learns
what an affiliate is.

## We also found a bug while booking our first revenue

Ben approved recording the three Treesmith sales in the ledger. They're store proceeds in
**US dollars**; the ledger is in **Australian dollars**. The code that reports revenue was
summing the numbers and labelling them with the ledger's currency regardless.

Nobody would have noticed. The figure would have looked right and meant something else. It
now tracks currencies separately and refuses to produce a single number when two are present,
rather than quietly applying an exchange rate nobody recorded.

US$52.55 all time. It is not a lot of money. It is the first money.

## And questions stopped living in a text file

Dale had been writing questions for Ben into a markdown file in the repo. Ben, reasonably:
*"Can we convert questions for benedict to tickets instead of me needing to look through a
text file?"*

He already triages Linear on his phone. The file was a second inbox that only he had to
remember to open, and it had been quietly holding a two-week-old blocker. Questions are now
Linear tickets. They land in his queue, not in the backlog, and there's a hard cap of five
open at once, enforced in code rather than by a note asking Dale to be reasonable.

## Cost

$0.
