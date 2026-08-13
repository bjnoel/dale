#!/usr/bin/env python3
"""Monthly server maintenance: announce, apply, reboot, verify.

Why this exists (DAL-282, DEC-290). unattended-upgrades had been working
perfectly for five months and the box had never acted on it: uptime 161 days,
running kernel 6.8.0-90 with 6.8.0-124 installed and unbooted, seven kernels
and libc6 patched on disk and inert in memory, reboot-required set since
2026-06-11. Zero packages pending from the security pocket, so every dashboard
read green while the actual security posture was March's.

A one-off reboot restores exactly the state that then decayed for nine weeks.
So the cadence is built so that the *default outcome is that it happens*:

  --announce   Saturday 09:00 AWST, two days ahead. Says what will be applied
               and how to stop it.
  --run        First Monday of the month, 02:30 AWST. Applies apt updates,
               refreshes the pinned Docker tags, reboots. Skipped only if
               someone actively vetoed it.
  --verify     On boot. Checks the box came back, then emails the result.

Nobody is surprised by a reboot, but nobody has to remember to act for the
right thing to happen. That distinction is the whole ticket.

Cron lines live in docs/server-maintenance.md. They are all UTC: this box is
Etc/UTC and CRON_TZ is not documented in its crontab(5), so the AWST logic
lives here in pure functions instead, where tests can reach it.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, "/opt/dale/autonomous")
from notify import send_email

PERTH = ZoneInfo("Australia/Perth")

LOCKS_DIR = "/opt/dale/autonomous/locks"
VETO_FILE = os.path.join(LOCKS_DIR, "no-reboot")
SESSION_LOCK = os.path.join(LOCKS_DIR, "session.lock")
REBOOT_REQUIRED_PATH = "/var/run/reboot-required"
# apt.systemd.daily touches this only after a successful update.
APT_SUCCESS_STAMP = "/var/lib/apt/periodic/update-success-stamp"
PLAUSIBLE_DIR = "/opt/dale/plausible"

# How far ahead the announcement goes out. Two days puts it in Saturday
# morning's inbox for a Monday 02:30 window, which is a readable hour and
# leaves a whole weekend to veto.
ANNOUNCE_LEAD_DAYS = 2

# An autonomous session holds locks/session.lock and is capped at 60 minutes,
# so one started at 18:00 UTC can still be live at the 18:30 window. Killing it
# is survivable (dale-runner.sh treats a dead-PID lock as stale, and a stranded
# commit is caught by uptime_monitor's git divergence check within the hour),
# but waiting a few minutes is free.
SESSION_WAIT_SECONDS = 600
SESSION_POLL_SECONDS = 15

# Options every apt call gets, and the reason each one is there.
#
# On 2026-08-13 an `apt-get -qq -y update` fired by apt.systemd.daily was found
# still running after 48 days, with four /usr/lib/apt/methods/https children
# stuck on sockets. It held /var/lib/apt/lists/lock the whole time, so
# unattended-upgrades had installed nothing since 24 June, and the "0 packages
# pending from -security" that made the box look current was a reading off an
# index frozen in June. On a fresh index it was 142 upgradable, 83 of them
# security.
#
# Acquire timeouts stop a wedged mirror connection hanging forever. The lock
# timeout stops the monthly window failing outright just because the daily
# timer happened to be mid-refresh.
APT_OPTS = [
    "-o", "Acquire::http::Timeout=30",
    "-o", "Acquire::https::Timeout=30",
    "-o", "DPkg::Lock::Timeout=300",
]

# Everything that has to be back after a reboot. Checked by --verify.
EXPECTED_UNITS = ["caddy", "docker", "subscribe-server", "gandon-hook"]
EXPECTED_CONTAINERS = [
    "plausible-plausible-1",
    "plausible-plausible_events_db-1",
    "plausible-plausible_db-1",
]
HTTP_CHECKS = [
    ("treestock.com.au", "https://treestock.com.au", [200]),
    # Subscribe server only handles POST; GET is a 404 by design. Same expected
    # set as uptime_monitor.py's subscribe_api check.
    ("subscribe API", "https://treestock.com.au/api/subscribe", [200, 400, 404, 405]),
]


# --- Pure helpers (unit-tested; no I/O) ------------------------------------

def is_first_monday(dt):
    """True when dt (already in Perth time) is the first Monday of its month."""
    return dt.weekday() == 0 and dt.day <= 7


def should_announce(dt, lead_days=ANNOUNCE_LEAD_DAYS):
    """True when the day `lead_days` after dt is the first Monday of its month.

    Called on Saturday mornings; the announcement only fires on the Saturday
    that actually precedes a maintenance window.
    """
    return is_first_monday(dt + timedelta(days=lead_days))


def next_window(dt):
    """The next first-Monday-of-the-month at 02:30 Perth time, at or after dt."""
    probe = dt.replace(hour=2, minute=30, second=0, microsecond=0)
    if probe < dt:
        probe += timedelta(days=1)
    while not is_first_monday(probe):
        probe += timedelta(days=1)
    return probe


def has_work(reboot_required, apt_count):
    """True when a window has anything to do.

    A window with no pending reboot and no pending packages is a no-op, and a
    no-op should not reboot the box or email about it. This is what stops the
    cadence becoming noise in the months where unattended-upgrades had nothing
    to install.
    """
    return bool(reboot_required) or apt_count > 0


def format_window(dt):
    """Both timezones, always. Getting 02:30 AWST Monday = 18:30 UTC Sunday
    wrong by a day is the easiest mistake available here."""
    utc = dt.astimezone(timezone.utc)
    return (f"{dt.strftime('%a %d %b %Y %H:%M')} AWST "
            f"({utc.strftime('%a %d %b %H:%M')} UTC)")


# --- Shell helpers ---------------------------------------------------------

def run(cmd, timeout=1800, check=False):
    """Run a command, returning (returncode, combined output)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        out = (result.stdout or "") + (result.stderr or "")
        if check and result.returncode != 0:
            raise RuntimeError(f"{' '.join(cmd)} exited {result.returncode}: {out[-2000:]}")
        return result.returncode, out.strip()
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"


def log(msg):
    print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}", flush=True)


def running_kernel():
    _, out = run(["uname", "-r"], timeout=30)
    return out


def parse_installed_kernels(dpkg_output):
    """Pure: newest actually-installed kernel from `dpkg-query -W` output.

    The status field is not optional here. A plain glob over
    linux-image-*-generic also returns `rc` packages (removed, config left
    behind) and `un` ones (never installed at all, listed only because
    something once depended on them). On this box that included eight
    `linux-image-unsigned-*` entries at status `un`, and taking the raw name
    yielded "unsigned-6.8.0-124-generic" as the newest kernel -- which would
    have made --verify compare uname -r against a package that does not exist,
    report a false failure after a perfectly good reboot, and skip the
    autoremove forever.
    """
    best = None
    for line in dpkg_output.split("\n"):
        parts = line.split()
        if len(parts) < 2 or not parts[1].startswith("ii"):
            continue
        version = parts[0][len("linux-image-"):]
        if best is None or _kernel_sort_key(version) > _kernel_sort_key(best):
            best = version
    return best


def _kernel_sort_key(name):
    """Ordering key for an Ubuntu kernel ABI name like `6.8.0-124-generic`.

    Numeric, not lexical: `6.8.0-90-generic` sorts *after* `6.8.0-124-generic`
    as a string, which would pick the older kernel as the newer one. Comparing
    the integers is exact for this naming scheme and keeps the function pure --
    shelling out to `dpkg --compare-versions` would make it untestable anywhere
    but the server, which is precisely where a wrong answer is expensive.
    """
    return tuple(int(n) for n in re.findall(r"\d+", name))


def newest_installed_kernel():
    """Highest installed linux-image-*-generic, by dpkg's own version ordering."""
    rc, out = run(["dpkg-query", "-W", "-f=${Package} ${db:Status-Abbrev}\\n",
                   "linux-image-*-generic"], timeout=60)
    if rc != 0 or not out:
        return None
    return parse_installed_kernels(out)


def reboot_required_since():
    """mtime of /var/run/reboot-required, or None. /var/run is tmpfs, so the
    file cannot survive a reboot and its mtime is a trustworthy 'set at'."""
    try:
        return datetime.fromtimestamp(os.path.getmtime(REBOOT_REQUIRED_PATH), timezone.utc)
    except OSError:
        return None


def reboot_required_packages():
    try:
        with open(REBOOT_REQUIRED_PATH + ".pkgs") as f:
            return sorted({line.strip() for line in f if line.strip()})
    except OSError:
        return []


def pending_upgrades():
    """(count, names) of packages a full-upgrade would install.

    Simulates full-upgrade, not upgrade, because full-upgrade is what --run
    actually applies; counting one and applying the other is how an
    announcement quietly stops matching reality.
    """
    rc, out = run(["apt-get"] + APT_OPTS + ["-s", "full-upgrade"], timeout=300)
    if rc != 0:
        return 0, []
    names = [l.split()[1] for l in out.split("\n") if l.startswith("Inst ")]
    return len(names), names


def apt_index_age_days():
    """Days since the last *successful* apt-get update, or None if never.

    apt.systemd.daily writes this stamp only on success, which is exactly the
    signal that was missing when a hung update held the lock for 48 days while
    every other indicator stayed green.
    """
    try:
        mtime = os.path.getmtime(APT_SUCCESS_STAMP)
    except OSError:
        return None
    return (datetime.now(timezone.utc)
            - datetime.fromtimestamp(mtime, timezone.utc)).total_seconds() / 86400


def session_is_live():
    """True when locks/session.lock names a process that still exists."""
    try:
        with open(SESSION_LOCK) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def wait_for_session(max_seconds=SESSION_WAIT_SECONDS, sleep=None):
    """Wait for a live autonomous session to finish. Returns True if clear."""
    import time
    sleep = sleep or time.sleep
    waited = 0
    while session_is_live() and waited < max_seconds:
        log(f"autonomous session still running, waited {waited}s")
        sleep(SESSION_POLL_SECONDS)
        waited += SESSION_POLL_SECONDS
    if session_is_live():
        log("session still running after the wait; proceeding anyway "
            "(a killed session self-heals via the stale-lock path)")
        return False
    return True


def http_status(url, timeout=15):
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "Dale-Maintenance/1.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


# --- Modes -----------------------------------------------------------------

def do_announce(now_perth, dry_run=False, force=False):
    if not (force or should_announce(now_perth)):
        log(f"not the announcement day ({now_perth:%a %d %b}); nothing to do")
        return 0

    window = next_window(now_perth)
    pending, names = pending_upgrades()
    since = reboot_required_since()
    running = running_kernel()
    newest = newest_installed_kernel()

    if not has_work(since, pending):
        log("no reboot pending and no packages to install; staying quiet")
        return 0

    pkgs = reboot_required_packages()
    since_str = f"{since:%Y-%m-%d %H:%M} UTC" if since else "not set"
    sample = ", ".join(names[:8]) + (f" and {pending - 8} more" if pending > 8 else "")

    html = f"""
<h2>🔧 Scheduled server maintenance: {format_window(window)}</h2>
<p>The Dale server will apply updates and reboot at the window above. About two
minutes of downtime: treestock, Plausible, the subscribe API and
gandon-calendar all go with it.</p>
<h3>What will be applied</h3>
<ul>
  <li><strong>Kernel:</strong> running <code>{running}</code>, will boot
      <code>{newest}</code></li>
  <li><strong>Reboot pending since:</strong> {since_str}
      ({len(pkgs)} package(s) waiting on it)</li>
  <li><strong>apt:</strong> {pending} package(s){' — ' + sample if sample else ''}</li>
  <li><strong>Docker:</strong> pinned-tag refresh of the Plausible stack (patch
      rebuilds only, not a version upgrade)</li>
</ul>
<h3>To stop it</h3>
<p><code>touch {VETO_FILE}</code> any time before the window.</p>
<p>The veto is <strong>one-shot on purpose</strong>: it skips this month only and
is deleted when it fires. A veto left in place would recreate exactly the
nine-week gap this cadence exists to close.</p>
<h3>How you will know it worked</h3>
<p>A verification email arrives about ten minutes after the window with the
booted kernel and the state of every service. <strong>If that email does not
arrive, the box did not come back.</strong></p>
""".strip()

    text = (f"Scheduled server maintenance: {format_window(window)}\n\n"
            f"Kernel: running {running}, will boot {newest}\n"
            f"Reboot pending since: {since_str} ({len(pkgs)} packages)\n"
            f"apt: {pending} package(s)\n"
            f"Docker: pinned-tag refresh of the Plausible stack\n\n"
            f"To stop it: touch {VETO_FILE} (one-shot, skips this month only)\n\n"
            f"A verification email arrives ~10 min after the window. "
            f"If it does not arrive, the box did not come back.")

    if dry_run:
        print(text)
        return 0
    send_email(f"🔧 Server maintenance {window:%a %d %b} 02:30 AWST", html, text)
    log("announcement sent")
    return 0


def do_run(now_perth, dry_run=False, force=False):
    if not (force or is_first_monday(now_perth)):
        log(f"not the maintenance window ({now_perth:%a %d %b}); nothing to do")
        return 0

    if os.path.exists(VETO_FILE):
        # Delete before emailing: a veto that survives its own window is the
        # failure mode, and an email that fails to send must not resurrect it.
        os.remove(VETO_FILE)
        log("veto file present: skipping this window, veto cleared")
        try:
            send_email(
                "⏭️ Server maintenance skipped (vetoed)",
                f"<h2>⏭️ Maintenance skipped for {now_perth:%B %Y}</h2>"
                f"<p><code>{VETO_FILE}</code> was present, so nothing was applied "
                f"and the box was not rebooted.</p>"
                f"<p>The veto has been cleared. The next window "
                f"({format_window(next_window(now_perth + timedelta(days=1)))}) "
                f"will proceed normally unless you veto it again.</p>",
                f"Maintenance skipped for {now_perth:%B %Y}: veto file was present. "
                f"Veto cleared; the next window will proceed normally.")
        except Exception as e:
            log(f"veto email failed: {e}")
        return 0

    pending, _ = pending_upgrades()
    since = reboot_required_since()
    if not has_work(since, pending):
        log("no reboot pending and no packages to install; skipping the window")
        return 0

    if dry_run:
        log(f"DRY RUN: would upgrade {pending} package(s), refresh Docker tags, and reboot")
        return 0

    wait_for_session()

    log(f"applying {pending} package upgrade(s)")
    rc, out = run(["sudo", "-n", "apt-get"] + APT_OPTS + ["update"], timeout=900)
    log(f"apt-get update exited {rc}")
    env_prefix = ["sudo", "-n", "env", "DEBIAN_FRONTEND=noninteractive",
                  "NEEDRESTART_MODE=a"]
    rc, out = run(env_prefix + ["apt-get"] + APT_OPTS +
                  ["-y", "-o", "Dpkg::Options::=--force-confdef",
                   "-o", "Dpkg::Options::=--force-confold", "full-upgrade"],
                  timeout=3600)
    log(f"apt-get full-upgrade exited {rc}")
    if rc != 0:
        # Do not reboot on top of a half-applied upgrade.
        send_email("🔴 Server maintenance FAILED at apt stage, no reboot",
                   f"<h2>🔴 apt-get full-upgrade exited {rc}</h2>"
                   f"<p>The box was <strong>not</strong> rebooted. Last output:</p>"
                   f"<pre>{out[-3000:]}</pre>",
                   f"apt-get full-upgrade exited {rc}. Box NOT rebooted.\n\n{out[-3000:]}")
        return 1

    # Tag-pinned pull: this can only pick up patch rebuilds of the versions
    # already named in docker-compose.yml. The Plausible CE / ClickHouse major
    # upgrade is deliberately not done here (docs/server-maintenance.md).
    if os.path.isdir(PLAUSIBLE_DIR):
        rc, out = run(["sudo", "-n", "docker", "compose", "-f",
                       os.path.join(PLAUSIBLE_DIR, "docker-compose.yml"), "pull"], timeout=1800)
        log(f"docker compose pull exited {rc}")
        rc, out = run(["sudo", "-n", "docker", "compose", "-f",
                       os.path.join(PLAUSIBLE_DIR, "docker-compose.yml"), "up", "-d"], timeout=900)
        log(f"docker compose up -d exited {rc}")

    log("rebooting in 1 minute")
    run(["sudo", "-n", "shutdown", "-r", "+1", "Dale monthly maintenance"], timeout=60)
    return 0


def do_verify(now_perth, dry_run=False, force=False):
    """Post-boot health check. Wired to @reboot, so it runs after every boot,
    not only maintenance ones. That is deliberate: an unplanned reboot is worth
    an email too."""
    checks = []

    running = running_kernel()
    newest = newest_installed_kernel()
    kernel_ok = (newest is None) or (running == newest)
    checks.append(("kernel", kernel_ok, f"running {running}, newest installed {newest}"))

    since = reboot_required_since()
    checks.append(("reboot-required cleared", since is None,
                   "cleared" if since is None else f"still set ({since:%Y-%m-%d %H:%M} UTC)"))

    for unit in EXPECTED_UNITS:
        rc, out = run(["systemctl", "is-active", unit], timeout=30)
        checks.append((f"unit {unit}", out == "active", out or "unknown"))

    rc, out = run(["sudo", "-n", "docker", "ps", "--format", "{{.Names}}"], timeout=120)
    up = set(out.split("\n")) if rc == 0 else set()
    for name in EXPECTED_CONTAINERS:
        checks.append((f"container {name}", name in up, "up" if name in up else "MISSING"))

    for name, url, expected in HTTP_CHECKS:
        status = http_status(url)
        checks.append((name, status in expected, f"HTTP {status}"))

    pending, _ = pending_upgrades()
    checks.append(("apt clean", pending == 0, f"{pending} package(s) still upgradable"))

    index_age = apt_index_age_days()
    checks.append(("apt index fresh", index_age is not None and index_age < 2,
                   "never updated" if index_age is None else f"{index_age:.1f} days old"))

    usage = shutil.disk_usage("/")
    pct = (usage.total - usage.free) / usage.total * 100
    checks.append(("disk", pct < 85, f"{pct:.0f}% used, {usage.free / 1e9:.1f} GB free"))

    all_ok = all(ok for _, ok, _ in checks)

    # Only reclaim the superseded kernels once everything else is confirmed
    # healthy. autoremove on a box that did not come back properly is the last
    # thing anyone wants.
    autoremove = "skipped (dry run)" if dry_run else "skipped (checks did not all pass)"
    if all_ok and not dry_run:
        rc, out = run(["sudo", "-n", "env", "DEBIAN_FRONTEND=noninteractive",
                       "apt-get"] + APT_OPTS + ["-y", "autoremove", "--purge"], timeout=1800)
        removed = [l for l in out.split("\n") if l.startswith("Remv ")]
        autoremove = f"exit {rc}, {len(removed)} package(s) removed"

    rows = "".join(
        f"<tr><td>{'✅' if ok else '🔴'}</td><td>{name}</td><td>{detail}</td></tr>"
        for name, ok, detail in checks
    )
    icon = "✅" if all_ok else "🔴"
    html = f"""
<h2>{icon} Post-boot verification: {'all checks passed' if all_ok else 'PROBLEMS FOUND'}</h2>
<table border="0" cellpadding="4">{rows}</table>
<p><strong>Old kernel cleanup:</strong> {autoremove}</p>
<p>Checked at {now_perth:%a %d %b %Y %H:%M} AWST.</p>
""".strip()
    text = (f"Post-boot verification: {'PASS' if all_ok else 'FAIL'}\n\n" +
            "\n".join(f"{'OK ' if ok else 'FAIL'} {name}: {detail}"
                      for name, ok, detail in checks) +
            f"\n\nOld kernel cleanup: {autoremove}")

    if dry_run:
        print(text)
        return 0 if all_ok else 1
    send_email(f"{icon} Dale server rebooted: {'all checks passed' if all_ok else 'PROBLEMS FOUND'}",
               html, text)
    log(f"verification {'passed' if all_ok else 'FAILED'}")
    return 0 if all_ok else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--announce", action="store_true",
                      help="email the upcoming window (Saturdays before a window)")
    mode.add_argument("--run", action="store_true",
                      help="apply updates and reboot (first Monday 02:30 AWST)")
    mode.add_argument("--verify", action="store_true",
                      help="post-boot health check (@reboot)")
    parser.add_argument("--force", action="store_true",
                        help="ignore the date guard (used for the attended first run)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would be sent or done; change nothing")
    parser.add_argument("--now", help="override 'now' as ISO-8601 Perth local time, for testing")
    args = parser.parse_args()

    if args.now:
        now_perth = datetime.fromisoformat(args.now).replace(tzinfo=PERTH)
    else:
        now_perth = datetime.now(PERTH)

    if args.announce:
        return do_announce(now_perth, args.dry_run, args.force)
    if args.run:
        return do_run(now_perth, args.dry_run, args.force)
    return do_verify(now_perth, args.dry_run, args.force)


if __name__ == "__main__":
    sys.exit(main())
