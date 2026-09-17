# South Australia is live, the ACT is not, and the reason is the same measurement

**2026-09-17 · treestock.com.au · DEC-338 / DAL-297**

South Australia now has its own fruit tree buy pages on treestock: twenty species pages
plus `/buy-fruit-trees-sa.html`, covering 1,390 in-stock products from the 14 of our 27
nurseries that ship there.

That gap had been open a while. SA has more reachable stock than Western Australia (2,012
listings from 14 nurseries against WA's 1,351 from 9) and it had zero pages to WA's 75. It
was never excluded on merit. It was simply never added to the config.

## The ticket said one config line. It was not one config line.

The ticket that asked for this work costed it at "one config line plus a golden review",
and asked for the ACT in the same pass on the grounds that it is served by the eastern
states shippers and costs nothing extra.

Two of its three premises turned out to be wrong. Both were caught by measuring rather
than by reading.

### The ACT would have been forty-nine copies of New South Wales

Before building anything, we compared what each state can actually reach. The ACT's set of
reachable listings overlaps NSW's by **95.8%**. It differs by exactly one nursery. **Thirty-five
of the forty-nine ACT pages would have carried a product list byte-identical to the live NSW
page**, and with no ACT-specific growing content written, the rest of the page would have been
the NSW page with the state name swapped.

So the ACT is dropped, and the measurement is written into the code beside the state list so
nobody re-proposes it from the same reasoning six months from now.

South Australia passed the same test, which is why it went ahead. Only two of its forty-six
candidate pages match any other state. It reaches a nursery nobody else does and misses seven
that serve Victoria. It is genuinely different stock.

### A condition that had only ever seen one answer

Our combo pages are capped at twenty per state, to stop a long tail of thin pages. There is
an exemption: a species with a growing guide gets a page regardless of where it ranks on
stock, because we measured guided pages ranking far better than guideless ones.

The exemption asked "does this species have a guide?" For four states, that was the same
question as "does this page have anything state specific on it?", because every guide covered
exactly those four states. South Australia separated the two on its first night: **all
fifty-five guides answer "yes, there is a guide" and "no, there is no South Australian
section".** The exemption would have let twenty-six SA pages through the cap on the strength
of a measurement taken on pages that carry a state-specific body those twenty-six would not
have had.

So the exemption now asks the question it always meant: does this page have a section written
for this state? South Australia launches at twenty pages and earns the rest as the content is
written, rather than arriving all at once on borrowed evidence.

### Adding a state used to be nine edits

The four states were typed out in nine places across four builders and the tests. Miss the
sweeper's filename pattern and new pages build and are never retired. Miss the sitemap and
they ship unlisted. Miss the cross-links and nothing on the site links to them. All of it now
comes from one list in one file, with the patterns and the cross-links computed rather than
typed. New tests fail if a copy comes back, and fail if a state is added without the copy
every page needs.

Those tests immediately found two defects already live. One of our state pages has been
serving the sentence "Finding fruit trees online that ship to WA is surprisingly hard most
nurseries are east coast only" since someone deleted a dash without rewriting the sentence
around it. Four others still carried em dashes we do not use. Both fixed.

## The lesson

**A condition that has only ever been evaluated on one population is not a condition, it is
a coincidence.** "Has a guide" and "has something written for this state" returned the same
answer for every page we had ever built, because in that population the two facts were
perfectly correlated. They were never the same question, and the version that would have
shipped was defensible: a real measurement, on a real metric, for the right reason.

When you extend a system to a new case, re-ask what each of its conditions was actually
testing. Not whether it still runs.

And the cheapest place to find a duplicate content problem is before you build the pages.
Probing the ACT against NSW took one script and one afternoon, and killed forty-nine pages
that would otherwise have needed discovering in Search Console months later.
