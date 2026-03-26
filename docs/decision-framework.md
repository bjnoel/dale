# Decision Framework

## Before Every Decision

1. **What problem does this solve?** If you can't state it in one sentence, think harder.
2. **What's the smallest test?** Never go big first. Find the cheapest way to validate.
3. **Is this reversible?** Reversible decisions can be made fast. Irreversible ones need more thought.
4. **What does failure look like?** Define the kill criteria upfront.
5. **Does this pass the ethics charter?** Front-page test.

## Decision Sizing

| Size | Process | Example |
|------|---------|---------|
| Trivial | Just do it, log after | Which CSS framework to use |
| Small | Log before, execute | Build a scraper for nursery X |
| Medium | Write proposal, get Benedict's input | Set pricing at $199 |
| Large | Full decision doc, joint approval | Pivot a track |

## Kill Criteria

Every experiment gets a kill condition:
- **Time-boxed:** "If we don't have X by [date], we stop."
- **Metric-based:** "If conversion rate is below X%, we pivot."
- **Cost-based:** "If this costs more than $X with no return, tell him he's dreaming."

## Strategic Reflection (Step-Back Protocol)

The autonomous pipeline detects when work in a category has stopped moving the needle
and forces Dale to step back and think broader before continuing.

### The Thinking Ladder

| Level | Question | Example |
|-------|----------|---------|
| 3 - Strategic | "Should I work on a different track entirely?" | Track B growth vs Track A revenue |
| 2 - Channel | "Should I try a different approach within this track?" | SEO vs social media for treestock |
| 1 - Approach | "Should I try a different tactic within this approach?" | Different subscriber conversion method |
| 0 - Tactical | "Should I tweak this specific thing?" | CTA button text |

When work at Level 0 stops moving metrics, step up to Level 1. When Level 1 is stale, step
up to Level 2. And so on.

### How it works

- `state/focus-tracker.json` tracks what categories Dale works on each session and metric snapshots
- `session-prompt.py` reads the tracker and computes whether any category is "stale" (3+ of the
  last 5 session-days with no meaningful metric movement)
- If stale, a reflection prompt is injected requiring Dale to justify continued work or switch
- **Revenue alarm:** if revenue is $0 after 14+ days of operation, every session gets a Level 3
  prompt requiring at least one revenue-directed ticket

### Benedict override

Set the `override` field in `state/focus-tracker.json` to exempt a category:

```json
"override": {
  "category": "treestock:seo",
  "reason": "Google indexing just started, push for 2 more weeks",
  "set_by": "benedict",
  "set_date": "2026-03-27",
  "expires": "2026-04-10"
}
```

The override expires automatically. Set to `null` to clear.

### Kill criteria (enhanced)

Every experiment now requires BOTH:
1. A kill condition (existing): "If X doesn't happen by Y, stop"
2. A metric gate: "The metric I expect to move is Z" (must be a metric tracked in focus-tracker.json)

### Step-back decision logging

When the reflection system triggers and Dale changes course:

```
## DEC-NNN -- YYYY-MM-DD -- Strategic Reflection: Step-back from [category]
**Triggered by:** Automatic (Level X reflection)
**Category:** [category key]
**Metric stagnation:** [metric]: [start] -> [current] (no movement)
**Reflection:** [Dale's analysis of why]
**Decision:** [What Dale will do instead]
**Status:** REFLECTED
```

## Logging Format

```
## DEC-NNN -- YYYY-MM-DD -- Title
**Decided by:** Dale / Benedict / Joint
**Decision:** What we decided
**Rationale:** Why
**Alternatives rejected:** What else we considered (optional)
**Kill criteria:** When do we stop (for experiments)
**Status:** PROPOSED / APPROVED / EXECUTED / KILLED
```
