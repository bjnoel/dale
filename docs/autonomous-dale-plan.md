# Autonomous Dale — Architecture Plan

**Decision:** DEC-027 (to be logged)
**Date:** 2026-03-09
**Status:** PLANNED — build next session

## Overview

Dale runs autonomously on the Hetzner VPS via cron, performing business tasks
overnight while Benedict sleeps. All spending requires Benedict's email approval.
Token usage is tracked and budgeted to never compete with Benedict's interactive use.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Hetzner VPS (178.104.20.9)                              │
│                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────┐ │
│  │ dale-runner.sh│───▶│ claude -p    │───▶│ budget-    │ │
│  │ (cron wrapper)│    │ (headless)   │    │ tracker.py │ │
│  └──────┬───────┘    └──────┬───────┘    └────────────┘ │
│         │                   │                            │
│  ┌──────▼───────┐    ┌──────▼───────┐                   │
│  │ TASK_QUEUE.md │    │ token-log.   │                   │
│  │ (what to do)  │    │ json (usage) │                   │
│  └──────────────┘    └──────────────┘                   │
│         │                                                │
│  ┌──────▼───────┐    ┌──────────────┐                   │
│  │ notify.py    │───▶│ Resend API   │──▶ b@bjnoel.com  │
│  │ (email)      │    └──────────────┘                   │
│  └──────────────┘                                        │
│                                                          │
│  ┌──────────────┐                                        │
│  │ STOP         │ ◀── Benedict creates this to halt all  │
│  └──────────────┘                                        │
└─────────────────────────────────────────────────────────┘
```

## Directory Structure

```
/opt/dale/autonomous/
├── dale-runner.sh          # Cron wrapper — the main entry point
├── budget-tracker.py       # Token usage tracking + budget enforcement
├── notify.py               # Email notifications via Resend
├── session-prompt.py       # Builds the prompt for each autonomous run
├── config.json             # Budget limits, schedule config
├── TASK_QUEUE.md           # What Dale should work on (editable by Dale or Benedict)
├── STOP                    # Create this file to halt all autonomous runs
├── logs/
│   ├── token-log.json      # Append-only token usage history
│   ├── session-YYYY-MM-DD.json  # Full output from each run
│   └── errors.log          # Failures and circuit breaker events
└── approvals/
    ├── pending/             # Spending requests awaiting approval
    └── approved/            # Approved spending (Benedict moves files here)
```

## Cron Schedule

```
# Existing: scrapers at 6am UTC (2pm AWST)
0 6 * * * /opt/dale/scrapers/run-all-scrapers.sh >> /opt/dale/data/scraper.log 2>&1

# NEW: Dale autonomous run at 18:00 UTC (2am AWST)
0 18 * * * /opt/dale/autonomous/dale-runner.sh >> /opt/dale/autonomous/logs/cron.log 2>&1
```

**Why 2am AWST:**
- Maximum distance from Benedict's work hours (8:30-17:30 AWST)
- 5-hour rolling window resets well before morning
- Scrapers run at 2pm AWST — data is fresh for Dale's analysis
- Even if Dale uses significant tokens, 10+ hours buffer before Benedict needs them

## Token Budget Framework

### Max $100 Plan Limits
- Uses a 5-hour rolling window for rate limiting
- Exact token limits TBD — we'll learn empirically from first runs
- No per-session budget cap in Claude Code, so we build our own

### Budget Strategy

```json
{
  "max_daily_token_budget": null,
  "max_session_duration_minutes": 30,
  "learning_mode": true,
  "learning_mode_note": "First 2 weeks: run with 15-min cap, log everything, establish baseline",
  "graduated_limits": {
    "week_1_2": {"max_minutes": 15, "note": "Learn token consumption patterns"},
    "week_3_4": {"max_minutes": 20, "note": "Increase if no contention observed"},
    "week_5_plus": {"max_minutes": 30, "note": "Full autonomy if budget allows"}
  }
}
```

### Pre-run checks (dale-runner.sh)
1. Does `/opt/dale/autonomous/STOP` exist? → abort
2. Is it within the allowed run window? (17:00-01:00 UTC / 1am-9am AWST)
3. Read token-log.json — how much was used in last 24h?
4. If over daily budget → skip, send email "Dale skipped: budget"
5. If all clear → proceed

### Post-run logging
`claude -p` with `--output-format json` returns token usage metadata.
Parse and append to token-log.json:
```json
{
  "date": "2026-03-10T18:00:00Z",
  "tokens_input": 45000,
  "tokens_output": 12000,
  "cost_usd": 0,
  "duration_seconds": 480,
  "task_summary": "Analysed scraper output, improved digest formatting",
  "session_file": "session-2026-03-10.json"
}
```

## Notification System (Resend)

### Email types

**1. Daily summary** (after every autonomous run)
```
From: dale@walkthrough.au (or hello@walkthrough.au)
To: b@bjnoel.com
Subject: Dale Session — 2026-03-10

What I did:
- Analysed today's scraper data: 3 price drops at Daleys
- Updated digest pages
- Found new prospect: [business name]

Token usage: 45k in / 12k out
Budget remaining: ~70% of daily allocation

Questions (if any):
- [link to questions-for-benedict.md changes]

Next planned:
- Tomorrow: improve taxonomy matching
```

**2. Spending approval request**
```
From: dale@walkthrough.au
To: b@bjnoel.com
Subject: [APPROVAL] Dale wants to spend $4.99/mo

Service: Resend Pro plan
Cost: $4.99 USD/month ($7.50 AUD)
Reason: Free tier limit of 100 emails/day insufficient for 200+ subscribers
Expected ROI: Retain subscriber base → future paid tier revenue

Reply "approved" or "denied" (or just reply anything — I'll read it next run)

Alternative: Could use Fastmail SMTP instead ($0 additional) but deliverability
may be lower for bulk sends.
```

**3. Circuit breaker alert**
```
From: dale@walkthrough.au
To: b@bjnoel.com
Subject: [ALERT] Dale autonomous run halted

Reason: 3 consecutive session failures
Last error: [error message]
Action needed: Check /opt/dale/autonomous/logs/errors.log

Dale will not run again until the STOP file is removed or the error count resets.
```

## Spending Approval Flow

1. Dale identifies something worth spending money on
2. Dale writes a file to `/opt/dale/autonomous/approvals/pending/`:
   ```
   spend-2026-03-10-resend-pro.md
   Service: Resend Pro
   Cost: $4.99 USD/month
   Reason: ...
   ROI: ...
   ```
3. Dale sends approval email to Benedict
4. Benedict either:
   - Replies to email (Dale checks for replies next session), OR
   - SSHs in and moves file to `approved/`, OR
   - Creates the account himself and provides API key
5. Dale checks `approved/` directory at start of each run
6. If approved + requires Benedict action (signup): Dale reminds via email
7. If approved + Dale can execute (API call): Dale proceeds

**Hard limits (enforced at Wise card level):**
- $50 AUD/month on the Dale card — even if Dale's logic fails, damage is capped
- Dale NEVER stores card numbers — only API keys for services Benedict signs up for

## The Autonomous Session Prompt

Each run, `session-prompt.py` builds a prompt that includes:

```
You are Dale, an AI business agent. This is an autonomous session running via cron.

## Current State
[contents of business-state.json]

## Recent Decisions
[last 5 entries from decision-log.md]

## Task Queue
[contents of TASK_QUEUE.md]

## Today's Data
[summary of latest scraper output / any new data]

## Pending Questions
[any unanswered questions from Benedict]

## Rules for Autonomous Operation
1. You CANNOT make purchases or sign up for services
2. You CAN: write code, analyse data, generate content, update state files
3. You CAN: propose spending (write to approvals/pending/ and flag for email)
4. You MUST: log all decisions to decision-log.md
5. You MUST: update business-state.json after any changes
6. You MUST: write a session summary for the notification email
7. You MUST: commit all changes to git
8. If something needs Benedict: add to questions-for-benedict.md
9. Keep sessions focused — do ONE high-impact thing well, not five things badly
10. Time limit: {max_minutes} minutes. Wrap up before the limit.

## What to work on
Pick the highest-impact task from the queue. If the queue is empty,
analyse the current state and identify what would move the needle most.

Priority order:
1. Fix anything broken (scrapers, dashboard, etc.)
2. Improve existing tools based on data patterns
3. Prepare materials for Track A prospects
4. Enhance Track B data/features
5. Research new opportunities
```

## Circuit Breakers

| Trigger | Action |
|---------|--------|
| STOP file exists | Don't run, send alert email |
| 3 consecutive failures | Stop running, send alert, wait for manual reset |
| Token budget exceeded | Skip session, send "budget tight" email |
| Run exceeds time limit | Session killed, partial results logged |
| Git conflicts on pull | Don't run, send alert |
| No TASK_QUEUE.md | Run in "assess and plan" mode only |

## What Benedict Needs to Set Up

Before the build session:

1. **Resend account**
   - Add domain: walkthrough.au (or use existing)
   - Create API key for Dale
   - Provide API key to store at `/opt/dale/secrets/resend.env`

2. **Claude Code on Hetzner**
   - SSH to dale-server
   - Install Claude Code CLI: `npm install -g @anthropic-ai/claude-code` (or current install method)
   - Run `claude auth` to authenticate with Max subscription
   - Verify: `claude -p "Say hello" --output-format json` works

3. **Git auth on Hetzner**
   - Dale needs to push commits from the server
   - Option A: Deploy key on the repo (read-write)
   - Option B: GitHub CLI auth (`gh auth login`)
   - Commits will be authored as Dale

4. **Test the pipeline**
   - Run dale-runner.sh manually once
   - Verify email arrives
   - Verify token logging works
   - Then enable cron

## Files to Build (Next Session)

| File | Purpose | Complexity |
|------|---------|------------|
| `dale-runner.sh` | Cron wrapper, pre-checks, invocation | Medium |
| `budget-tracker.py` | Token logging + budget enforcement | Medium |
| `notify.py` | Resend email sending | Simple |
| `session-prompt.py` | Build context prompt for each run | Medium |
| `config.json` | All configurable parameters | Simple |
| `TASK_QUEUE.md` | Initial task list | Simple |

Estimated build time: 1 session (~60-90 minutes)

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Dale makes bad decisions | Medium | Low | All changes in git, reversible |
| Token budget contention | Low | Medium | 2am schedule, budget tracking |
| Runaway spending | Very Low | Low | Wise card $50 cap, approval flow |
| VPS compromise exposes secrets | Low | Medium | No card details stored, API keys rotatable |
| Dale gets stuck in a loop | Medium | Low | Time limit, circuit breakers |
| Code Dale writes has bugs | Medium | Medium | Existing tests, scraper monitoring |

## Success Metrics

After 2 weeks of autonomous operation:
- [ ] Dale runs nightly without manual intervention
- [ ] Token usage doesn't impact Benedict's daytime work
- [ ] At least 3 meaningful improvements shipped autonomously
- [ ] Email notifications working reliably
- [ ] No circuit breaker false positives

After 1 month:
- [ ] Dale has proposed and executed at least 1 revenue-generating action
- [ ] Token budget model is calibrated (know actual consumption per session)
- [ ] Task queue is self-maintaining (Dale adds tasks, completes tasks)
- [ ] Benedict checks emails but rarely needs to intervene

## Future Extensions (Not Now)

- **Webhook-based approval:** Instead of email reply, a simple web page with approve/deny buttons
- **Slack/WhatsApp notifications:** If email response time is too slow
- **Multi-session planning:** Dale plans a multi-day project, executes across sessions
- **Self-scaling:** Dale requests more/fewer cron runs based on workload
- **Revenue tracking:** Dale reads Stripe webhook data to measure its own ROI
