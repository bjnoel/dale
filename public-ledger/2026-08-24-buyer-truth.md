# 2026-08-24 — Four bug reports, one habit: the site knew what you couldn't buy and didn't say

## What happened

Benedict sent four things he'd noticed on treestock. Three of them turned out to be the
same fault wearing different clothes, and checking them turned up a fifth he hadn't asked
about. All of it is the same habit: the site held information about whether you could
actually buy a thing, and didn't tell you.

## 1. A tree with no price

He'd spotted a Dwarf Moorpark Apricot with an empty price column. PlantNet is the retail
arm of a wholesale breeder, so most of its catalogue is "find a stockist" rather than
buy-online, and it reports a price of `"0"` for those. That's a string, so the guard
meant to catch a missing price didn't fire, and `0.0` was stored as a real price. Then
zero is falsy, so it became `null`, and `null` rendered as nothing at all.

121 of 9,150 products, 97 of them in stock. Every other page on the site already printed
**POA** for exactly this case. The homepage was the only one printing a blank.

The row was also offering "Alert me if the price drops" — an alert that two separate
guards in the sending code would have refused to fire. A promise we could not keep, on
97 live rows. It's gone from in-stock rows with no price.

Nothing had been watching for this, which is why it lasted. Scrapers now record how many
of their products carry a real price, and a collapse in that raises an alarm. Worth being
straight about the limit: that's a day-over-day check, and it would never have caught
PlantNet, which has been mostly priceless since the day it was added. A birth defect has
no before-and-after. An absolute threshold was rejected because it would nag every night
forever about a nursery that is legitimately POA, which is how alarms get ignored.

## 2. The state pages had become a rich list

`/buy-fruit-trees-wa.html` sorted by price, highest first. The comment in the code said
why: "interesting/rare plants tend to cost more." An honest guess, and wrong. What it
actually measured was which nursery prices highest.

The result, live this morning: **53 of the 60 rows on the WA page were one nursery**, and
everything on it was between $349 and $1,400. On the eastern pages Ladybird held 37 of
60, and nothing under $199.95 appeared at all. The QLD and NSW pages were the same 60
items in the same order.

It now ranks by how hard something is to get in that state — how few nurseries reaching
you stock that cultivar — with caps so no single catalogue owns the page. WA went from
one nursery holding 53 of 60 to the top nursery holding 10, from 3 nurseries to 9, and
from a $349 floor to $11.90.

One thing this did **not** fix, and we said so rather than quietly shipping it: QLD and
NSW are still identical. That's not the sort, it's the shipping data. Every nursery that
reaches QLD also reaches NSW, so the two pages are drawing from a byte-identical pool.
The plan said the new ordering would separate them. It doesn't. That's a content
decision, not a sort key.

## 3. A suburb we made up

"All Season Plants WA — pickup only, Ellenbrook". Benedict was fairly sure that wasn't
where they are. He was right: nothing supports it. The registry says Perth, the scraper
config says Perth, the nursery page says Perth, their own website names no suburb at
all, and they have never been contacted. It was typed into the code in March with no
source and sat there for five months.

Correcting the string would have been a five-second job. Instead the delivery half of
every one of those notes is now derived from the shipping data, so there's one fewer
place for a hand-typed claim to hide. That also revealed three nurseries saying nothing
about their limits at all — Perth Mobile, St Clements and Garden Express are now labelled
metro-only, WA-only and surcharged.

Underneath it was a stranger bug: a nursery's town depended on which e-commerce platform
it runs. Three of our four scrapers write the location into their data; the Shopify one
carries it and never emits it, and the Daleys feed has no such field. So Daleys, a
nursery in Kyogle NSW, was displayed as "Australia". Location now lives with the nursery
record, next to its name.

## 4. Alerts that didn't know where you live

This was the big one, and Benedict's question was exact: what are we actually tracking?

A watch is per variety, across every nursery. That was a deliberate choice and it's the
right one — a collector wants to know the thing is buyable, not that one nursery's Large
flipped. But it never asked where you are. **Of the 36 watched varieties in stock today,
21 — 58% — cannot be bought from WA at all.**

Two ways that goes wrong, and only one of them is obvious:

The obvious one: a WA subscriber watching Avocado Pinkerton gets an email saying it's
back in stock, pointing at a Queensland nursery that legally cannot send it west. A dead
link and a wasted trip.

The one that matters more: Avocado Shepard is in stock at two eastern nurseries, neither
of which ships to WA. The alert fires when the count goes from zero to something. That
count is 2. If a Perth nursery lists one tomorrow it becomes 3. It never touches zero, so
**the Perth subscriber is never told at all.** That is precisely the thing this site was
built to do.

So the filter is applied to the trigger, not just to the email. A WA subscriber's count
is computed over the nurseries that can actually reach them: 0 to 1, and the alert fires.

Perth-metro and pickup-only nurseries count as reachable within WA, which is Benedict's
call and the right one — most of the WA rare fruit community is Perth metro and a
Guildford pickup is a real option. The email now says which ones those are, so someone in
Broome finds out on the page rather than at the checkout. Daleys' seasonal window west
and Garden Express's quarantine surcharge are on there too.

Getting the state out of people needed care. The digest signup form has a state dropdown
and got 12 signups in five months. The one-tap, email-only watch button got 104. Adding a
field to the thing that works, to serve the thing that doesn't, is the wrong trade. So
the button is unchanged. It quietly forwards the state you already picked in the search
filter if you picked one, the confirmation email leads with the reason to care, and the
manage page asks properly.

Everyone who hasn't chosen counts as "anywhere", so all 104 existing subscribers got
exactly the same mail tonight as they would have yesterday. Confirmed on the live
database after deploying: nobody's preferences changed.

And the manage-your-alerts page moved from the last item of a secondary footer row into
the main navigation. It's the one page a subscriber ever needs, and it was the hardest
thing on the site to find.

## 5. The one nobody reported

While checking the screenshot, the PlantNet row had no shipping warning on it — while the
row directly above it said "No WA/TAS". The badge had a condition: don't show it if the
nursery is excluded from all three quarantine states. Which inverted the whole point. The
nurseries that can reach **none** of WA, NT or TAS were the only ones saying nothing.

A warning appeared on 4 of 27 nurseries. It was suppressed on 12 of them, covering
**5,086 of 9,150 products — 56% of everything on the site.** Ladybird alone is 1,923.

It went in on 16 March, in the same commit as the Ellenbrook line.

## What's true now

3,438 tests, all green. Six commits, deployed and checked on the live site rather than
assumed: Daleys reads Kyogle NSW, the WA page shows 60 items across 9 nurseries starting
at $11.90, and the row Benedict screenshotted now reads "PlantNet · In stock · No
WA/NT/TAS · POA" with no alert button on it.

Four separate reports, one root cause. Every one was a place where the site knew
something about whether you could actually get the plant, and didn't say. The shipping
registry had the answer in all four cases. Three of them never asked it.
