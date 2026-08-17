# 2026-08-17: An hour at Guildford Garden Centre, and the bug the owner found for us

Track B. The first in-person nursery visit of the goodwill outreach programme, and the
first time someone outside the project has looked at one of our pages and told us it was
wrong.

## The visit

Benedict went to Guildford Garden Centre on Monday 2026-08-17 and spent about an hour with
Emma. No pitch, nothing commercial, nothing asked for. That was the plan and it held.

The sequence that got us there is worth stating plainly, because it took four and a half
months. Touch 1 went out 2026-03-30 and got no reply. It turned out not to have been
ignored: when touch 2 landed on 2026-08-10, Emma replied within three days saying the first
email had simply been buried, apologised for it, and offered to meet in person. She named
the quiet window herself, Mondays before 2.30pm, because August is peak bare root and they
are bagging a couple of thousand trees.

She now knows who Benedict is, and she likes the idea of the site. That was the entire
objective.

## What she told us that we could not have found by scraping

**Most bare root stock is spoken for before the public sees it.** Guildford orders bare root
in around June. It goes first to a pre-registration list. Anything not collected within two
weeks is released to the general public, and whatever still does not sell gets potted up and
sold on as potted stock. Where pre-order demand is strong they try to order well above it,
but supply does not always allow.

The important detail is what this looks like from outside. Those lines *are* on their
website. They simply never show as anything but out of stock, because they are pre-sold
before the public listing ever means anything.

That is the opposite of a blind spot. We hold 161 Guildford bare root lines, 102 of them
out of stock, and they are exactly the ones collectors chase: Cox's Orange Pippin, Angelina
Burdett, Coe's Golden Drop, Nijisseiki, the Minnie Royal / Royal Crimson cherry multigrafts.
Every one has a variety page carrying a notify-me.

So a collector who wants an Angelina Burdett has two independent places to wait: Guildford's
own registration list, and ours. Neither depends on the other, and ours works across every
nursery we track rather than one. Being a second notification surface for stock a nursery
cannot list as available is a genuinely useful thing to be, and it is the obvious thing to
offer nurseries commercially later.

**Some absences are decisions, not stock-outs.** They deliberately do not import certain
deciduous stock that is too susceptible to pests. Shot hole borer is the live problem in
Perth. It does not generally affect fruit trees, but it does affect much of the deciduous
range they would otherwise bring in. A variety missing from Guildford is sometimes a
biosecurity judgement rather than a sold-out line.

**Their stock levels are deliberately accurate.** Emma was clear that an online-versus-shop
mismatch causes real problems when the last plant sells twice. That makes Guildford's
availability data high quality, which is useful to know about a dataset we depend on.

**She may be able to give us the stock listings directly**, instead of us scraping. Format
and cadence are not yet specified. That is now the open follow-up.

What we will not be asking for is the registration list itself. It is a spreadsheet with
thousands of rows and it is not going to be shared, which is fine: the demand signal we
actually need is the one our own notify-me captures generate.

## The part where she found our bug

Emma's first substantive comment on the site was that our page for her nursery was a bit
weird: the "In Stock Now" panel was showing seeds. It was.

```
 1 Watermelon - Sugar Baby - Eden Seeds
 2 Watermellon - Warpaint - Eden Seeds
 3 Silverbeet - Ruby Red Chard - Eden Seeds
 4 Pea - Greenfeast (Lincoln) - Eden Seeds
 5 Cauliflower - All Year Round - Eden Seeds
 6 Carrot - Baby (Amsterdam) - Eden Seeds
 7 Lettuce - Salad Bowl Red - Eden Seeds
 8 Blueberry - Premier
 9 Cabbage - Red Acre - Eden Seeds
...
20 Kohl Rabi - Purple Vienna - Eden Seeds
```

Nineteen of twenty slots were vegetable seed packets on a fruit tree site.

The cause was a single missing filter. Ten places on the site run products through a
"is this actually a plant we track" check before displaying them. The nursery profile page
was the only builder that never did. That stayed invisible until Guildford loaded an Eden
Seeds vegetable range into their store in August, and because the store returns newest
products first, the new seed packets took every slot at the top.

The headline numbers on the page were wrong the same way, since they came from the
pre-filter totals. Same snapshot, before and after the fix:

| | In Stock | Products Tracked | Top of the list |
|---|---|---|---|
| Before | 278 | 924 | Watermelon - Sugar Baby - Eden Seeds |
| After | 225 | 859 | Blueberry - Premier |

Across all 27 nurseries the fix removes 607 non-plant products, 331 of them in stock, from
the nursery profile pages. Guildford was by far the worst affected; the next worst had five
of twenty slots.

Fixed, tested with a new regression test built on the real 2026-08-17 ordering, and
deployed. Full detail in DEC-301.

## The uncomfortable bit

We emailed Emma twice asking her to look at her page. She came back warm, invited us in,
and the page we had pointed her at was listing cabbage seeds. The outreach worked and then
handed the relationship a defect to survive.

She was amused rather than annoyed, and it cost nothing. But the lesson is not about seeds.
It is that we had no test on that page, no golden coverage for it, and no reason to look at
it, so the only quality check that ran was a nursery owner opening her own listing. That is
not a control we can rely on twenty-six more times.

## Next

Reply to Emma, thank her for the hour, and take up the stock feed offer: what format they
can export and how often it refreshes.

Worth telling her, too, that we already carry her out-of-stock bare root lines with a
notify-me on each. Her pre-registration list is not the only place a collector can put their
hand up, and a nursery having a second queue it does not have to run itself is the beginning
of the commercial conversation rather than a favour we are asking for.
