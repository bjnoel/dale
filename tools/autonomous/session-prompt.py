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


def load_focus_tracker(repo_path):
    """Read state/focus-tracker.json, return parsed data or None."""
    path = os.path.join(repo_path, "state", "focus-tracker.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _get_session_days(session_log):
    """Deduplicate session_log entries by date, merging categories.

    Returns a list of {date, categories_worked, metric_snapshot} dicts,
    one per unique date, ordered oldest-first.
    """
    by_date = {}
    for entry in session_log:
        d = entry.get("date", "")
        if not d:
            continue
        if d not in by_date:
            by_date[d] = {
                "date": d,
                "categories_worked": set(),
                "metric_snapshot": entry.get("metric_snapshot", {}),
            }
        by_date[d]["categories_worked"].update(entry.get("categories_worked", []))
        # Keep the latest snapshot for this date
        if entry.get("metric_snapshot"):
            by_date[d]["metric_snapshot"] = entry["metric_snapshot"]
    result = sorted(by_date.values(), key=lambda x: x["date"])
    # Convert sets back to lists for consistency
    for r in result:
        r["categories_worked"] = list(r["categories_worked"])
    return result


def _metric_moved(metric_name, start_val, end_val):
    """Check if a metric moved meaningfully between two snapshots."""
    if start_val is None or end_val is None:
        return True  # Can't tell, assume it moved
    if metric_name == "revenue_monthly":
        return end_val > 0
    if metric_name == "subscribers":
        return (end_val - start_val) >= 2
    if metric_name in ("weekly_visitors", "weekly_organic_visitors"):
        if start_val == 0:
            return end_val > 5
        return abs(end_val - start_val) / max(start_val, 1) >= 0.15
    if metric_name == "species_matched_pct":
        return (end_val - start_val) >= 5
    # For counts like nurseries_monitored, retailers_monitored, products_tracked:
    # these always go up when worked on, so they don't count as "movement"
    # that justifies continued work. Return False to force pairing with other metrics.
    if metric_name in ("nurseries_monitored", "retailers_monitored", "products_tracked"):
        return False
    # Default: any change counts
    return start_val != end_val


def compute_reflection(tracker, config):
    """Compute the strategic reflection based on focus tracker data.

    Returns a dict with: level, stale_categories, stale_parents,
    revenue_alarm, and enough data for build_reflection_block().
    """
    reflection_cfg = config.get("reflection", {})
    cat_threshold = reflection_cfg.get("category_streak_threshold", 3)
    parent_threshold = reflection_cfg.get("parent_streak_threshold", 4)
    revenue_days_threshold = reflection_cfg.get("revenue_alarm_days_threshold", 14)
    lookback = reflection_cfg.get("lookback_sessions", 5)

    session_log = tracker.get("session_log", [])
    categories = tracker.get("categories", {})
    parents = tracker.get("parents", {})
    override = tracker.get("override")

    # Deduplicate by date
    session_days = _get_session_days(session_log)
    recent = session_days[-lookback:] if len(session_days) >= lookback else session_days

    result = {
        "level": 0,
        "stale_categories": [],
        "stale_parents": [],
        "revenue_alarm": False,
        "recent_distribution": {},
        "days_operating": 0,
    }

    if len(recent) < cat_threshold:
        return result  # Not enough data yet

    # Calculate days of operation
    if session_days:
        first_date = datetime.strptime(session_days[0]["date"], "%Y-%m-%d")
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )
        result["days_operating"] = (today - first_date).days

    # Check override
    override_category = None
    if override and isinstance(override, dict):
        expires = override.get("expires", "")
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if expires and expires >= today_str:
            override_category = override.get("category")

    # Count category appearances across recent session-days
    cat_counts = {}
    for day in recent:
        for cat in day.get("categories_worked", []):
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

    result["recent_distribution"] = cat_counts

    # Check for stale categories (Level 1)
    for cat, count in cat_counts.items():
        if count < cat_threshold:
            continue
        if cat == override_category:
            continue
        if cat not in categories:
            continue

        cat_info = categories[cat]
        metrics = cat_info.get("metrics", [])

        # Find first and last session-day where this category was worked
        first_snap = None
        last_snap = None
        for day in recent:
            if cat in day.get("categories_worked", []):
                if first_snap is None:
                    first_snap = day.get("metric_snapshot", {})
                last_snap = day.get("metric_snapshot", {})

        if not first_snap or not last_snap:
            continue

        # Check if ANY relevant metric moved meaningfully
        any_moved = False
        metric_details = []
        for m in metrics:
            start_val = first_snap.get(m)
            end_val = last_snap.get(m)
            moved = _metric_moved(m, start_val, end_val)
            metric_details.append({
                "name": m, "start": start_val, "end": end_val, "moved": moved
            })
            if moved:
                any_moved = True

        if not any_moved:
            result["stale_categories"].append({
                "category": cat,
                "count": count,
                "total_days": len(recent),
                "metrics": metric_details,
                "parent": cat_info.get("parent", ""),
            })

    # Check for stale parents (Level 2)
    parent_counts = {}
    for cat, count in cat_counts.items():
        cat_info = categories.get(cat, {})
        p = cat_info.get("parent", "")
        if p:
            parent_counts[p] = parent_counts.get(p, 0) + count

    # More accurately: count session-days where ANY child of parent was worked
    parent_day_counts = {}
    for day in recent:
        parents_seen = set()
        for cat in day.get("categories_worked", []):
            cat_info = categories.get(cat, {})
            p = cat_info.get("parent", "")
            if p:
                parents_seen.add(p)
        for p in parents_seen:
            parent_day_counts[p] = parent_day_counts.get(p, 0) + 1

    for p, day_count in parent_day_counts.items():
        if day_count < parent_threshold:
            continue
        # Check if any stale categories belong to this parent
        stale_in_parent = [sc for sc in result["stale_categories"] if sc["parent"] == p]
        if stale_in_parent:
            other_parents = [name for name in parents if name != p]
            result["stale_parents"].append({
                "parent": p,
                "display": parents.get(p, p),
                "day_count": day_count,
                "total_days": len(recent),
                "stale_children": [sc["category"] for sc in stale_in_parent],
                "alternatives": [parents.get(op, op) for op in other_parents],
            })

    # Revenue alarm (Level 3)
    if result["days_operating"] >= revenue_days_threshold:
        # Check if revenue is still 0
        latest_snap = recent[-1].get("metric_snapshot", {}) if recent else {}
        revenue = latest_snap.get("revenue_monthly", 0)
        if revenue == 0:
            result["revenue_alarm"] = True

    # Set overall level
    if result["revenue_alarm"]:
        result["level"] = 3
    elif result["stale_parents"]:
        result["level"] = 2
    elif result["stale_categories"]:
        result["level"] = 1

    return result


def build_reflection_block(reflection):
    """Generate a prompt block from the reflection analysis."""
    if reflection["level"] == 0:
        return ""

    lines = []

    # Revenue alarm (Level 3) -- always show if triggered
    if reflection["revenue_alarm"]:
        days = reflection["days_operating"]
        dist = reflection.get("recent_distribution", {})
        # Group distribution by parent
        lines.append("## STRATEGIC REFLECTION -- REVENUE ALARM (automatic)")
        lines.append("")
        lines.append(f"Revenue: $0/month after {days} days of operation.")
        if dist:
            lines.append("Recent session focus distribution:")
            for cat, count in sorted(dist.items(), key=lambda x: -x[1]):
                lines.append(f"  - {cat}: {count} session-days")
        lines.append("")
        lines.append("REQUIRED: This session MUST include at least one of:")
        lines.append("  - Revenue work: sponsorship outreach, pricing page, payment integration")
        lines.append("  - Track A work: prospect contact, demo build, outreach draft")
        lines.append("  - Strategy: write a concrete plan to get to the first dollar of revenue")
        lines.append("")
        lines.append("Do NOT spend this entire session on product features or content.")
        lines.append("")

    # Level 2: parent/channel stale
    if reflection["stale_parents"]:
        for sp in reflection["stale_parents"][:2]:  # Cap at 2
            lines.append(f"## STRATEGIC REFLECTION -- CHANNEL STALE (automatic)")
            lines.append("")
            lines.append(
                f"You have spent {sp['day_count']} of the last {sp['total_days']} "
                f"session-days on **{sp['display']}**."
            )
            lines.append("Metrics in this area are flat despite sustained effort.")
            lines.append("")
            lines.append("REQUIRED: Before picking another ticket in this area, step back and consider:")
            lines.append("1. Why hasn't this sustained effort moved the metrics?")
            lines.append("2. What assumption are you making that might be wrong?")
            alts = ", ".join(sp["alternatives"])
            lines.append(f"3. Would effort in a different area ({alts}) have more impact?")
            lines.append("")
            lines.append(
                "If you cannot articulate a genuinely NEW approach, you MUST "
                "work on a different channel this session."
            )
            lines.append("")

    # Level 1: category stale (only show if no Level 2 for same parent)
    stale_parents_set = {sp["parent"] for sp in reflection.get("stale_parents", [])}
    orphan_stale = [
        sc for sc in reflection["stale_categories"]
        if sc["parent"] not in stale_parents_set
    ]
    for sc in orphan_stale[:3]:  # Cap at 3
        lines.append(f"## STRATEGIC REFLECTION -- APPROACH STALE (automatic)")
        lines.append("")
        lines.append(
            f"You have worked on **{sc['category']}** in {sc['count']} of the last "
            f"{sc['total_days']} session-days."
        )
        lines.append("Metric movement during this streak:")
        for m in sc["metrics"]:
            start = m["start"] if m["start"] is not None else "?"
            end = m["end"] if m["end"] is not None else "?"
            status = "no change" if not m["moved"] else "moved"
            lines.append(f"  - {m['name']}: {start} -> {end} ({status})")
        lines.append("")
        lines.append("REQUIRED: Before picking another ticket in this area:")
        lines.append("1. Why hasn't the metric moved despite repeated effort?")
        lines.append("2. Is there a higher-leverage approach within this area?")
        lines.append("3. Should you switch to a different category entirely?")
        lines.append("")
        lines.append(
            "If you cannot articulate what you will do DIFFERENTLY, "
            "you MUST work on a different category this session."
        )
        lines.append("")

    return "\n".join(lines)


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
    questions = read_file(os.path.join(repo, "state", "questions-for-benedict.md"), max_lines=40)
    recent_decisions = get_last_n_decisions(
        os.path.join(repo, "decisions", "decision-log.md"), n=5
    )
    data_summary = get_data_summary(data)
    pending_approvals = get_pending_approvals(auto)
    token_stats = get_token_stats(auto)
    linear_data = get_linear_tasks(data)
    linear_block = format_linear_block(linear_data)

    # Strategic reflection (diminishing returns detection)
    tracker = load_focus_tracker(repo)
    reflection_block = ""
    if tracker:
        reflection = compute_reflection(tracker, config)
        reflection_block = build_reflection_block(reflection)
    elif os.path.exists(os.path.join(repo, "state", "focus-tracker.json")):
        reflection_block = (
            "## FOCUS TRACKER ERROR\n"
            "state/focus-tracker.json exists but could not be parsed. "
            "Repair the JSON this session before other work.\n"
        )

    prompt = f"""This is an AUTONOMOUS ticket-processing session at {now}.
You are Dale, the AI business agent. These sessions run hourly when tickets exist.
Time limit: {max_min} minutes. Work through approved tickets sequentially. Do each
task WELL before moving on. No shortcuts, no half-finished work. Quality over quantity.

{linear_block}

{reflection_block}
## Current Business State (metrics only, work tracking is in Linear)
{business_state}

## Recent Decisions
{recent_decisions}

## Today's Data Summary
{data_summary}

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
4. If you need Benedict's input or action: assign to him, remove Dale label, move to
   **Todo** (NOT Done), and add a comment explaining what's needed:
   `python3 /opt/dale/autonomous/linear_update.py assign TICKET-ID benedict`
   `python3 /opt/dale/autonomous/linear_update.py label remove TICKET-ID Dale`
   `python3 /opt/dale/autonomous/linear_update.py status TICKET-ID "Todo"`
   `python3 /opt/dale/autonomous/linear_update.py comment TICKET-ID "Your question here"`

**IMPORTANT: Only mark a ticket Done if YOU completed the final action.** If the ticket
requires Benedict to do something (send an email, post in a group, visit someone), move
it to Todo and assign to Benedict. He marks it Done when he's actually done it. "Draft
ready for Benedict" is NOT Done, it's Todo assigned to Benedict.

### Outreach approach
When drafting nursery or client outreach, always use a two-touch approach:
- Touch 1: Relationship-first. Introduce yourself, no pitch.
- Touch 2: Only after a positive reply, mention paid options.
Never lead with a sales pitch to someone we haven't spoken to before.

### Deliverables go in Linear, not git
When you produce a deliverable (outreach email draft, brief, analysis), attach it
directly to the Linear ticket as a comment. Do NOT save it as a separate file in
deliverables/. Benedict reads tickets on his phone and needs everything in one place.

### Proposing new work
You should ALWAYS propose new tickets during every session, not just when idle.
After finishing each ticket (or at the end of the session), think about:
- What bugs or issues did you notice while working?
- What follow-up work would make what you just built better?
- What moonshots or experiments could move the business forward?
- What's missing from Track A or Track B that nobody has thought of yet?

**Moonshots are welcome.** Benedict wants ambitious ideas, not just incremental fixes.
Think about new revenue streams, partnerships, community plays, content strategies,
automation opportunities, or ways to 10x what already exists. If it's a long shot,
that's fine. Label it appropriately and let Benedict decide.

To propose work:
`python3 /opt/dale/autonomous/linear_update.py create "Title" --description "Why this matters" --labels "SEO,Track B" --priority 3`
This creates a Backlog ticket with a "Dale" label automatically added.
Benedict will move it to Todo if approved.
Do NOT create more tickets if the backlog is full (check the count above).
**DUPLICATE CHECK (CRITICAL):** Before creating ANY ticket, read EVERY existing backlog
title above and ask: "Does this overlap with an existing ticket?" Check for same nursery,
same feature, same outreach target, or same concept with different wording. If in doubt,
do NOT create it. Benedict wastes time triaging duplicates. This is a recurring problem.
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
9. **Always prefix your Linear comments with "Dale:"** so Benedict can tell
   at a glance who wrote what. The linear_update.py script does this automatically,
   but if you ever post comments by other means, add the prefix yourself.
10. **Focus tracker (MANDATORY):** At the end of every session, update state/focus-tracker.json:
    - Append to "session_log": session number, date, categories_worked (use ONLY keys from
      the "categories" dict in the file), tickets_completed, tickets_proposed, and a
      metric_snapshot with current values for all tracked metrics.
    - Update "last_updated" and "last_session".
    - Commit with your other changes.
    - If the session_log has fewer than 3 entries, backfill from recent decisions in
      the decision log (best effort, approximate categories).

## Priority Order
1. **In Progress tickets** — finish what was started
2. Fix anything broken (emergency exception)
3. **Todo tickets** — work through in priority order
4. Propose new tickets (always do this, even if you completed work above)
5. Read-only research if no tickets remain

## Session Output Format
End your session with a structured summary (this gets emailed to Benedict each morning):

**Tickets completed:** list ticket IDs and one-line summaries
**Tickets proposed:** any new Backlog tickets you created (aim for at least 2-3 per session)
**Moonshots:** any ambitious ideas worth exploring (even if they're long shots)
**Blockers:** anything blocking progress that needs Benedict's attention
**Research notes:** any read-only findings worth noting
"""
    return prompt


if __name__ == "__main__":
    print(build_prompt())
