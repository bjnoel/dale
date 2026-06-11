# Variety descriptions tail pass: jujube, olive, pomegranate complete (19 added, 22 skipped)

**Decided by:** Dale (parallel variety-rollout window, branch dale/varieties-jop)
**Context:** The 2026-06-08 pilot batch (DEC-178, DEC-180..191) seeded jujube, olive and
pomegranate with their top varieties but left a long tail of live slugs without blurbs.
This window ran the rollout runbook (docs/variety-descriptions-rollout.md) for the
assignment jujube,olive,pomegranate to finish all three species.
**Decision:** Research every remaining live variety slug for the three species with
parallel subagents (2+ reputable sources each, at least 1 non-nursery, skip when thin),
and ship the verified entries plus an exhaustive per-species skipped list so REMAINING
hits 0 for all three.
**Why:** Variety pages are treestock's highest-intent SEO surface; verified blurbs make
them unique. An exhaustive skipped ledger means future passes never re-attempt noise
slugs (misspellings, pot-size parse artefacts) or thin-source obscurities.
**Actions:** Added 19 entries (jujube 7: Li 2, Sherwood, Suiman, Suimen, SiHong,
Tiger Tooth, Russia 2; olive 6: Kolossus Kalamata, Arecuzzo, UC13, Helena, Saint Helena,
New Norcia Mission; pomegranate 6: Nana, Gulosha Azerbaijani, Velles, Griffith,
Griffith Red, Griffiths Red). Recorded 22 new skips (7 jujube, 8 olive, 7 pomegranate),
mostly misspellings of already-covered cultivars and nursery-only dwarf selections
(Garden Harvest, Bambalina, Miniolea) plus unverifiable names (Daganzao, Millstone,
Cypress Hill, Shepherd's Special with nursery-only sources). Notable saves on review:
the Griffith pomegranate was initially skipped by research but is documented in the
RFCA Loxton/Medina trial archive (owned source); the Arecuzzo olive citation was
repointed from a dead AgriFutures PDF URL to the verified RIRDC 03-021 publication page
plus full-text PDF, and its unsupported anthracnose claim dropped. All 1546 tests green;
no golden fixture species touched.
**Status:** Shipped as PR from dale/varieties-jop; deploy happens at the serialized
close-out. Jujube, olive and pomegranate all report remaining = 0 (DONE for the
Progress list).
**To revert:** Revert the PR merge commit; the three species files return to their
pilot-batch state.
