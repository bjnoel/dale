# Ticket format: the decision card

Benedict triages Linear on his phone. A ticket description exists so he can
answer **yes / no / later**, and nothing else. Everything that supports that
decision goes in the research comment.

## The format

```
<One sentence: what you will actually do.>

**Why now:** <the single strongest number or fact, 1-2 sentences>

**Cost:** <$ and time> · <Dale autonomous | Benedict must: X>

`L2 · treesmith_downloads`
```

Target 60 to 80 words. **Hard cap 100, enforced by `linear_update.py create`,
which exits 4. There is no override flag.**

The final backticked line carries the thinking level (L0 tactical to L3
strategic) and the metric the ticket expects to move. Do **not** open the
description with `Level 2 (Channel). Expected metric: ...` prose. That was the
old habit, and it spent the first line of every ticket, the only line visible
on a phone list view, on metadata.

## The trailer is parsed (since 2026-08-06)

This used to read "nothing parses it; it is there so Benedict can see the
altitude at a glance". That was true and it was the problem: Dale declared an
intended outcome on roughly sixty tickets and was never graded against one, so
"done" was the last word on every piece of work.

`tools/autonomous/ticket_outcomes.py` now reads it. When a ticket is completed
it stamps the named metric's current value; 28 days later it re-reads the
metric and posts the before/after as a comment on the ticket, and in the daily
digest. So:

- **Prefer a metric the registry can read.** As of 2026-08-06:
  `treestock_organic_visitors`, `treesmith_downloads`, `revenue_monthly`,
  `treestock_subscribers`, `treestock_subscriber_engagement`. Adding one is a
  single entry in `METRIC_READERS`.
- **Prose trailers are still legal.** `nursery relationships`, `protects every
  other metric` and `unblocks DEC-248 step 3` are all real, and all describe
  work whose value is not a number. Those tickets are reported as "shipped
  without a readable metric" rather than being forced into a false measurement.
  Use one when it is honest, not to duck a verdict.
- **Name the metric you actually believe will move.** A scraper refactor
  claiming `revenue_monthly` will be graded on revenue and will read as a
  failure, which is the correct outcome for an inflated claim.

The verdict is deliberately worded as correlation, not attribution: other work
ships inside the same 28 days and nursery traffic is seasonal. It says what
happened, not what caused it. The value is in having the question asked at all.

## Where the thinking goes

```bash
python3 linear_update.py create "Title" \
  --description "$(cat <<'EOF'
...the card...
EOF
)" \
  --research "$(cat <<'EOF'
...evidence, workings, rejected alternatives, prior tickets, how to verify...
EOF
)" \
  --labels "Track A" --priority 3
```

`--research` is posted as the first comment, one scroll below the description.
Be as thorough there as the work deserves. The point is not to think less. It
is to put the thinking where it costs nothing to skip.

## Rules of thumb

- One number beats three. Pick the one that would change his mind.
- If a sentence would not turn a yes into a no, it is research, not description.
- Do not restate the title.
- Name the blocker explicitly when there is one. "Blocked on X" is worth more
  than a paragraph of context.
- Never split one idea across several tickets to duck the cap.

## Why this exists

Measured 2026-08-03: 48 open tickets held **14,112 words**, about **64 minutes**
of reading to triage the backlog. Benedict: *"it's taking me longer to read
tickets than come up with tasks myself."*

The cause was not the model freelancing. `session-prompt.py` asked every ticket
to state its thinking level, its expected metric, and why it would move that
metric, and Opus 5 (switched on 2026-07-30, commit 6f1b1cd) complied more
thoroughly than its predecessor. Median description went from ~95 words to ~320
overnight, with the longest hand-written one at 705.

So the fix has three parts, and the prompt alone was never going to be enough:

1. The prompt asks for a card and shows the `--research` heredoc.
2. `linear_update.py` enforces the cap in code, the same lesson as the
   duplicate guard (DEC-236): prompt text is not an enforcement mechanism.
3. `gsc_page_review.py`, which pasted 4,000 characters into `--description`
   every fortnight, builds a card and sends the brief to `--research`.

The 48 existing tickets were migrated on 2026-08-03: each original description
was posted verbatim as a **Research backing** comment first, then the
description was replaced with its card. Backlog went from 14,112 words to
3,051, roughly 64 minutes to 14. Nothing was deleted.
