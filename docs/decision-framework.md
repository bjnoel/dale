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
