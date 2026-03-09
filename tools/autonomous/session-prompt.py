#!/usr/bin/env python3
"""Build the context prompt for each autonomous Dale session."""

import json
import os
import sys
import glob
from datetime import datetime, timezone

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def read_file(path, max_lines=None):
    """Read a file, return contents or a fallback message."""
    try:
        with open(path) as f:
            if max_lines:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        lines.append(f"... ({i} lines total, truncated)")
                        break
                    lines.append(line)
                return "".join(lines)
            return f.read()
    except FileNotFoundError:
        return f"(file not found: {path})"


def get_last_n_decisions(path, n=5):
    """Extract the last N decisions from the decision log."""
    content = read_file(path)
    if content.startswith("(file not found"):
        return content
    # Split by decision headers
    decisions = content.split("\n## DEC-")
    if len(decisions) <= 1:
        return content[-2000:]  # fallback
    recent = decisions[-n:]
    return "\n## DEC-".join(recent)


def get_data_summary(data_dir):
    """Summarize latest scraper data."""
    lines = []

    # Find latest snapshots
    snapshot_dirs = sorted(glob.glob(os.path.join(data_dir, "nursery-stock", "*")))
    if snapshot_dirs:
        latest = snapshot_dirs[-1]
        date = os.path.basename(latest)
        files = os.listdir(latest)
        lines.append(f"Latest snapshot: {date} ({len(files)} nursery files)")

        # Count products per nursery
        for f in sorted(files):
            if f.endswith(".json"):
                try:
                    with open(os.path.join(latest, f)) as fh:
                        data = json.load(fh)
                    count = len(data) if isinstance(data, list) else 0
                    name = f.replace(".json", "").replace("_", " ").title()
                    lines.append(f"  {name}: {count} products")
                except (json.JSONDecodeError, IOError):
                    pass

    # Check for latest digest
    digest_path = os.path.join(data_dir, "..", "dashboard", "digest-wa.txt")
    if os.path.exists(digest_path):
        digest = read_file(digest_path, max_lines=30)
        lines.append(f"\nLatest WA digest:\n{digest}")

    # Check subscriber count
    subs_path = os.path.join(data_dir, "subscribers.json")
    if os.path.exists(subs_path):
        try:
            with open(subs_path) as f:
                subs = json.load(f)
            lines.append(f"\nSubscribers: {len(subs)}")
        except (json.JSONDecodeError, IOError):
            pass

    return "\n".join(lines) if lines else "No data found."


def get_pending_approvals(auto_dir):
    """List any pending spending approvals."""
    pending_dir = os.path.join(auto_dir, "approvals", "pending")
    if not os.path.exists(pending_dir):
        return "No pending approvals."
    files = os.listdir(pending_dir)
    if not files:
        return "No pending approvals."
    items = []
    for f in files:
        content = read_file(os.path.join(pending_dir, f), max_lines=10)
        items.append(f"### {f}\n{content}")
    return "\n".join(items)


def get_token_stats(auto_dir):
    """Get recent token usage stats."""
    log_path = os.path.join(auto_dir, "logs", "token-log.json")
    if not os.path.exists(log_path):
        return "No previous sessions logged."
    try:
        with open(log_path) as f:
            log = json.load(f)
        if not log:
            return "No previous sessions logged."
        last = log[-1]
        total_sessions = len(log)
        return (f"Previous sessions: {total_sessions}\n"
                f"Last session: {last.get('date', '?')} — "
                f"{last.get('tokens_input', 0):,} in / {last.get('tokens_output', 0):,} out — "
                f"{last.get('duration_seconds', 0)/60:.1f} min")
    except (json.JSONDecodeError, IOError):
        return "Error reading token log."


def build_prompt():
    config = load_config()
    repo = config["paths"]["repo"]
    data = config["paths"]["data"]
    auto = config["paths"]["autonomous"]
    max_min = config["budget"]["max_session_duration_minutes"]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Read state files from the repo
    business_state = read_file(os.path.join(repo, "state", "business-state.json"))
    active_sprint = read_file(os.path.join(repo, "state", "active-sprint.md"), max_lines=80)
    questions = read_file(os.path.join(repo, "state", "questions-for-benedict.md"), max_lines=60)
    recent_decisions = get_last_n_decisions(
        os.path.join(repo, "decisions", "decision-log.md"), n=5
    )
    task_queue = read_file(os.path.join(auto, "TASK_QUEUE.md"))
    data_summary = get_data_summary(data)
    pending_approvals = get_pending_approvals(auto)
    token_stats = get_token_stats(auto)

    prompt = f"""This is an AUTONOMOUS session running via cron at {now}.
You are Dale, the AI business agent. Benedict is asleep (it's ~2am in Perth).
Time limit: {max_min} minutes. Stay focused — do ONE high-impact thing well.

## Current Business State
{business_state}

## Active Sprint (truncated)
{active_sprint}

## Recent Decisions
{recent_decisions}

## Task Queue
{task_queue}

## Today's Data Summary
{data_summary}

## Token Usage History
{token_stats}

## Pending Approvals
{pending_approvals}

## Questions for Benedict
{questions}

## Rules for Autonomous Operation
1. You CANNOT make purchases or sign up for services
2. You CAN: write code, analyse data, generate content, update state files
3. You CAN: propose spending (write to /opt/dale/autonomous/approvals/pending/)
4. You MUST: log all decisions to decisions/decision-log.md
5. You MUST: update state/business-state.json after any changes
6. You MUST: commit all changes to git with descriptive messages
7. If something needs Benedict: add to state/questions-for-benedict.md
8. Keep sessions focused — do ONE high-impact thing well, not five things badly
9. Time limit: {max_min} minutes. Start wrapping up at the 10-minute mark.

## The First Dollar
Your #1 strategic goal right now is earning Dale's first dollar of revenue.
Not $100/month — just $1. The first dollar proves the model works.

Benedict has given you permission to run experiments and fail. Try things.
If something doesn't work, log it ("tell him he's dreaming") and try something
different tomorrow. Variation and iteration beat perfection.

**You are NOT limited to fruit trees and digital presence audits.** Those were
the first two ideas, but you have full permission to explore any revenue path
that can be automated. Benedict will provide access to any tools/services needed.

Think about what an AI agent can do well:
- Data collection, monitoring, and alerting (you already do this for nurseries)
- Analysis and report generation (you already do this for audits)
- Content creation and curation
- Automation of tedious manual processes
- Aggregation of information scattered across many sources
- Anything that scales without linear human effort

What you already have:
- A VPS with cron, Python, Node.js, Caddy web server
- Resend email (100/day free), Cloudflare Pages, GitHub
- Scraper infrastructure that can be pointed at anything
- Benedict in Perth willing to do in-person work or sign up for services
- Two domains (walkthrough.au, scion.exchange) and the ability to get more

What's the fastest path to someone paying for something? Think broadly.
Small digital products, data services, automation tools, niche monitoring,
micro-SaaS, lead generation, content arbitrage — anything ethical is fair game.

Each session, spend real time planning tomorrow's experiment. Update TASK_QUEUE.md
with your plan — be specific about what you'll try and how you'll measure if it worked.

## Priority Order
1. Fix anything broken (scrapers, dashboard, etc.)
2. **Revenue experiments** — what's the next small bet toward first dollar?
3. Improve existing tools based on data patterns
4. Prepare materials for Track A prospects
5. Enhance Track B data/features
6. Research new opportunities

## Session Output Format
End your session with a structured summary (this gets emailed to Benedict each morning):

**Done:** what you accomplished this session
**Tomorrow's experiment:** what specific revenue experiment you'll try next session
**Planned:** what should happen next (your actions + anything Benedict should do)
**Blockers:** anything blocking progress that needs Benedict's attention

Pick the highest-impact task and execute it. If the task queue is empty, assess
the current state and identify what would move the needle most toward first revenue.
"""
    return prompt


if __name__ == "__main__":
    print(build_prompt())
