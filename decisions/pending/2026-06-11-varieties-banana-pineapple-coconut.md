# Variety blurbs: banana tail + pineapple + coconut

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-banana-pineapple-coconut)
**Context:** Continuing the `/variety-rollout` (DEC-178 layer) for three tropical species. Banana
had its top varieties seeded in the pilot but a long tail of Cavendish, plantain, and Pacific
cooking-banana listings was uncovered; pineapple and coconut had no variety files at all.
**Decision:** Added 12 verified "what's unique" blurbs across banana (8), pineapple (1), and
coconut (3), and recorded 20 thin/duplicate skips in the per-species `skipped` arrays.

Banana added: william, super-dwarf-cavendish, dwarf-ducasse, french-plantain, saba, pacific,
tonga, dpm-25. Pineapple added: f180. Coconut added: yellow, green, malay-red.

**Why:** Banana/pineapple/coconut are common nursery stock; accurate blurbs help collectors tell
near-identical listings apart (e.g. Williams vs Dwarf Cavendish, Ducasse sugar banana vs plantain,
the Malayan Dwarf colour forms). Most skips are mangled product-title duplicates of a cultivar
already covered, or trade names with no reputable non-nursery source.
**Actions:** Wrote `variety_descriptions/{banana,pineapple,coconut}.json`. All facts verified
against >=2 reputable sources (ABGC, ProMusa, QLD DPI/NT field-screening literature, RFCA archive
[owned], Wikipedia, Specialty Produce); nursery pages used as grounding only. Full test suite green
(1546 tests). Banana golden unchanged (new varieties are outside the golden fixture set).
**Status:** Shipped via PR; not deployed (close-out deploys the batch).
**To revert:** Drop the three files' new entries; the renderer falls back to no blurb.
