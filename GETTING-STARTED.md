# Getting Started

## Step 1: Create the GitHub Repo

```bash
mkdir dale && cd dale
git init
# Copy all these files into the repo
git add .
git commit -m "Dale v2: dual-track framework with market research"
gh repo create dale --private --source=. --push
```

## Step 2: First Claude Code Session

```bash
cd dale
claude
```

### First prompt:

```
Read CLAUDE.md first. Then run the orient protocol — read all state files:
state/business-state.json, state/active-sprint.md, decisions/decision-log.md,
financials/ledger.json, state/questions-for-benedict.md.

Then read docs/business-plan.md for full context on both tracks.

This is your first working session as Dale. Pick the highest-impact tasks
from the active sprint and start executing. Focus on things you can build
without waiting for my answers to the questions — I'll answer those async.
```

## Step 3: Ongoing Workflow

After each session:
1. Answer questions in `state/questions-for-benedict.md` (mark [ANSWERED])
2. `git add . && git commit -m "Session N: [brief summary]" && git push`
3. Next session: `claude` → "Continue where you left off"

## Step 4: Question Dashboard (coming soon)

Dale will build a simple web page where you can see and answer pending
questions from your phone. Until then, edit the markdown file directly
(GitHub mobile app works for this).

## Tips

- **Git commit after every session** — this is Dale's long-term memory
- **Answer [BLOCKING] questions first** — these stop progress
- **Short answers are fine** — "yes", "option b", "the one on King St"
- **Trust but verify** — review anything customer-facing before it goes out
- **The public ledger is the record** — keep it honest, even when things go wrong
