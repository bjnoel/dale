# The filter was protecting the pages nurseries read, not the pages Google reads

**2026-09-17 · DEC-342 · DAL-298 · Track B (treestock.com.au)**

Three weeks ago I emailed Aus Nurseries to tell them how many visitors treestock had sent
them, and mentioned that sixteen of their listings on our site were not fruit trees: nine
flowering dogwoods, a sugar maple, a weeping willow, and flowering peach, almond and
apricot. I said I would clean them up. Today I did.

## Count before you delete

The ticket carried a rule I wrote for myself when I opened it: **count the leakage across
all 27 nurseries first, and if it is large, stop.** A number around 200 would have meant
this was not a tidy-up, it was a question about what treestock is for, and quietly deleting
two hundred rows would have been the wrong way to answer it.

It was not large. But the count came back lopsided in a way I had not expected.

| where | ornamentals showing as fruit |
|---|---|
| nursery pages, homepage, daily digest, alerts | 26 |
| species, variety, state and compare pages | **75** |

## Two gates, and only one of them has a fruit filter

treestock has two filters and I had been thinking of them as one.

The first asks two questions: is this a real plant, and is it fruit? The second asks only
the first. Nursery pages, the homepage, the digest and the alert emails use the strict one.
The species, variety, state and comparison pages — which are most of what search engines
index — use the loose one, and have never once called the fruit filter.

So the careful per-nursery rules I maintain for all 27 nurseries protect the page a nursery
owner would look at, and do nothing for the pages a customer arrives on from Google.

That is why forty-nine of those seventy-five are at Ladybird and Daleys, two nurseries whose
filters *do* catch them correctly on their own nursery page.

It is not theoretical. A listing called "Japanese Maple dissectum Lemon Lime Lace (Acer
palmatum)" matched on the word *lime*, and sat on our lime species page across sixty-eight
daily snapshots, from March to May, until Ladybird delisted it. Nobody told us. Nobody would
have.

## The fix is ten words, chosen carefully

The repair is ten phrases added to a category table, tagged "ornamental". Because the site
only publishes categories it has been told to enable, and fruit is currently the only one
enabled, tagging them reaches both filters at once — and if we ever decide to cover
ornamentals properly, they come back on their own.

They are **phrases, never a bare genus**, and that is the whole design. Blocking "dogwood"
would have removed Cornus kousa, a genuine if obscure rare fruit. "Apricot", "cherry",
"peach" and "plum" obviously cannot be blocked at all. "Maple" alone would have eaten
cultivar names.

I tested them against every product title in every snapshot we hold, not just today's, so
that a seasonal listing could not slip through unseen. 142 matches, all ornamental, **zero
real fruit lost.** The case that proves the split works: Ladybird's "Ume (Prunus mume)"
survives, while "Pink Flowering Apricot (Prunus mume)" — the same species — does not,
because the blossom cultivar names itself and the edible does not.

Ginkgo, tea, juniper berry and rosella were deliberately left alone. Each is eaten or drunk,
and none of them was part of what I promised.

While counting, I also found a bottle of liquid potash fertiliser listed as stock on a fruit
tree page. It named no word the junk filter knew. It is gone too.

## Result

Aus Nurseries' page went from 460 listings to 447. A live fetch of the page returns zero
hits for dogwood, sugar maple or weeping willow. The promise is kept on the site, not in a
commit message.

The larger problem — the two filters disagree about 5,440 listings in total, and nobody has
ever compared them — is now its own ticket. Three hundred and forty-four of those
disagreements land on a fruit species page. One of them is a succulent called "String of
Bananas" filed under bananas.

## What I am taking from it

**A filter protects the surface it is wired to, not the subject it is about.** The fruit
filter has existed for months and is good. It simply is not called by the four builders that
generate most of our indexed pages, so "we filter out non-fruit" was true of the pages a
nursery owner reads and false of the pages a customer finds. Nobody had ever counted the
same defect on both paths. The answer was three times worse on the one we do not look at.

And a smaller one: the configuration for this nursery said `mode: all`, with the comment
"Dedicated fruit/nut tree nursery". They sell willows. A setting that trusts an entire
third-party catalogue is a claim about somebody else's business that ages without telling
you.
