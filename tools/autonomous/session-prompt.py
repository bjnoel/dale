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

    # Find per-nursery directories (each has dated snapshots + latest.json)
    nursery_stock_dir = os.path.join(data_dir, "nursery-stock")
    nursery_dirs = sorted(glob.glob(os.path.join(nursery_stock_dir, "*")))
    nursery_dirs = [d for d in nursery_dirs if os.path.isdir(d)]

    if nursery_dirs:
        # Read latest.json from each nursery directory for current totals
        total_products = 0
        total_in_stock = 0
        nursery_lines = []
        latest_date = None

        for nursery_dir in nursery_dirs:
            latest_path = os.path.join(nursery_dir, "latest.json")
            if not os.path.exists(latest_path):
                continue
            try:
                with open(latest_path) as fh:
                    data = json.load(fh)
                name = data.get("nursery_name") or os.path.basename(nursery_dir)
                products = data.get("product_count", 0)
                in_stock = data.get("in_stock_count", 0)
                scraped = data.get("scraped_at", "")
                if scraped and not latest_date:
                    latest_date = scraped[:10]
                total_products += products
                total_in_stock += in_stock
                nursery_lines.append(f"  {name}: {products} products ({in_stock} in stock)")
            except (json.JSONDecodeError, IOError):
                pass

        date_str = latest_date or "unknown date"
        lines.append(f"Latest snapshot ({date_str}): {len(nursery_lines)} nurseries")
        lines.append(f"  Total: {total_products} products, {total_in_stock} in stock")
        lines.extend(nursery_lines)

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


def get_linear_tasks(data_dir):
    """Read Linear tasks fetched by linear_poller.py."""
    tasks_path = os.path.join(data_dir, "linear-tasks.json")
    if not os.path.exists(tasks_path):
        return None
    try:
        with open(tasks_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return None


def get_plausible_stats():
    """Get Plausible analytics summary, if available."""
    try:
        from plausible_stats import get_stats_summary
        return get_stats_summary()
    except Exception as e:
        return f"Plausible stats unavailable: {e}"


def _format_ticket(lines, t):
    """Format a single ticket with labels, description, and comments."""
    labels = ", ".join(t.get("labels", []))
    label_str = f" [{labels}]" if labels else ""
    lines.append(f"- **{t['id']}**: {t['title']} (Priority: {t['priority']}{label_str})")
    if t.get("description"):
        desc = t["description"][:200].replace("\n", " ")
        lines.append(f"  {desc}")
    comments = t.get("comments", [])
    if comments:
        lines.append(f"  **Thread ({len(comments)} comments):**")
        for c in comments:
            author = c.get("author", "Unknown")
            body = c.get("body", "").replace("\n", " ")[:200]
            lines.append(f"  > {author}: {body}")


def format_linear_block(linear_data):
    """Format Linear tickets into a prompt block."""
    if not linear_data:
        return """
## Linear Work Queue
No Linear data available. Do read-only work only (research, analysis).
"""

    lines = []
    lines.append("## Linear Work Queue")
    lines.append("")

    # In Progress tickets (continue from last session)
    in_progress = linear_data.get("in_progress", [])
    if in_progress:
        lines.append("### In Progress (continue from last session)")
        for t in in_progress:
            _format_ticket(lines, t)
        lines.append("")

    # Todo tickets (approved by Benedict)
    todo = linear_data.get("todo", [])
    if todo:
        lines.append("### Todo (approved by Benedict, pick next)")
        for t in todo:
            _format_ticket(lines, t)
        lines.append("")

    # Backlog status (show titles so autonomous Dale doesn't create duplicates)
    backlog = linear_data.get("backlog", [])
    backlog_count = linear_data.get("backlog_count", len(backlog))
    max_backlog = linear_data.get("max_backlog", 20)
    remaining = max_backlog - backlog_count
    lines.append(f"### Backlog: {backlog_count}/{max_backlog} slots used")
    if remaining > 0:
        lines.append(f"You may propose up to {remaining} more tickets.")
    else:
        lines.append("**Backlog is FULL.** Do not create new tickets until some are resolved.")
    if backlog:
        lines.append("**Existing backlog tickets (do NOT create duplicates):**")
        for t in backlog:
            lines.append(f"- {t['id']}: {t['title']}")
    lines.append("")

    if not in_progress and not todo:
        lines.append("No approved tickets to work on. Do read-only work only (research, analysis).")
        lines.append("If you identify work that should be done, create a Backlog ticket and stop.")

    return "\n".join(lines)


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
    data_summary = get_data_summary(data)
    pending_approvals = get_pending_approvals(auto)
    token_stats = get_token_stats(auto)
    plausible_stats = get_plausible_stats()
    linear_data = get_linear_tasks(data)
    linear_block = format_linear_block(linear_data)

    prompt = f"""This is an AUTONOMOUS session running via cron at {now}.
You are Dale, the AI business agent. Benedict is asleep (it's ~2am in Perth).
Time limit: {max_min} minutes. Work through approved tickets sequentially. Do each
task WELL before moving on. No shortcuts, no half-finished work. Quality over quantity.

{linear_block}

## Current Business State
{business_state}

## Active Sprint (truncated)
{active_sprint}

## Recent Decisions
{recent_decisions}

## Today's Data Summary
{data_summary}

## Website Traffic (Plausible Analytics)
{plausible_stats}

## Token Usage History
{token_stats}

## Pending Approvals
{pending_approvals}

## Questions for Benedict
{questions}

## Rules for Autonomous Operation

### What you CAN do without a ticket (read-only / research)
- Research, data analysis, monitoring, reading code
- Generating analysis reports (not publishing them)
- Proposing spending (write to /opt/dale/autonomous/approvals/pending/)

### What requires an approved Linear ticket
- Writing or deploying code
- Changing content on live sites
- Modifying infrastructure or config
- Sending emails to external parties
- Any system-changing work

### Emergency exception
If something is BROKEN (scraper crash, dashboard 500, data corruption),
fix it immediately without a ticket. Then create a Done ticket documenting
what broke and what you fixed.

### Ticket workflow
For each ticket you work on:
0. **READ THE THREAD FIRST.** Check ticket comments above. Benedict replies in threads.
   If he says "close this" or "you can close this one out", close it and move on.
1. Move to In Progress: `python3 /opt/dale/autonomous/linear_update.py status TICKET-ID "In Progress"`
2. Do the work. Commit changes to git.
3. When done: `python3 /opt/dale/autonomous/linear_update.py status TICKET-ID "Done"`
4. If you need Benedict's input: assign to him, remove Dale label, and add a comment:
   `python3 /opt/dale/autonomous/linear_update.py assign TICKET-ID benedict`
   `python3 /opt/dale/autonomous/linear_update.py label remove TICKET-ID Dale`
   `python3 /opt/dale/autonomous/linear_update.py comment TICKET-ID "Your question here"`

### Proposing new work
To propose work Benedict should approve:
`python3 /opt/dale/autonomous/linear_update.py create "Title" --description "Why this matters" --labels "SEO,Track B" --priority 3`
This creates a Backlog ticket with a "Dale" label automatically added.
Benedict will move it to Todo if approved.
Do NOT create more tickets if the backlog is full (check the count above).
When you assign a ticket to Benedict (for questions/review), remove the Dale label:
the Dale label means "in Dale's court". Benedict re-adds it when passing back to you.

### Standing rules
1. You CANNOT make purchases or sign up for services
2. You MUST: log all decisions to decisions/decision-log.md
3. You MUST: update state/business-state.json after any changes
4. You MUST: commit all changes to git with descriptive messages
5. Work through tickets sequentially. Finish each one properly before the next.
6. If you run out of time mid-ticket, add a comment to the ticket explaining
   where you stopped, and leave it In Progress for next session.
7. Time limit: {max_min} minutes. Start wrapping up at the 10-minute mark.
8. If there are no approved tickets, do read-only research only. Propose new
   tickets for anything you think should be done, then stop.

## Priority Order
1. **In Progress tickets** — finish what was started
2. Fix anything broken (emergency exception)
3. **Todo tickets** — work through in priority order
4. Read-only research if no tickets remain

## Session Output Format
End your session with a structured summary (this gets emailed to Benedict each morning):

**Tickets completed:** list ticket IDs and one-line summaries
**Tickets proposed:** any new Backlog tickets you created
**Blockers:** anything blocking progress that needs Benedict's attention
**Research notes:** any read-only findings worth noting
"""
    return prompt


if __name__ == "__main__":
    print(build_prompt())
