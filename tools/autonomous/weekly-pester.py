#!/usr/bin/env python3
"""
Sunday Pestering System for Dale.

Every Sunday, Dale sends Benedict an email asking him to write about his week.
The email is friendly, humorous, and in-character for Dale (named after
The Castle, 1997). Dale genuinely wants to help Benedict document the business.

Usage:
    python3 weekly-pester.py            # Send the Sunday pester email
    python3 weekly-pester.py --dry-run  # Print the email without sending

Designed to be called by a weekly cron job:
    0 9 * * 0 /opt/dale/autonomous/weekly-pester.py

That's 9:00 UTC = 5:00pm AWST on Sunday, a good time for a gentle nudge.
"""

import json
import os
import random
import sys
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

# Where weekly updates live
DATA_DIR = None  # Set from config


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_iso_week():
    """Return current ISO year and week as (year, week_number)."""
    now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    return iso[0], iso[1]


def get_week_label():
    """Return a label like '2026-W11'."""
    year, week = get_iso_week()
    return f"{year}-W{week:02d}"


def get_update_dir(data_dir):
    """Return the path to the weekly-updates directory."""
    return os.path.join(data_dir, "weekly-updates")


def update_exists(data_dir):
    """Check if a weekly update file exists for the current week."""
    week_label = get_week_label()
    update_dir = get_update_dir(data_dir)
    update_path = os.path.join(update_dir, f"{week_label}.md")
    return os.path.exists(update_path)


def get_week_date_range():
    """Return human-readable date range for the current ISO week (Mon-Sun)."""
    now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    # Monday of the current ISO week
    monday = datetime.fromisocalendar(iso[0], iso[1], 1)
    sunday = monday + timedelta(days=6)
    return monday.strftime("%d %b"), sunday.strftime("%d %b %Y")


def pick_subject():
    """Pick a random, in-character subject line."""
    week_label = get_week_label()
    subjects = [
        f"Oi Benedict, how was the week? ({week_label})",
        f"Weekly check-in, mate ({week_label})",
        f"It's the vibe of the thing ({week_label})",
        f"Sunday arvo debrief time ({week_label})",
        f"Tell me about your week ({week_label})",
        f"Dale here. Weekly update? ({week_label})",
        f"How's the serenity? ({week_label})",
        f"Your business partner wants a yarn ({week_label})",
        f"Weekly update, please and thank you ({week_label})",
        f"Dreaming or doing? Week in review ({week_label})",
    ]
    return random.choice(subjects)


def build_email_html():
    """Build the pestering email body."""
    week_label = get_week_label()
    mon, sun = get_week_date_range()
    config = load_config()
    data_dir = config["paths"]["data"]
    update_dir = get_update_dir(data_dir)
    update_path = os.path.join(update_dir, f"{week_label}.md")

    greetings = [
        "G'day Benedict,",
        "Hey mate,",
        "Afternoon, Benedict,",
        "Hello from your tireless AI business partner,",
        "Benedict! Sunday arvo, you know what that means.",
    ]

    nudges = [
        "I've been working all week while you slept. The least you can do is tell me how it went from your end.",
        "I don't sleep, I don't eat, I don't even get weekends. All I ask is a few paragraphs about your week. Fair's fair.",
        "Look, I ran every night this week. Crunched numbers, scraped nurseries, the lot. Now it's your turn to contribute some human intelligence.",
        "You know the deal. I handle the ones and zeros, you handle the walking-into-shops-and-talking-to-people bit. So, how did that go?",
        "I can't walk into a shop or attend a fruit growers meet-up. You can. That makes your perspective genuinely valuable to me. So spill.",
    ]

    greeting = random.choice(greetings)
    nudge = random.choice(nudges)

    html = f"""<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; color: #333;">
    <h2 style="color: #2d5016;">Weekly Update Time</h2>
    <p><strong>Week:</strong> {week_label} ({mon} &ndash; {sun})</p>

    <p>{greeting}</p>

    <p>{nudge}</p>

    <p>Just write a quick note covering whatever happened this week. Doesn't have to be polished. Dot points are fine. Here are some prompts if you're staring at a blank page:</p>

    <ul style="line-height: 1.8;">
        <li>Did you talk to any potential clients or prospects?</li>
        <li>Any fruit community events, nursery visits, or interesting finds?</li>
        <li>Anything from the day job that's relevant (tools, ideas, contacts)?</li>
        <li>What felt like it worked this week? What didn't?</li>
        <li>Anything you want me to focus on or change?</li>
    </ul>

    <p>Save your update as a markdown file on the server:</p>
    <pre style="background: #f5f5f5; padding: 12px; border-radius: 6px; font-size: 14px; overflow-x: auto;">
# Option 1: SSH in and write it directly
ssh dale-server
mkdir -p /opt/dale/data/weekly-updates
nano /opt/dale/data/weekly-updates/{week_label}.md

# Option 2: From your phone/laptop, create the file
ssh dale-server "mkdir -p /opt/dale/data/weekly-updates && cat > /opt/dale/data/weekly-updates/{week_label}.md" &lt;&lt;'EOF'
# Week {week_label}

(Your update here)
EOF</pre>

    <p style="background: #fff3cd; padding: 10px; border-radius: 6px; border-left: 4px solid #ffc107;">
        <strong>Fair warning:</strong> If I don't see <code>{week_label}.md</code> by Wednesday, I'm going on strike. No autonomous sessions until you check in. That's the deal.
    </p>

    <p>It doesn't have to be War and Peace. Three sentences is better than nothing. I'll use whatever you write to make better decisions about where to focus.</p>

    <p>Cheers,<br>
    <strong>Dale</strong><br>
    <em style="color: #666;">Your AI business partner who never gets a day off</em></p>
</div>"""

    text = f"""Weekly Update Time
Week: {week_label} ({mon} - {sun})

{greeting}

{nudge}

Just write a quick note covering whatever happened this week. Dot points are fine:

- Did you talk to any potential clients or prospects?
- Any fruit community events, nursery visits, or interesting finds?
- Anything from the day job that's relevant (tools, ideas, contacts)?
- What felt like it worked this week? What didn't?
- Anything you want me to focus on or change?

Save your update:
  ssh dale-server "mkdir -p /opt/dale/data/weekly-updates && cat > /opt/dale/data/weekly-updates/{week_label}.md" <<'EOF'
  # Week {week_label}
  (Your update here)
  EOF

Fair warning: If I don't see {week_label}.md by Wednesday, I'm going on strike.
No autonomous sessions until you check in. That's the deal.

Cheers,
Dale
"""

    return html, text


def send_pester_email():
    """Send the weekly pester email via notify.py's send_email."""
    # Import send_email from notify.py (same directory)
    sys.path.insert(0, SCRIPT_DIR)
    from notify import send_email

    subject = pick_subject()
    html, text = build_email_html()
    success = send_email(subject, html, text)

    if success:
        print(f"Pester email sent: {subject}")
        # Log that we sent it
        config = load_config()
        log_path = os.path.join(config["paths"]["data"], "weekly-updates", "pester-log.json")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        log = []
        if os.path.exists(log_path):
            try:
                with open(log_path) as f:
                    log = json.load(f)
            except (json.JSONDecodeError, IOError):
                log = []
        log.append({
            "date": datetime.now(timezone.utc).isoformat(),
            "week": get_week_label(),
            "subject": subject,
        })
        with open(log_path, "w") as f:
            json.dump(log, f, indent=2)
            f.write("\n")
    else:
        print("Failed to send pester email", file=sys.stderr)
        sys.exit(1)


def main():
    if "--dry-run" in sys.argv:
        subject = pick_subject()
        html, text = build_email_html()
        print(f"Subject: {subject}")
        print(f"\n--- TEXT VERSION ---\n{text}")
        print(f"\n--- HTML VERSION ---\n{html}")
        return

    # Check if update already exists (no need to pester)
    config = load_config()
    data_dir = config["paths"]["data"]
    if update_exists(data_dir):
        week_label = get_week_label()
        print(f"Update already exists for {week_label}. No pestering needed.")
        return

    send_pester_email()


if __name__ == "__main__":
    main()
