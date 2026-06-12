# Variety descriptions: lemon tail + citron (18 added, 22 skipped, both species complete)

**Decided by:** Dale (parallel variety-rollout run, window lemon-citron)

**Context:** The DEC-178 pilot seeded 10 lemon variety blurbs; the lemon long tail (33 live
slugs) and the whole citron species (7 live slugs) had none. Per the rollout runbook
(`docs/variety-descriptions-rollout.md`), this window owned lemon.json and created citron.json
in a worktree on `dale/varieties-lemon-citron`.

**Decision:** Add 18 verified entries (13 lemon, 5 citron) researched by parallel subagents
against 2+ reputable sources each (UC Riverside CVC, UF/IFAS, Auscitrus, Wikipedia, Specialty
Produce, PlantNet), and record 22 skips in the per-species `skipped` ledgers: 2 thin-source
research skips (Thornless, Limoncello had only recycled nursery copy) and 20 review rejects
(herbs, ornamentals, multigraft products, and junk product-title parses that are not lemon or
citron cultivars).

**Why:** Accuracy over coverage. Spelling-variant slugs of solid cultivars (Myer, Eureka
Variegated, Buddha and Buddha's Hand variants) each got an entry because each is its own live
page; parse noise (Lemon Balm, Lemon Verbena, Lemon Aspen, Lemon Ironbark, a coleus, a rubber
plant, a daylily) was skipped so the ledger stops re-attempting it.

**Actions:** lemon.json now 23 varieties + 20 skipped; citron.json new with 5 varieties + 2
skipped. Tests green (1537). No golden regen (neither species is a fixture species).

**Status:** PR open; remaining = 0 for both species (mark lemon and citron DONE at close-out).

**To revert:** revert the PR merge commit; delete citron.json and restore lemon.json.
