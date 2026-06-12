# Variety descriptions tail pass: apple finished (15 added, 18 skipped, 0 remaining)

**Decided by:** Dale (parallel variety-descriptions run, window: apple)

**Context:** Apple was reported remaining=0 in the 2026-06-08 batch (DEC-180..191), but live stock
moves: the step-1 rank script showed 33 live apple variety slugs with no entry and no skip record,
a mix of newly listed heritage and cider apples, alternate-spelling slugs for already-researched
cultivars, and multi-graft parse artifacts.

**Decision:** Run one tail pass on the apple file per docs/variety-descriptions-rollout.md.
Researched 13 candidates via 3 parallel subagents (2+ sources each, 1 spot-checked source per
agent), adapted 3 entries for duplicate-spelling slugs of already-verified cultivars
(apple-ballerina-bolero, apple-ballerina-flamenco, apple-cider-improved-foxwhelp), and skipped 18
slugs (16 multi-graft / "way" / pollinating-duo parse artifacts plus apple-cactus-pink noise, and
apple-lovejoy-s-lunch which has no findable reputable sources).

**Why:** Accuracy over coverage. The 12 researched additions (Kingston Black, Yarlington Mill,
Cimetiere de Blangy, Verite, Ballerina Polka, Ballerina Waltz, Crofton Red, Beauty of Bath,
Braeburn, Grimes Golden, James Grieve, Worcester Pearmain) are all multi-source verified; one
unsupported claim (a Robert Hogg attribution on Kingston Black) was dropped at spot-check, and the
Polka/Waltz entries were re-grounded on Pomiferous (Trajan/Telamon) after the first drafts leaned
on nursery copy.

**Actions:** tools/scrapers/variety_descriptions/apple.json now has 85 varieties + 98 skipped;
full test suite green (1537 tests, golden unchanged since no fixture entry was modified). Shipped
as PR on branch dale/varieties-apple.

**Status:** Apple remaining = 0 (tick at close-out). Deploy is the serialized close-out step.

**To revert:** git revert the PR merge commit; the blurb layer falls back gracefully per slug.
