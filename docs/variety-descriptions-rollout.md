# Variety descriptions rollout runbook (parallel, worktree-based)

Plan for adding verified "what's unique about this variety" blurbs to treestock
`/variety/<slug>.html` pages, **one species (or small species-set) per Claude Code window**,
many windows at once. Modelled on `docs/species-guide-rollout.md`: each window works in its own
git worktree on its own branch, touches only files unique to its assignment, writes shared-file
edits as uniquely-named fragments, and opens a PR. A serialized close-out folds the fragments,
ticks progress, and deploys once. **Accuracy over coverage is the rule.**

See also `memory/project_variety_descriptions.md` (the content layer + gotchas) and
`memory/reference_treestock_rebuild_no_emails.md` (deploy).

## How concurrency stays collision-free (mimics the species rollout)
- **Unit of work = a whole species.** Each window owns one or more species; all of a species'
  varieties live in its own `tools/scrapers/variety_descriptions/<species>.json`. Two windows
  working different species never touch the same file, so branches merge cleanly.
- **Two on-disk ledgers, both per-species (no shared mutable file):**
  - successes -> the `varieties` map in `<species>.json`
  - thin-source skips -> an optional top-level `"skipped": ["<slug>", ...]` array in the SAME
    `<species>.json` (so a re-run of that species never re-attempts them).
  - `REMAINING(species) = live variety slugs of that species (ranked) - varieties - skipped`.
- **No shared-file edits in a branch** (these are the merge-conflict points): do NOT edit
  `decisions/decision-log.md`, the shared daily `public-ledger/<date>.md`, or the Progress list
  in this doc. Use uniquely-named fragments (step 5). Deploy and progress-ticking are close-out.
- **Assignment is human-driven** (like substituting `SPECIES =` per window): you open N windows
  and give each a different species/set. Pick in the priority order below.

## The prompt (substitute the assignment line per window)

```text
ASSIGNMENT = mango          # one species, or a comma-separated disjoint set e.g. apple,pear
LABEL      = mango          # short unique tag for this window's branch/worktree/fragments

You are adding verified "what's unique about this variety" blurbs to the treestock /variety
pages for the species in ASSIGNMENT, shipping via PR. Accuracy is paramount: a fabricated
cultivar fact is worse than no blurb.

## 0. Start from origin/main in your OWN worktree (do this FIRST)
The variety-descriptions infra (stocklib/variety_descriptions.py, the variety_descriptions/
dir, build_variety_pages.py slot, tests/test_variety_descriptions.py) is MERGED to origin/main;
the local main may be stale. Create and work inside a worktree off origin/main:
  git -C /Users/bjnoel/Projects/dale fetch origin
  git -C /Users/bjnoel/Projects/dale worktree add ../dale-varieties-{{LABEL}} -b dale/varieties-{{LABEL}} origin/main
  cd /Users/bjnoel/Projects/dale/../dale-varieties-{{LABEL}}
Sanity check: `tools/scrapers/variety_descriptions/apple.json` MUST exist here. If not, you are
not on origin/main; fix that before continuing.
Orient: read `memory/project_variety_descriptions.md`; skim `variety_descriptions/apple.json`
(schema/house style), `stocklib/variety_descriptions.py`, and `tests/test_variety_descriptions.py`.

## 1. Build REMAINING for your assigned species (idempotent tick-off)
Get live, correctly-spelled fruit slugs from the SERVER (so blurbs key to real built pages).
Write to /tmp/rank.py and run `ssh dale-server 'cd /opt/dale/scrapers && python3 -' < /tmp/rank.py`:
  ```python
  import json, importlib.util
  from pathlib import Path
  spec = importlib.util.spec_from_file_location("bvp", "build_variety_pages.py")
  m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
  from cultivar_parsing import slugify
  VALID = {s["slug"] for s in json.load(open("fruit_species.json")) if s.get("slug")}
  g = m.group_by_cultivar(m.load_all_products(Path("/opt/dale/data/nursery-stock")))
  rows = []
  for slug, d in g.items():
      if slugify(d["species"]) not in VALID:
          continue
      ns = len({p["nursery_key"] for p in d["products"]})
      ins = sum(1 for p in d["products"] if p["available"] and p["price"])
      rows.append((slugify(d["species"]), ns, ins, slug, d["species"], d["variety"]))
  rows.sort(key=lambda r: (r[0], -r[1], -r[2]))
  for sp, ns, ins, slug, species, var in rows:
      print(f"{sp}|{slug}|{species}|{var}|{ns}|{ins}")
  ```
Keep only rows whose species slug is in ASSIGNMENT. For each, subtract slugs already in that
species' `varieties` map and its `skipped` array. That set, ranked by nursery_count then
in_stock, is REMAINING. Drop semantic mis-parses (a "species" that is really another fruit, or
noise); when unsure keep it. Cap this run at ~50 varieties; if a big species has more, note it
(re-run the same species later to continue, it is collision-free because you own the file).

## 2. Fan out NON-OVERLAPPING research subagents
Split REMAINING into disjoint slices of ~7 (group by species). Launch them in parallel in ONE
message (general-purpose subagents, multiple Agent calls). Each agent gets ONLY its slice
(`slug | species | variety` lines) plus this contract:

> Research Australian fruit-tree varieties for treestock.com.au. For each assigned variety,
> write a SHORT, FACTUAL "what's unique" blurb verified against multiple reputable sources, in
> strict JSON. Accuracy is paramount: when fewer than 2 reputable sources exist, SKIP it (never
> guess). Per variety: web-search; open/fetch 2+ reputable sources and confirm the facts appear
> there. Prefer authoritative (.gov.au, .edu, UC Riverside Citrus Variety Collection, UF/IFAS,
> AgriFutures, the RFCA archive at rfcarchives.org.au -> tier "owned"), then third_party
> (Wikipedia, Orange Pippin, California Rare Fruit Growers), then nursery (Daleys etc. =
> grounding only, never the sole non-nursery source). State a fact only if 2+ independent
> sources, or 1 authoritative source, confirm it. Write 1-2 paragraphs (each under ~650 chars)
> on what is DISTINCTIVE: origin/breeding, flavour/texture, ripening season, appearance, uses,
> and notable quirks (self-fertile vs needs a pollinator, low-chill, seedless, dwarf,
> polyembryonic). NOT generic growing advice. Do not invent specific numbers (brix, chill hours,
> height, yield) unless an authoritative source gives them. NO em or en dashes (commas, periods,
> parentheses); Australian spelling. Use the EXACT slug/species/variety given; slug must equal
> slugify("species-variety"). Output ONLY a single JSON object, no prose, no fences:
> {"entries": {"<slug>": {"slug","species","variety","paragraphs":["...","..."],"claims":[{"text","type","cites":["<source-id>"]}],"sources":[{"id","name","url":"https://...","tier":"authoritative|owned|third_party|nursery"}],"confidence":"high|medium","confidence_score":0.80-1.0,"verified":true,"generated_date":"<today>"}}, "skipped":[{"slug","reason"}]}
> Auto-checked: >=2 sources, >=1 non-nursery, every claim.cites id resolves, no orphan sources,
> 1-2 paragraphs, no dashes. Mirror the existing apple.json Pink Lady entry.

## 3. Assemble into your species files (ONLY your assigned species)
For each assigned species, update `tools/scrapers/variety_descriptions/<species>.json`
(`{species_slug, schema_version:1, varieties:{...sorted}, skipped:[...sorted]}`):
- merge returned entries into `varieties`; force rfcarchives.org.au sources to tier "owned".
- append every skip (returned, or one you reject on review) to that file's `skipped` array.
- Spot-check ~1 cited source per agent (use Chrome if a .gov page 403s the fetcher).

## 4. Validate
- `python3 -m unittest discover tests/` green. Typical fixes: a slug whose species isn't in
  fruit_species.json (drop it), a non-https or nursery-only source, a dropped cite.
- Golden: only these fixture species change golden output: apple, avocado, banana, black-sapote,
  fig, longan, lychee, mango. If your assignment includes one, review the diff then
  `GOLDEN_UPDATE=1 python3 -m unittest tests.test_golden.GoldenTest.test_variety`. (Only YOUR
  species' golden pages actually change, so branches for different species merge cleanly.)

## 5. Ship as a PR with uniquely-named fragments (do NOT merge, deploy, or tick progress)
You are in the dale/varieties-{{LABEL}} worktree. Commit, push, open a PR. In your branch:
- Decision: write ONE fragment `decisions/pending/{{DATE}}-varieties-{{LABEL}}.md` (a `# title`
  line then the body; see `decisions/pending/README.md`). Do NOT edit decision-log.md or pick a
  DEC number.
- Public ledger: write `public-ledger/{{DATE}}-varieties-{{LABEL}}.md`, NOT the shared daily file.
- Do NOT tick the Progress list in this doc; do NOT run any builder/deploy. These uniquely-named
  artifacts let any number of variety branches merge cleanly.

## 6. Report what you researched (always end with this)
Print, and put in the PR body, a per-species report:
  Researched this run (branch dale/varieties-{{LABEL}}):
    <species>: N added, M skipped, R remaining
      added:   <slug> - <one-line what's-unique>   (one per added variety)
      skipped: <slug> - <reason>                    (one per skipped variety)
  Totals: X added, S skipped, R remaining across ASSIGNMENT.
Mark a species DONE (for the Progress list at close-out) when its remaining is 0.
```

## Close-out (ONE serialized step, after the batch of PRs has merged)
Run once for the whole batch (Benedict, or a single coordinating session):
- `python3 tools/fold_pending_decisions.py` folds `decisions/pending/*.md` into the log with
  fresh sequential DEC numbers and deletes the fragments (`--dry-run` to preview).
- Tick the Progress list below for species whose remaining is now 0.
- Deploy once (NEVER run-all-scrapers.sh):
  `ssh dale-server 'cd /opt/dale/repo && git pull --ff-only && bash tools/deploy.sh && cd /opt/dale/scrapers && DALE_DATA_DIR=/opt/dale/data python3 build_variety_pages.py /opt/dale/data/nursery-stock /opt/dale/dashboard && bash purge_cloudflare.sh'`
  then confirm `grep -rl variety-about /opt/dale/dashboard/variety/ | wc -l` rose and spot-check a page.
- Remove merged worktrees: `git worktree remove ../dale-varieties-<label>` per window.

## Progress (species claim board)
Assign UN-done / under-done species to windows in priority order; tick at close-out when a
species' remaining hits 0. Pilot batch (DEC-178) seeded these 24 species with their top varieties
(most still have a tail to finish): apple, apricot, avocado, banana, black-sapote, cherry, fig,
finger-lime, grapefruit, jujube, lemon, lime, longan, lychee, mandarin, mango, mulberry,
nectarine, olive, orange, peach, pear, plum, pomegranate. The remaining fruit species in
`fruit_species.json` have no variety blurbs yet. Run the step-1 rank script for live per-species
remaining counts to decide assignments (biggest catalogues: mango, apple, orange, plum, peach,
avocado, cherry, fig, pear, grape, mandarin, nectarine).

- [ ] (assign species to windows and tick here as each completes)

## Notes / guardrails
- Skipping is success; never publish a guess. Clean prose on-page; sources stored, not rendered.
- One window per species at a time (the file owner). Different windows take different species.
- A species file may end up with `varieties: {}` and a long `skipped` list (all its live
  varieties were too obscure to verify) - that is a valid, complete result.
- For a SOLO window with no other windows running, you may skip the PR and instead fast-forward
  main + run the close-out yourself.
