# Species registry expansion (2026-10-18)

Approved by Benedict in chat, 2026-10-18. No Linear ticket: the backlog was full
(15/15) and this is approved work, not a proposal.

## Why

A local embedding-classifier test (BGE + logistic regression) over all 14,926 live
titles found that 6,904 (46%) match no species. Most are Ladybird ornamentals and
correctly unmatched, but the pile also holds:

- rare fruit stocked by 4-8 nurseries with **no registry record** (Ice Cream Bean,
  Star Gooseberry, Jostaberry, Yuzu, Santol, Durian, Chempedak...);
- rule-matcher bugs: a trailing `™`/`®` stops a match (`Angel Peach™` unmatched,
  `Angel Peach` -> peach), and first-fruit-word wins (`Dwarf Satsuma Plum` ->
  mandarin, `Pineapple Orange Tree` -> pineapple, `Banana Passionfruit` -> banana).

## Units (in order)

1. **™/® fix** in `stocklib/species_match.py` + regression test.
2. **First-fruit-word fixes**: Satsuma Plum, Pineapple Orange, Banana Passionfruit,
   Banana Ken Mango, via longer synonyms (longest leading match already wins).
3. **Citrus** (Benedict: yes): Yuzu (*Citrus junos*) and Sudachi (*Citrus sudachi*)
   get own records; Chinotto -> orange synonym with `synonym_latin` *Citrus
   myrtifolia*; Lemonade -> lemon synonym.
4. **New species records**: real fruit/nut stocked by >= 4 nurseries, plus Carob
   (Benedict: include). Herbs/spices stay out (DEC-195 gate).
5. **Multi-graft secondary listing** (Benedict: multi-grafts only, NOT hybrids):
   a product naming 2+ species joined by `+`, `&`, `/`, "and" or "Multi Graft"
   keeps its primary species (variety slug, watches, alerts unchanged) and is
   listed in a **separate, lower section** on the other species' pages.
   Hybrids (`x`, Peacharine, Plumcot) stay single-species.
   Guard: never split inside quotes (`Guava 'Red Cherry/Strawberry'`,
   `Plum Combo - 'Santa Rosa' & 'Satsuma'`).

## Done means

- Each unit's before/after impact diff (species + variety slug over all live
  titles) reviewed; **no watched variety slug orphaned** (206 watched slugs).
- Regression tests for each bug; `python3 -m unittest discover tests/` passes;
  golden diffs reviewed before `GOLDEN_UPDATE=1`.
- Decision log entry.
