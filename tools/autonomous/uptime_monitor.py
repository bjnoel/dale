#!/usr/bin/env python3
"""
Uptime monitor for Dale's websites.
Checks treestock.com.au and walkthrough.au every 5 minutes.
Sends email via Resend when a site goes down or recovers.
State is tracked in /opt/dale/data/uptime_state.json to avoid alert spam.
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.request
import urllib.error
import socket
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/opt/dale/autonomous")
from notify import send_email

STATE_PATH = "/opt/dale/data/uptime_state.json"

CHECKS = [
    {
        "name": "treestock.com.au",
        "url": "https://treestock.com.au",
        "id": "treestock",
    },
    {
        "name": "walkthrough.au",
        "url": "https://walkthrough.au",
        "id": "walkthrough",
    },
    {
        "name": "Subscribe API",
        "url": "https://treestock.com.au/api/subscribe",
        "id": "subscribe_api",
        # Server only handles POST; GET to /subscribe returns 404 (working as designed)
        "expected_status": [200, 400, 404, 405],
    },
]

TIMEOUT = 15  # seconds

# --- Disk-space monitoring -------------------------------------------------
# A full disk silently truncates scraper snapshots (corrupting the dataset) and
# crashes the digest builder. On 2026-07-04 the root FS sat at 100% for ~10 days
# undetected because this monitor only checked HTTP endpoints. The thresholds
# below give days of lead time on the 38 GB VPS.
# See memory/project_server_disk_clickhouse.md for the runbook.
DISK_PATH = "/"
DISK_WARN_PCT = 85       # first heads-up
DISK_CRIT_PCT = 93       # urgent
DISK_RECOVER_PCT = 80    # hysteresis: only clear the alert once back below this
_SEVERITY = {"ok": 0, "warning": 1, "critical": 2}

# Reboot-required monitoring (DAL-282). unattended-upgrades installs kernel and
# libc patches; only a reboot activates them. On 2026-08-13 the box had been up
# 161 days running 6.8.0-90 with 6.8.0-124 installed, and reboot-required had
# been set since 11 June. Zero packages pending from the security pocket, so
# every existing signal read green while the live posture was March's.
#
# monthly_maintenance.py now reboots on the first Monday of each month, so this
# check is the backstop for that cadence failing rather than the primary fix.
# The thresholds are set accordingly: the longest possible gap between first
# Mondays is 35 days, so 40 fires only when a window was actually missed, not
# every month. /var/run is tmpfs, so the file cannot survive a reboot and its
# mtime is a trustworthy "set at".
REBOOT_REQUIRED_PATH = "/var/run/reboot-required"
REBOOT_WARN_DAYS = 40
REBOOT_CRIT_DAYS = 75

# Stale apt index. Found while fixing the above: an `apt-get -qq -y update`
# started by apt.systemd.daily on 24 June was still running 48 days later, four
# https methods stuck on sockets, holding /var/lib/apt/lists/lock the whole
# time. unattended-upgrades therefore installed nothing after 24 June, and the
# "0 packages pending from -security" that made the box look current was read
# off a two-month-old index. On a fresh index it was 142 upgradable, 83 of them
# security.
#
# This is the same failure shape as the reboot gap, one layer further down:
# every visible signal reported success and the effect had stopped happening.
# apt.systemd.daily runs daily, so 3 days is already anomalous and 10 means
# nobody is coming.
APT_SUCCESS_STAMP = "/var/lib/apt/periodic/update-success-stamp"
APT_STALE_WARN_DAYS = 3
APT_STALE_CRIT_DAYS = 10

# Repo divergence. git_sync.sh should heal a rejected push within the hour, so
# anything still unpushed after this long means the self-heal itself failed and
# the next session's pull is about to start failing.
#
# On 2026-08-13 a stranded commit sat for 50 minutes and was found by accident;
# three failed sessions would have halted Dale entirely. One hour is inside that
# window and outside the normal push-retry path.
GIT_REPO_PATH = "/opt/dale/repo"
GIT_AHEAD_ALERT_HOURS = 1

# Certificate expiry (DEC-289). stock.scion.exchange's origin certificate expired
# and Caddy retried for eight days across 53 attempts, fell back to the Let's
# Encrypt staging CA, and would have given up at thirty. Every check in this file
# stayed green the whole time, because the hostname kept returning 200: Cloudflare
# was serving cache in front of a dead origin. It was found by accident during an
# audit for an unrelated ticket.
#
# Caddy begins renewing around thirty days out, so twenty-one days remaining means
# renewal has already been failing for about a week. Seven is the point where a
# human has to act before it breaks in public.
#
# Hostnames come from Caddy's own admin API rather than a list here. A hardcoded
# list is exactly the drift DAL-281 existed to remove, and a certificate monitor
# that silently stops covering a new hostname is worse than none.
CADDY_ADMIN_SERVERS_URL = "http://127.0.0.1:2019/config/apps/http/servers"
CERT_WARN_DAYS = 21
CERT_CRIT_DAYS = 7
CERT_RECOVER_DAYS = 25   # hysteresis: only clear once comfortably renewed


def load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        # Corrupt or empty state file — treat as fresh start; next save_state() rewrites it.
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def check_url(check):
    url = check["url"]
    expected = check.get("expected_status", [200, 301, 302])
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "Dale-UptimeMonitor/1.0")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status = resp.status
            if status in expected:
                return True, status, None
            else:
                return False, status, f"Unexpected status {status}"
    except urllib.error.HTTPError as e:
        if e.code in expected:
            return True, e.code, None
        return False, e.code, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, None, str(e.reason)
    except socket.timeout:
        return False, None, f"Timeout after {TIMEOUT}s"
    except Exception as e:
        return False, None, str(e)


def format_down_email(check, error, down_since):
    name = check["name"]
    url = check["url"]
    return f"""
<h2>⚠️ Site Down: {name}</h2>
<p><strong>URL:</strong> <a href="{url}">{url}</a></p>
<p><strong>Error:</strong> {error}</p>
<p><strong>Down since:</strong> {down_since}</p>
<p>Dale's uptime monitor will notify you when it recovers.</p>
""".strip(), f"Site Down: {name}\n\nURL: {url}\nError: {error}\nDown since: {down_since}"


def format_recovered_email(check, down_since, now):
    name = check["name"]
    url = check["url"]
    try:
        ds = datetime.fromisoformat(down_since)
        duration = now - ds
        mins = int(duration.total_seconds() / 60)
        duration_str = f"{mins} minutes" if mins < 120 else f"{mins // 60} hours {mins % 60} minutes"
    except Exception:
        duration_str = "unknown duration"
    return f"""
<h2>✅ Site Recovered: {name}</h2>
<p><strong>URL:</strong> <a href="{url}">{url}</a></p>
<p><strong>Was down since:</strong> {down_since}</p>
<p><strong>Downtime duration:</strong> {duration_str}</p>
""".strip(), f"Site Recovered: {name}\n\nURL: {url}\nDown for: {duration_str}"


def disk_level(pct):
    """Pure: map a used-percentage to an alert level."""
    if pct >= DISK_CRIT_PCT:
        return "critical"
    if pct >= DISK_WARN_PCT:
        return "warning"
    return "ok"


def disk_alert_decision(prev_level, pct):
    """Pure: decide what to do given the previously-alerted level and current % used.

    Returns (new_level, action) where action is one of:
      "alert"     — severity increased (ok->warning, ok/warning->critical); email.
      "recovered" — dropped back below the recover threshold; send an all-clear.
      "none"      — nothing worth emailing (including silent de-escalation).

    Hysteresis: once alerting, we don't clear to "ok" until usage falls below
    DISK_RECOVER_PCT, so usage hovering around the warn line doesn't flap.
    """
    level = disk_level(pct)
    if level == "ok" and prev_level != "ok" and pct >= DISK_RECOVER_PCT:
        level = prev_level  # hold the alert; not recovered yet
    if _SEVERITY[level] > _SEVERITY.get(prev_level, 0):
        return level, "alert"
    if level == "ok" and prev_level != "ok":
        return level, "recovered"
    return level, "none"


def format_disk_email(level, pct, used_gb, total_gb, free_gb):
    icon = "🔴" if level == "critical" else "⚠️"
    html = f"""
<h2>{icon} Disk {level}: {pct:.0f}% used on the Dale server</h2>
<p><strong>Filesystem {DISK_PATH}:</strong> {used_gb:.1f} GB used of {total_gb:.1f} GB
({pct:.0f}%), {free_gb:.1f} GB free.</p>
<p>A full disk silently truncates scraper snapshots and crashes the digest builder,
so act before it reaches 100%. Common culprits: Plausible ClickHouse internal log
tables (system.text_log), ClickHouse server logs, and old weekly backups in
/opt/dale/backups.</p>
<p>Runbook: memory/project_server_disk_clickhouse.md in the repo.</p>
""".strip()
    text = (f"Disk {level}: {pct:.0f}% used on the Dale server\n\n"
            f"{DISK_PATH}: {used_gb:.1f} GB used of {total_gb:.1f} GB "
            f"({pct:.0f}%), {free_gb:.1f} GB free.\n"
            f"Culprits: ClickHouse system.text_log, ClickHouse logs, old /opt/dale/backups.\n"
            f"Runbook: memory/project_server_disk_clickhouse.md")
    return html, text


def format_disk_recovered_email(pct, free_gb):
    html = (f"<h2>✅ Disk recovered: {pct:.0f}% used</h2>"
            f"<p>Free space is back to {free_gb:.1f} GB on {DISK_PATH}.</p>")
    text = f"Disk recovered: {pct:.0f}% used, {free_gb:.1f} GB free on {DISK_PATH}."
    return html, text


def check_disk(state, now_str):
    """Check root-filesystem usage; alert on threshold crossings.

    Mirrors the URL checks: de-dupes via state["disk"], and on a failed send keeps
    the previous level so the alert is retried next run. Returns True (state always
    updated with the latest reading).
    """
    try:
        usage = shutil.disk_usage(DISK_PATH)
    except Exception as e:
        print(f"[{now_str}] DISK: check failed: {e}")
        return False

    total_gb = usage.total / 1e9
    free_gb = usage.free / 1e9
    used_gb = total_gb - free_gb
    pct = (usage.total - usage.free) / usage.total * 100

    prev_level = state.get("disk", {}).get("level", "ok")
    new_level, action = disk_alert_decision(prev_level, pct)
    committed_level = new_level

    if action == "alert":
        html, text = format_disk_email(new_level, pct, used_gb, total_gb, free_gb)
        icon = "🔴" if new_level == "critical" else "⚠️"
        try:
            send_email(f"{icon} Disk {new_level}: {pct:.0f}% on Dale server", html, text)
            print(f"[{now_str}] DISK {new_level.upper()}: {pct:.0f}% used — alert sent")
        except Exception as e:
            committed_level = prev_level  # keep prev level so we retry next run
            print(f"[{now_str}] DISK {new_level.upper()}: {pct:.0f}% used — failed to send alert: {e}")
    elif action == "recovered":
        html, text = format_disk_recovered_email(pct, free_gb)
        try:
            send_email(f"✅ Disk recovered: {pct:.0f}% on Dale server", html, text)
            print(f"[{now_str}] DISK RECOVERED: {pct:.0f}% used — alert sent")
        except Exception as e:
            committed_level = prev_level  # retry the all-clear next run
            print(f"[{now_str}] DISK RECOVERED: {pct:.0f}% used — failed to send alert: {e}")
    else:
        print(f"[{now_str}] DISK {new_level.upper()}: {pct:.0f}% used ({free_gb:.1f}GB free)")

    state["disk"] = {"level": committed_level, "pct": round(pct, 1), "last_checked": now_str}
    return True


def git_divergence_decision(prev_alerted, ahead, oldest_age_hours):
    """Pure: decide what to do about unpushed commits in the server repo.

    Returns (now_alerted, action) where action is "alert", "recovered" or "none".

    A repo briefly ahead of origin is completely normal: every session and every
    inbound merge commits before it pushes. Only a repo that is *still* ahead an
    hour later indicates the push path has failed, which is the state that
    breaks every subsequent pull.
    """
    if ahead == 0:
        return False, ("recovered" if prev_alerted else "none")
    if oldest_age_hours >= GIT_AHEAD_ALERT_HOURS:
        return True, ("none" if prev_alerted else "alert")
    return prev_alerted, "none"


def _git(*args):
    """Run git in the server repo. Returns stdout, or None on any failure."""
    try:
        result = subprocess.run(
            ["git", "-C", GIT_REPO_PATH, *args],
            capture_output=True, text=True, timeout=60,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def format_git_email(ahead, oldest_age_hours, subjects):
    listed = "".join(f"<li><code>{s}</code></li>" for s in subjects[:5])
    html = f"""
<h2>⚠️ /opt/dale/repo has been ahead of origin for {oldest_age_hours:.1f} hours</h2>
<p><strong>{ahead} unpushed commit(s).</strong> A push has failed and did not
self-heal.</p>
<ul>{listed}</ul>
<p>This matters more than it looks. Autonomous Dale's hourly session pulls before
it runs; a diverged repo makes that pull fail, which logs a failure, and three
consecutive failures trip the circuit breaker and halt Dale entirely.</p>
<p><strong>Fix:</strong> <code>cd /opt/dale/repo &amp;&amp; git rebase origin/main
&amp;&amp; git push origin main</code>. If the rebase conflicts, resolve it by
hand: the decision log is append-only, so keep both entries and renumber the one
that has not reached origin.</p>
""".strip()
    text = (f"/opt/dale/repo is {ahead} commit(s) ahead of origin, oldest "
            f"{oldest_age_hours:.1f}h old. A push failed and did not self-heal. "
            f"The next autonomous session's pull will fail; three failures halt Dale. "
            f"Fix: cd /opt/dale/repo && git rebase origin/main && git push origin main")
    return html, text


def check_git_divergence(state, now_str):
    """Alert when the repo has held unpushed commits for over an hour.

    The failure this catches is silent by construction: everything stays healthy,
    the sites stay up, and the only symptom is automation quietly stopping an
    hour later. Mirrors check_disk: de-dupes via state, and on a failed send
    keeps the previous flag so the alert retries.
    """
    if not os.path.isdir(os.path.join(GIT_REPO_PATH, ".git")):
        return False

    # --no-write-fetch-head: this monitor runs every five minutes in the same
    # repo the hourly session pulls in, and both land on :00. A fetch truncates
    # .git/FETCH_HEAD on start and appends on arrival, so this one used to leave
    # a second "for-merge" line in the file the session's `git pull` was about to
    # read, and the pull died with "Cannot fast-forward to multiple branches".
    # Three of those halted Dale on 2026-08-17 (DEC-299). Only origin/main is
    # read below, so writing FETCH_HEAD at all was never anything but a hazard.
    if _git("fetch", "-q", "--no-write-fetch-head", "origin") is None:
        print(f"[{now_str}] GIT: fetch failed, skipping divergence check")
        return False

    log = _git("log", "origin/main..HEAD", "--format=%ct\t%s")
    if log is None:
        print(f"[{now_str}] GIT: could not read divergence")
        return False

    lines = [l for l in log.split("\n") if l.strip()]
    ahead = len(lines)
    subjects = [l.split("\t", 1)[1] for l in lines if "\t" in l]

    oldest_age_hours = 0.0
    if lines:
        try:
            oldest_ts = min(int(l.split("\t", 1)[0]) for l in lines)
            oldest_age_hours = (
                datetime.now(timezone.utc) - datetime.fromtimestamp(oldest_ts, timezone.utc)
            ).total_seconds() / 3600
        except (ValueError, IndexError):
            oldest_age_hours = GIT_AHEAD_ALERT_HOURS  # unreadable timestamp, assume stale

    prev_alerted = state.get("git", {}).get("alerted", False)
    now_alerted, action = git_divergence_decision(prev_alerted, ahead, oldest_age_hours)
    committed = now_alerted

    if action == "alert":
        html, text = format_git_email(ahead, oldest_age_hours, subjects)
        try:
            send_email(f"⚠️ Dale repo stuck: {ahead} unpushed commit(s)", html, text)
            print(f"[{now_str}] GIT: {ahead} unpushed, {oldest_age_hours:.1f}h old — alert sent")
        except Exception as e:
            committed = prev_alerted  # retry next run
            print(f"[{now_str}] GIT: {ahead} unpushed — failed to send alert: {e}")
    elif action == "recovered":
        try:
            send_email("✅ Dale repo back in sync with origin",
                       "<h2>✅ /opt/dale/repo is back in sync with origin/main.</h2>",
                       "/opt/dale/repo is back in sync with origin/main.")
            print(f"[{now_str}] GIT RECOVERED: in sync — alert sent")
        except Exception as e:
            committed = prev_alerted
            print(f"[{now_str}] GIT RECOVERED: failed to send alert: {e}")
    else:
        print(f"[{now_str}] GIT: {ahead} unpushed ({oldest_age_hours:.1f}h old)")

    state["git"] = {"alerted": committed, "ahead": ahead, "last_checked": now_str}
    return True


def reboot_level(age_days):
    """Pure: map the age of /var/run/reboot-required to an alert level."""
    if age_days >= REBOOT_CRIT_DAYS:
        return "critical"
    if age_days >= REBOOT_WARN_DAYS:
        return "warning"
    return "ok"


def reboot_alert_decision(prev_level, age_days):
    """Pure: decide what to do given the previously-alerted level and the age in
    days of /var/run/reboot-required. `age_days` is None when no reboot is
    pending.

    Returns (new_level, action) with the same vocabulary as
    disk_alert_decision: "alert", "recovered", or "none".

    No hysteresis here, unlike disk: the age only ever increases, and the file
    vanishing is unambiguous. Recovery therefore means "someone rebooted".
    """
    if age_days is None:
        return "ok", ("recovered" if prev_level != "ok" else "none")
    level = reboot_level(age_days)
    if _SEVERITY[level] > _SEVERITY.get(prev_level, 0):
        return level, "alert"
    return level, "none"


def format_reboot_email(level, age_days, since_str, packages):
    icon = "🔴" if level == "critical" else "⚠️"
    listed = "".join(f"<li><code>{p}</code></li>" for p in packages[:10])
    more = f"<p>...and {len(packages) - 10} more.</p>" if len(packages) > 10 else ""
    html = f"""
<h2>{icon} Reboot pending for {age_days:.0f} days on the Dale server</h2>
<p><code>/var/run/reboot-required</code> has been set since <strong>{since_str}</strong>.
The monthly maintenance window should have cleared this, so the cadence itself
has failed.</p>
<p>This is the failure that hides: patches are installed, apt reports nothing
pending, every dashboard reads green, and the running kernel is still the old
one. Packages waiting on a reboot:</p>
<ul>{listed}</ul>{more}
<p><strong>Fix:</strong> <code>sudo /usr/bin/python3
/opt/dale/autonomous/monthly_maintenance.py --run --force</code>, or check why
the Sunday 18:30 UTC cron did not fire (a stale <code>locks/no-reboot</code>
veto file is the first thing to look at).</p>
<p>Runbook: docs/server-maintenance.md in the repo.</p>
""".strip()
    text = (f"Reboot pending for {age_days:.0f} days on the Dale server.\n\n"
            f"/var/run/reboot-required set since {since_str}.\n"
            f"Packages waiting: {', '.join(packages[:10])}"
            f"{f' and {len(packages) - 10} more' if len(packages) > 10 else ''}\n\n"
            f"The monthly maintenance window should have cleared this, so the "
            f"cadence has failed. Check for a stale locks/no-reboot veto file.\n"
            f"Fix: sudo python3 /opt/dale/autonomous/monthly_maintenance.py --run --force\n"
            f"Runbook: docs/server-maintenance.md")
    return html, text


def read_reboot_required():
    """(age_in_days, since_str, packages) or (None, None, []) when none pending."""
    try:
        mtime = os.path.getmtime(REBOOT_REQUIRED_PATH)
    except OSError:
        return None, None, []
    since = datetime.fromtimestamp(mtime, timezone.utc)
    age_days = (datetime.now(timezone.utc) - since).total_seconds() / 86400
    try:
        with open(REBOOT_REQUIRED_PATH + ".pkgs") as f:
            packages = sorted({line.strip() for line in f if line.strip()})
    except OSError:
        packages = []
    return age_days, since.strftime("%Y-%m-%d %H:%M UTC"), packages


def check_reboot_required(state, now_str):
    """Alert when installed kernel/libc patches have sat unactivated too long.

    Mirrors check_disk: de-dupes via state["reboot"], and on a failed send keeps
    the previous level so the alert is retried next run.
    """
    age_days, since_str, packages = read_reboot_required()

    prev_level = state.get("reboot", {}).get("level", "ok")
    new_level, action = reboot_alert_decision(prev_level, age_days)
    committed_level = new_level

    if action == "alert":
        html, text = format_reboot_email(new_level, age_days, since_str, packages)
        icon = "🔴" if new_level == "critical" else "⚠️"
        try:
            send_email(f"{icon} Reboot pending {age_days:.0f} days on Dale server", html, text)
            print(f"[{now_str}] REBOOT {new_level.upper()}: pending {age_days:.0f}d — alert sent")
        except Exception as e:
            committed_level = prev_level  # retry next run
            print(f"[{now_str}] REBOOT {new_level.upper()}: pending {age_days:.0f}d — "
                  f"failed to send alert: {e}")
    elif action == "recovered":
        try:
            send_email("✅ Dale server reboot no longer pending",
                       "<h2>✅ /var/run/reboot-required is clear.</h2>"
                       "<p>The installed kernel and libc patches are now the ones "
                       "actually running.</p>",
                       "/var/run/reboot-required is clear. Installed patches are now active.")
            print(f"[{now_str}] REBOOT RECOVERED: no reboot pending — alert sent")
        except Exception as e:
            committed_level = prev_level  # retry the all-clear next run
            print(f"[{now_str}] REBOOT RECOVERED: failed to send alert: {e}")
    else:
        pending = f"pending {age_days:.0f}d" if age_days is not None else "none pending"
        print(f"[{now_str}] REBOOT {new_level.upper()}: {pending}")

    state["reboot"] = {
        "level": committed_level,
        "age_days": round(age_days, 1) if age_days is not None else None,
        "last_checked": now_str,
    }
    return True


def apt_stale_level(age_days):
    """Pure: map the age of the last successful apt-get update to a level."""
    if age_days is None or age_days >= APT_STALE_CRIT_DAYS:
        return "critical"
    if age_days >= APT_STALE_WARN_DAYS:
        return "warning"
    return "ok"


def apt_stale_decision(prev_level, age_days):
    """Pure: same vocabulary as disk_alert_decision.

    `age_days` is None when the stamp has never been written, which is treated
    as critical rather than ok: "no evidence apt has ever succeeded" is the
    worse reading, and assuming the friendlier one is what let this sit for
    seven weeks.
    """
    level = apt_stale_level(age_days)
    if _SEVERITY[level] > _SEVERITY.get(prev_level, 0):
        return level, "alert"
    if level == "ok" and prev_level != "ok":
        return level, "recovered"
    return level, "none"


def apt_index_age_days():
    """Days since the last successful apt-get update, or None if never."""
    try:
        mtime = os.path.getmtime(APT_SUCCESS_STAMP)
    except OSError:
        return None
    return (datetime.now(timezone.utc)
            - datetime.fromtimestamp(mtime, timezone.utc)).total_seconds() / 86400


def format_apt_stale_email(level, age_days):
    icon = "🔴" if level == "critical" else "⚠️"
    age = "never" if age_days is None else f"{age_days:.0f} days ago"
    html = f"""
<h2>{icon} apt has not successfully updated its index since {age}</h2>
<p><code>{APT_SUCCESS_STAMP}</code> is stale. <code>apt.systemd.daily</code> runs
daily and only touches that stamp on success, so this means the refresh is
failing or wedged.</p>
<p><strong>Why this matters more than it reads.</strong> While the index is
stale, unattended-upgrades installs nothing new and <code>apt list
--upgradable</code> reports against a frozen snapshot. The box then reports
zero pending security updates because it has not looked, which is
indistinguishable from being up to date.</p>
<p><strong>First thing to check:</strong> a hung update still holding the lock.
<code>pgrep -a apt-get</code> — on 2026-08-13 one had been running for 48 days
with its https methods stuck on sockets. Kill the tree, then
<code>sudo apt-get -o Acquire::http::Timeout=30 update</code>.</p>
<p>Runbook: docs/server-maintenance.md in the repo.</p>
""".strip()
    text = (f"apt has not successfully updated its index since {age}.\n\n"
            f"{APT_SUCCESS_STAMP} is stale. While it is, unattended-upgrades "
            f"installs nothing and 'apt list --upgradable' reports against a "
            f"frozen snapshot, so the box reports zero pending security updates "
            f"because it has not looked.\n\n"
            f"Check for a hung update holding the lock: pgrep -a apt-get\n"
            f"Then: sudo apt-get -o Acquire::http::Timeout=30 update\n"
            f"Runbook: docs/server-maintenance.md")
    return html, text


def check_apt_freshness(state, now_str):
    """Alert when apt's package index has stopped refreshing.

    Mirrors check_disk: de-duped via state["apt"], previous level retained on a
    failed send so the alert retries.
    """
    age_days = apt_index_age_days()
    prev_level = state.get("apt", {}).get("level", "ok")
    new_level, action = apt_stale_decision(prev_level, age_days)
    committed_level = new_level
    age_str = "never" if age_days is None else f"{age_days:.1f}d"

    if action == "alert":
        html, text = format_apt_stale_email(new_level, age_days)
        icon = "🔴" if new_level == "critical" else "⚠️"
        try:
            send_email(f"{icon} apt index stale on Dale server ({age_str})", html, text)
            print(f"[{now_str}] APT {new_level.upper()}: index {age_str} old — alert sent")
        except Exception as e:
            committed_level = prev_level
            print(f"[{now_str}] APT {new_level.upper()}: index {age_str} old — "
                  f"failed to send alert: {e}")
    elif action == "recovered":
        try:
            send_email("✅ apt index refreshing again on Dale server",
                       "<h2>✅ apt has successfully updated its index.</h2>"
                       "<p>unattended-upgrades can see current packages again.</p>",
                       "apt has successfully updated its index. unattended-upgrades "
                       "can see current packages again.")
            print(f"[{now_str}] APT RECOVERED: index {age_str} old — alert sent")
        except Exception as e:
            committed_level = prev_level
            print(f"[{now_str}] APT RECOVERED: failed to send alert: {e}")
    else:
        print(f"[{now_str}] APT {new_level.upper()}: index {age_str} old")

    state["apt"] = {
        "level": committed_level,
        "age_days": round(age_days, 1) if age_days is not None else None,
        "last_checked": now_str,
    }
    return True


def caddy_hostnames(config):
    """Pure: every host matcher in Caddy's server config, deduped and sorted.

    Walks the whole structure rather than assuming a shape, because the JSON Caddy
    generates from a Caddyfile nests differently depending on how many matchers and
    subroutes a site block has.
    """
    found = set()

    def walk(node):
        if isinstance(node, dict):
            hosts = node.get("host")
            if isinstance(hosts, list):
                found.update(h for h in hosts if isinstance(h, str))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(config)
    return sorted(found)


def parse_not_after(openssl_output):
    """Pure: 'notAfter=Nov 11 03:22:04 2026 GMT' -> aware datetime, or None."""
    for line in (openssl_output or "").splitlines():
        line = line.strip()
        if not line.startswith("notAfter="):
            continue
        raw = line.split("=", 1)[1].strip()
        try:
            return datetime.strptime(raw, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def cert_days_remaining(not_after, now):
    """Pure: days until expiry. Negative once expired. None if unknown."""
    if not_after is None:
        return None
    return (not_after - now).total_seconds() / 86400.0


def cert_level(days):
    """Pure: map days-remaining to an alert level.

    Unreadable (None) is critical, not unknown. The failure this monitor exists to
    catch presented exactly that way: the origin could not complete a handshake at
    all, so there was no certificate to read. Treating that as "no data" would skip
    the one case worth alerting on.
    """
    if days is None or days <= CERT_CRIT_DAYS:
        return "critical"
    if days <= CERT_WARN_DAYS:
        return "warning"
    return "ok"


def cert_alert_decision(prev_level, days):
    """Pure: same contract as disk_alert_decision, thresholds running the other way.

    Hysteresis holds an existing alert until the certificate is comfortably renewed
    (CERT_RECOVER_DAYS), so a cert sitting near the warn line does not flap an
    all-clear and a fresh warning at each run.
    """
    level = cert_level(days)
    if level == "ok" and prev_level != "ok" and days is not None and days < CERT_RECOVER_DAYS:
        level = prev_level  # renewed, but not far enough clear to call it recovered
    if _SEVERITY[level] > _SEVERITY.get(prev_level, 0):
        return level, "alert"
    if level == "ok" and prev_level != "ok":
        return level, "recovered"
    return level, "none"


def format_cert_email(level, offenders):
    """offenders: list of (hostname, days) worst first. days None means unreadable."""
    icon = "🔴" if level == "critical" else "⚠️"

    def describe(host, days):
        if days is None:
            return f"{host}: certificate could not be read at the origin"
        if days < 0:
            return f"{host}: EXPIRED {abs(days):.0f} days ago"
        return f"{host}: {days:.0f} days remaining"

    rows = "".join(f"<li>{describe(h, d)}</li>" for h, d in offenders)
    html = f"""
<h2>{icon} Certificate {level}: {len(offenders)} hostname(s) on the Dale server</h2>
<ul>{rows}</ul>
<p>This is measured at the origin (127.0.0.1 with SNI), not through Cloudflare. A
proxied hostname keeps serving Cloudflare's own valid certificate while the origin's
is dead, which is how stock.scion.exchange failed for eight days with every check
green.</p>
<p>Most likely cause: the hostname is Cloudflare-proxied, so neither ACME challenge
can complete. http-01 gets answered by the edge and tls-alpn-01 cannot negotiate.
Fix is to set the DNS record to DNS-only (grey cloud), then
<code>sudo systemctl restart caddy</code>. A reload is not enough; the existing
multi-hour backoff keeps running.</p>
<p>Runbook: memory/project_caddy_acme_needs_grey_cloud.md. Confirm recovery by
checking the issuer is acme-v02 and not acme-staging-v02.</p>
""".strip()
    text = (f"Certificate {level} on the Dale server\n\n"
            + "\n".join(describe(h, d) for h, d in offenders)
            + "\n\nMeasured at the origin, not through Cloudflare.\n"
              "Likely cause: hostname is Cloudflare-proxied so ACME cannot complete.\n"
              "Fix: grey-cloud the DNS record, then sudo systemctl restart caddy.\n"
              "Runbook: memory/project_caddy_acme_needs_grey_cloud.md")
    return html, text


def format_cert_recovered_email(worst_host, days):
    html = (f"<h2>✅ Certificates recovered</h2>"
            f"<p>All Caddy hostnames are comfortably valid again; the nearest expiry is "
            f"{worst_host} at {days:.0f} days.</p>")
    text = (f"Certificates recovered. Nearest expiry is {worst_host} at {days:.0f} days.")
    return html, text


def fetch_caddy_hostnames(timeout=10):
    """Ask Caddy what it is actually serving. Returns [] if the admin API is unreachable."""
    try:
        with urllib.request.urlopen(CADDY_ADMIN_SERVERS_URL, timeout=timeout) as response:
            return caddy_hostnames(json.load(response))
    except Exception:
        return []


def read_cert_not_after(hostname, timeout=15):
    """The origin's certificate expiry for `hostname`, or None if it cannot be read.

    Connects to 127.0.0.1 with SNI rather than to the public name on purpose: for a
    Cloudflare-proxied hostname a public connection returns Cloudflare's certificate,
    which stayed valid throughout the outage this check exists to detect.

    Verification is not performed, because an expired certificate is the thing being
    reported and must not become an exception that prevents reading it.
    """
    try:
        handshake = subprocess.run(
            ["openssl", "s_client", "-servername", hostname, "-connect", "127.0.0.1:443"],
            input="", capture_output=True, text=True, timeout=timeout,
        )
    except Exception:
        return None

    out = handshake.stdout or ""
    start = out.find("-----BEGIN CERTIFICATE-----")
    end = out.find("-----END CERTIFICATE-----")
    if start == -1 or end == -1:
        return None
    pem = out[start:end + len("-----END CERTIFICATE-----")] + "\n"

    try:
        parsed = subprocess.run(
            ["openssl", "x509", "-noout", "-enddate"],
            input=pem, capture_output=True, text=True, timeout=timeout,
        )
    except Exception:
        return None

    return parse_not_after(parsed.stdout)


def check_certs(state, now_str, now=None):
    """Alert when any Caddy-served hostname's origin certificate is near expiry.

    One email for all offenders rather than one per hostname: these fail together,
    since the usual cause is a zone-level DNS posture rather than a single cert.
    """
    now = now or datetime.now(timezone.utc)
    hostnames = fetch_caddy_hostnames()
    if not hostnames:
        print(f"[{now_str}] CERTS: could not read hostnames from Caddy admin API, skipped")
        return False

    readings = []
    for hostname in hostnames:
        days = cert_days_remaining(read_cert_not_after(hostname), now)
        readings.append((hostname, days))

    # Worst first: unreadable ranks above expired ranks above merely near.
    readings.sort(key=lambda r: (r[1] is not None, r[1]))
    worst_host, worst_days = readings[0]

    prev_level = state.get("certs", {}).get("level", "ok")
    new_level, action = cert_alert_decision(prev_level, worst_days)
    committed_level = new_level

    offenders = [(h, d) for h, d in readings if cert_level(d) != "ok"]

    if action == "alert":
        html, text = format_cert_email(new_level, offenders)
        icon = "🔴" if new_level == "critical" else "⚠️"
        try:
            send_email(f"{icon} Certificate {new_level}: {worst_host} on Dale server", html, text)
            print(f"[{now_str}] CERTS {new_level.upper()}: {len(offenders)} offender(s) — alert sent")
        except Exception as e:
            committed_level = prev_level  # keep prev level so we retry next run
            print(f"[{now_str}] CERTS {new_level.upper()}: failed to send alert: {e}")
    elif action == "recovered":
        html, text = format_cert_recovered_email(worst_host, worst_days)
        try:
            send_email("✅ Certificates recovered on Dale server", html, text)
            print(f"[{now_str}] CERTS RECOVERED: nearest {worst_host} {worst_days:.0f}d — alert sent")
        except Exception as e:
            committed_level = prev_level  # retry the all-clear next run
            print(f"[{now_str}] CERTS RECOVERED: failed to send alert: {e}")
    else:
        nearest = "unreadable" if worst_days is None else f"{worst_days:.0f}d"
        print(f"[{now_str}] CERTS {new_level.upper()}: {len(hostnames)} checked, nearest {worst_host} {nearest}")

    state["certs"] = {
        "level": committed_level,
        "nearest_host": worst_host,
        "nearest_days": None if worst_days is None else round(worst_days, 1),
        "last_checked": now_str,
    }
    return True


def main():
    state = load_state()
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()
    changed = False

    for check in CHECKS:
        cid = check["id"]
        is_up, status, error = check_url(check)
        prev = state.get(cid, {"status": "unknown", "alerted": False})

        if is_up:
            if prev.get("status") == "down" and prev.get("alerted"):
                # Recovery — send notification
                html, text = format_recovered_email(check, prev.get("down_since", "unknown"), now)
                try:
                    send_email(f"✅ Recovered: {check['name']}", html, text)
                    print(f"[{now_str}] RECOVERED: {check['name']} — alert sent")
                except Exception as e:
                    print(f"[{now_str}] RECOVERED: {check['name']} — failed to send alert: {e}")
            else:
                print(f"[{now_str}] UP: {check['name']} ({status})")

            state[cid] = {"status": "up", "last_checked": now_str, "alerted": False}
            changed = True

        else:
            if prev.get("status") != "down":
                # Just went down — record it
                state[cid] = {
                    "status": "down",
                    "down_since": now_str,
                    "last_checked": now_str,
                    "error": error,
                    "alerted": False,
                }
                changed = True
                print(f"[{now_str}] DOWN (first detection): {check['name']} — {error}")

            elif not prev.get("alerted"):
                # Still down and haven't alerted yet — send alert
                down_since = prev.get("down_since", now_str)
                html, text = format_down_email(check, error, down_since)
                try:
                    send_email(f"⚠️ Down: {check['name']}", html, text)
                    state[cid]["alerted"] = True
                    state[cid]["last_checked"] = now_str
                    state[cid]["error"] = error
                    changed = True
                    print(f"[{now_str}] DOWN: {check['name']} — alert sent")
                except Exception as e:
                    print(f"[{now_str}] DOWN: {check['name']} — failed to send alert: {e}")
            else:
                # Still down, already alerted
                state[cid]["last_checked"] = now_str
                state[cid]["error"] = error
                changed = True
                print(f"[{now_str}] DOWN (ongoing): {check['name']} — {error}")

    # Disk space — the failure mode HTTP checks can't see (full disk corrupts data silently).
    if check_disk(state, now_str):
        changed = True

    # Repo divergence — the other invisible failure: sites stay up, disk is fine,
    # and automation silently stops an hour later.
    if check_git_divergence(state, now_str):
        changed = True

    # Reboot pending — the third invisible failure: patches installed, apt clean,
    # every signal green, and the running kernel still the old one.
    if check_reboot_required(state, now_str):
        changed = True

    # Stale apt index — the fourth, and the one that fakes all the others: with
    # a frozen index the box reports zero pending security updates because it
    # has not looked.
    if check_apt_freshness(state, now_str):
        changed = True

    # Certificate expiry — the fifth invisible failure, and the one that hid behind
    # a 200. The origin's cert was dead for eight days while the URL check above
    # reported the site up, because Cloudflare was serving cache in front of it.
    if check_certs(state, now_str, now):
        changed = True

    if changed:
        save_state(state)


if __name__ == "__main__":
    main()
