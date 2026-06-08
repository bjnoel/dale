# Variety descriptions rollout runbook

Runbook for continuing the treestock variety-descriptions rollout (DEC-178): add verified
"what's unique about this variety" blurbs to more `/variety/<slug>.html` pages, in batches,
never re-doing a variety, ticking off as you go. **Accuracy over coverage is the rule.**

Invoke one batch with the `/variety-rollout` slash command, or paste this file's steps. It is
**idempotent**: every run recomputes the remaining list from on-disk state, so subagents never
overlap and nothing is redone. Run it again (ideally in a fresh context) to continue.

See also: `memory/project_variety_descriptions.md` (the pattern + gotchas) and
`memory/reference_treestock_rebuild_no_emails.md` (deploy).

## What "done" means (the two ledgers)
- **Success ledger:** a variety with a committed entry in `tools/scrapers/variety_descriptions/*.json`.
- **Skip ledger:** `tools/scrapers/variety_skiplist.json` (a JSON array of slugs that were
  researched but could not clear the >=2-source bar; create as `[]` if missing).
- `REMAINING = live fruit variety slugs (ranked) - success ledger - skip ledger`.

## 0. Orient
- `cat memory/project_variety_descriptions.md` (authoritative: pattern, gate, gotchas)
- Skim the schema/house style: `tools/scrapers/variety_descriptions/apple.json`
- Skim the guards `tests/test_variety_descriptions.py` and the loader
  `tools/scrapers/stocklib/variety_descriptions.py`

## 1. Build the REMAINING work-list
Get live, correctly-spelled fruit slugs from the SERVER (so blurbs key to real built pages).
Write this to a temp file and run `ssh dale-server 'cd /opt/dale/scrapers && python3 -' < /tmp/rank.py`:

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
    if slugify(d["species"]) not in VALID:        # fruit species only (anti-noise)
        continue
    ns = len({p["nursery_key"] for p in d["products"]})
    ins = sum(1 for p in d["products"] if p["available"] and p["price"])
    rows.append((ns, ins, slug, d["species"], d["variety"]))
rows.sort(reverse=True)                            # widely-stocked first = more value + better docs
for ns, ins, slug, sp, var in rows:
    print(f"{slug}|{sp}|{var}|{ns}|{ins}")
```

Then locally: subtract every slug already in `tools/scrapers/variety_descriptions/*.json` and
every slug in `tools/scrapers/variety_skiplist.json`. Drop semantic mis-parses where the
"species" is really another fruit or noise (e.g. `lemon-drop-mangosteen`, `jaboticaba-leaf`,
multigraft combos); when unsure, keep it. Take the top ~50 remaining for THIS run.

## 2. Fan out NON-OVERLAPPING research subagents
Split the ~50 into ~7 disjoint slices, grouped BY SPECIES where possible (so an agent reuses
sources). Launch them in parallel in ONE message (general-purpose subagents, multiple Agent
calls). Each agent gets ONLY its slice (`slug | species | variety` lines) plus this contract:

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
> polyembryonic). NOT generic growing advice. Do not invent specific numbers (brix, chill
> hours, height, yield) unless an authoritative source gives them. NO em dashes or en dashes
> (use commas, periods, parentheses); Australian spelling. Use the EXACT slug/species/variety
> given; slug must equal slugify("species-variety"). Output ONLY a single JSON object, no prose,
> no fences:
> `{"entries": {"<slug>": {"slug","species","variety","paragraphs":["...","..."],"claims":[{"text","type","cites":["<source-id>"]}],"sources":[{"id","name","url":"https://...","tier":"authoritative|owned|third_party|nursery"}],"confidence":"high|medium","confidence_score":0.80-1.0,"verified":true,"generated_date":"<today>"}}, "skipped":[{"slug","reason"}]}`
> Auto-checked: >=2 sources, >=1 non-nursery source, every claim.cites id resolves to a source,
> no orphan sources, 1-2 paragraphs, no dashes. (Mirror the existing apple.json Pink Lady entry.)

## 3. Assemble + tick off
- Merge returned entries into `tools/scrapers/variety_descriptions/<species-slug>.json`
  (`{species_slug, schema_version:1, varieties:{...sorted by slug}}`). Force rfcarchives.org.au
  sources to tier "owned". Spot-check ~1 cited source per agent (use Chrome if a .gov page 403s).
- Append every skip returned (and any you reject on review) to
  `tools/scrapers/variety_skiplist.json` so they are never retried.

## 4. Validate
- `python3 -m unittest discover tests/` must be green. Typical fixes: a slug whose species
  isn't in fruit_species.json (drop it), a non-https or nursery-only source, or a dropped cite.
- If any touched variety is in the golden fixture: review the diff, then
  `GOLDEN_UPDATE=1 python3 -m unittest tests.test_golden.GoldenTest.test_variety`.

## 5. Deploy + verify (NEVER run-all-scrapers.sh)
```
ssh dale-server 'cd /opt/dale/repo && git pull --ff-only && bash tools/deploy.sh && cd /opt/dale/scrapers && DALE_DATA_DIR=/opt/dale/data python3 build_variety_pages.py /opt/dale/data/nursery-stock /opt/dale/dashboard && bash purge_cloudflare.sh'
```
Then confirm `grep -rl variety-about /opt/dale/dashboard/variety/ | wc -l` rose by ~the batch
size, and spot-check one new live page.

## 6. Commit + report the tally
Commit and push to main (branch first if on main, then fast-forward). Print: "Done this run:
N. Total committed: X. Skipped cumulative: S. Remaining fruit varieties: R." and update the
coverage line in `memory/project_variety_descriptions.md`.

## Guardrails
- Skipping is success; never publish a guess. Clean prose on-page; sources stored, not rendered.
- Safe to re-run in a fresh context: it always recomputes REMAINING from disk, so subagents
  never overlap and nothing is redone.

## Running it unattended (read before /loop or /schedule)
- **`/loop /variety-rollout` does NOT clear context between iterations.** It re-runs in the
  same conversation; context accumulates and only auto-compacts (lossily) when full. Progress
  stays correct (state is on disk), but it gets token-heavy. For a clean fresh context per
  batch, either `/clear` then `/variety-rollout` manually each time, or use `/schedule` (each
  scheduled run is a fresh agent).
- **Auto-publishing tradeoff:** as written, each batch commits to main and deploys, so it goes
  live with only the automated gate (>=2 sources, tests, skip-if-thin) as the safeguard, no
  per-batch human review. That matches the trust-critical design, but if you want a human gate,
  run interactively, or change step 6 to push a branch + open a PR per batch instead of pushing
  to main (note: committed JSON on main also goes live via the nightly rebuild within ~24h).
