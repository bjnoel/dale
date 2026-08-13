# Server maintenance runbook

Hetzner CAX11, `ssh dale-server`, Ubuntu 24.04 (noble), arm64, 38 GB disk.

Established by DEC-290 (DAL-282). Read this before changing anything about
patching, reboots, or the Plausible container stack.

## The problem this exists to solve

`unattended-upgrades` had been installed, enabled and working correctly since
March 2026. Zero packages were ever pending from the `-security` pocket. Every
signal read green.

On 2026-08-13 the box had been up 161 days, running kernel `6.8.0-90-generic`
with `6.8.0-124-generic` installed and unbooted. Seven kernel images and `libc6`
were patched on disk and inert in memory. `/var/run/reboot-required` had been
set since 11 June. Every kernel and libc CVE fixed since March was fixed on disk
and running nowhere.

The mechanism worked. The effect never landed. `libc6` is the quiet one: every
long-running process still had the old copy mapped.

**The lesson generalises: "the patch is installed" and "the patch is running"
are different claims, and only one of them is what security means.**

### And one layer further down: the index had frozen too

Found while fixing the above, and worse than the original finding.

An `apt-get -qq -y update` started by `apt.systemd.daily` on **24 June** was
still running **48 days later**, with four `/usr/lib/apt/methods/https` children
stuck on sockets and no timeout to end them. It held `/var/lib/apt/lists/lock`
that entire time, so `unattended-upgrades` could not run at all after 24 June —
`unattended-upgrades-dpkg.log` has been zero bytes since 1 July.

That means the reassuring number was itself an artefact. "0 packages pending
from `-security`" was read off an index frozen in June. The box reported zero
pending security updates **because it had not looked**.

On a fresh index: **142 packages upgradable, 83 of them from the security
pocket**, and the available kernel had moved on again to 6.8.0-137.

No dpkg transaction was in flight (`/var/lib/dpkg/updates/` empty, frontend lock
free), so the hung tree was killed and the index refreshed. Two defences now
exist: every apt call carries `Acquire::*::Timeout` and `DPkg::Lock::Timeout`
(`APT_OPTS` in `monthly_maintenance.py`), and `uptime_monitor.py` alerts when
`/var/lib/apt/periodic/update-success-stamp` goes stale.

## The cadence

| when | what | how |
| -- | -- | -- |
| Saturday 09:00 AWST, 2 days before a window | announcement email | `monthly_maintenance.py --announce` |
| **First Monday of the month, 02:30 AWST** | apt full-upgrade, Docker tag refresh, reboot | `monthly_maintenance.py --run` |
| every boot, +2 min | health check email | `monthly_maintenance.py --verify` |
| every 5 min | backstop alert if a window was missed | `uptime_monitor.py` |

### Why the default is that it happens

The reboot is **announced, not requested**. Two days' notice, then it proceeds
unless someone actively vetoes it. A reminder that waits for a human to act is
the same shape as the failure being fixed: the last nine weeks were also waiting
on someone to act.

Automatic *unattended* reboots were rejected. Rebooting a box that hosts someone
else's holiday-rental calendar without a human knowing is worse than a stale
kernel. The announcement is what makes this not that.

### Timezone arithmetic — the easiest thing to get wrong

**02:30 AWST Monday is 18:30 UTC the preceding Sunday.**

The server is `Etc/UTC`, and `CRON_TZ` is **not** documented in this box's
`crontab(5)`, so it is not relied on. Every cron line is UTC; all AWST logic
lives in `monthly_maintenance.py` as pure functions, covered by
`tests/test_monthly_maintenance.py`. An off-by-one day here means the reboot
silently never fires, which is indistinguishable from the original bug.

Perth has no daylight saving, so the offset is +8 year-round.

## Crontab lines (UTC, `dale` user)

```cron
# Monthly maintenance (DEC-290). Times are UTC; 18:30 Sun = 02:30 Mon AWST.
0  1 * * 6  /usr/bin/python3 /opt/dale/autonomous/monthly_maintenance.py --announce >> /opt/dale/autonomous/logs/maintenance.log 2>&1
30 18 * * 0 /usr/bin/python3 /opt/dale/autonomous/monthly_maintenance.py --run      >> /opt/dale/autonomous/logs/maintenance.log 2>&1
@reboot     sleep 120 && /usr/bin/python3 /opt/dale/autonomous/monthly_maintenance.py --verify >> /opt/dale/autonomous/logs/maintenance.log 2>&1
```

Both scheduled entries fire weekly and exit immediately on the weeks that are
not a maintenance window. The date guard is in the script, not in cron, because
cron cannot express "first Monday" without the day-of-month/day-of-week OR trap.

`--verify` runs after **every** boot, not only maintenance ones. An unplanned
reboot is worth an email too.

No sudoers change was needed: `/etc/sudoers.d/dale` already grants
`dale ALL=(ALL) NOPASSWD: ALL`.

## Why this window

- **Traffic.** treestock's trough is 01:00–03:00 AWST at ~1.6 visitors/hour,
  against ~13/hour at the 18:00 AWST peak (Plausible v2 `time:hour`, 7 days to
  2026-08-12; the site's Plausible timezone is `Australia/Perth`).
- **Scrapers do not collide.** `run-all-scrapers.sh` starts 00:00:01 UTC and the
  whole pipeline, dashboard build included, is done by ~00:45 UTC. The window is
  ~17.5 h after it finishes and 5.5 h before the next one starts.
- **Backups.** `weekly_backup.sh` runs Sunday 02:00 UTC, so a fresh backup always
  exists ~16 h before each window.
- **Known collision, accepted.** The weekly subscriber digest runs Sunday 23:00
  UTC, 4.5 h after the reboot. If the box does not come back, that send is
  missed. The `--verify` email is the mitigation: 4.5 h of lead time to react.

## What goes down, and for how long

Everything on the box: treestock (Caddy), Plausible, `subscribe-server`, and
gandon-calendar. Roughly two to three minutes, most of it Docker coming back up.
All three Plausible containers are `restart: always` and all four systemd units
(`caddy`, `docker`, `subscribe-server`, `gandon-hook`) are `enabled`, so nothing
needs starting by hand.

## Vetoing a window

```bash
touch /opt/dale/autonomous/locks/no-reboot
```

The veto is **one-shot by design**. It skips one month and is deleted when it
fires — including when the "skipped" email fails to send, so a Resend outage
cannot turn a one-month skip into a permanent one. A sticky veto left in place
would recreate exactly the nine-week gap this cadence closes.

## The backstops

`uptime_monitor.py` runs every 5 minutes and now carries two checks for this,
both de-duped through `uptime_state.json` and both retried on a failed send.

**Reboot pending.** Alerts once past **40 days**, escalating at **75**, with an
all-clear when the file disappears. 40 is deliberate: the longest possible gap
between first Mondays is 35 days, so it fires only when a window was actually
missed, never during a healthy cycle. An alert that cried wolf every month would
be filtered inside two. `/var/run` is tmpfs, so the file cannot survive a reboot
and its mtime is a trustworthy "set at".

**apt index stale.** Alerts once past **3 days** since the last *successful*
`apt-get update`, critical at **10**, using
`/var/lib/apt/periodic/update-success-stamp` — which `apt.systemd.daily` touches
only on success. A missing stamp is treated as **critical, not ok**: "no evidence
apt has ever succeeded" is the worse reading, and assuming the friendlier one is
what let the 48-day hang sit unnoticed.

The two are complementary and the order matters. A stale index makes the
reboot-required check look healthy too, because nothing new ever gets installed
to require a reboot. If both fire, believe the apt one first.

## Manual run

```bash
ssh dale-server
# see what would happen, change nothing
python3 /opt/dale/autonomous/monthly_maintenance.py --run --dry-run --force
# actually do it
python3 /opt/dale/autonomous/monthly_maintenance.py --run --force
# health check without emailing
python3 /opt/dale/autonomous/monthly_maintenance.py --verify --dry-run
```

`--now 2026-09-05T09:00` overrides the clock for testing the date guards.

Avoid `:00`–`:15` past the hour, so the run does not race the hourly
`dale-runner.sh` session or `merge-nursery-inbound.sh` at `:15`. `--run` waits up
to 10 minutes for a live `locks/session.lock` anyway, then proceeds: killing a
session is survivable (`dale-runner.sh` treats a dead-PID lock as stale, and a
stranded commit is caught by `check_git_divergence` within the hour), but waiting
is free.

## Safety properties worth not breaking

- `--run` **does not reboot** if `apt-get full-upgrade` exits non-zero. Rebooting
  on top of a half-applied upgrade is how a two-minute outage becomes an
  unbootable box.
- `--verify` runs `apt-get autoremove --purge` **only if every health check
  passed**. Reclaiming kernels on a box that did not come back properly is the
  last thing anyone wants.
- `--run` exits without rebooting when there is nothing pending. A cadence that
  produces twelve pointless outages a year gets switched off.

## unattended-upgrades

`Allowed-Origins` in `/etc/apt/apt.conf.d/50unattended-upgrades` includes the
`-updates` pocket as well as the security ones (DEC-290). That default is only
safe *because* a reboot cadence now exists to activate what it installs; do not
widen it further without one.

## Docker images

The three images in `/opt/dale/plausible/docker-compose.yml` are **tag-pinned**:

| image | pinned tag |
| -- | -- |
| `ghcr.io/plausible/community-edition` | `v3.2.0` |
| `clickhouse/clickhouse-server` | `24.12-alpine` |
| `postgres` | `16-alpine` |

`--run` does `docker compose pull && up -d`, which can therefore only pick up
**patch rebuilds of those same versions**. It is not a version upgrade.

### Deferred: the Plausible CE + ClickHouse major upgrade

Plausible CE v3.2.0 is 6 months old and ClickHouse 24.12 is a 17-month-old
release line. Bumping them is **not** a `docker compose pull`:

- Plausible CE pins a supported ClickHouse major; they move as a matched set,
  against the CE release notes and migration steps.
- ClickHouse is the component that filled the disk once already
  (`memory/project_server_disk_clickhouse.md`), so it is not a hypothetical part
  of the stack.

Not filed in Linear: the backlog stands at 23 tickets against a cap of 15, so
`linear_update.py create` exits 1. It is recorded here and in DEC-290 instead.

**Before attempting it**, note that the ClickHouse log-table suppression in
`/opt/dale/plausible/clickhouse/clickhouse-config.xml` (`text_log`, `metric_log`,
`asynchronous_metric_log`, `trace_log`, `processors_profile_log`, `error_log` all
`remove="remove"`) is what keeps the disk from filling. It is config-file based
and therefore restart-durable — verified 2026-08-13, `system.metric_log` max
`event_time` is still epoch. This supersedes the older note in
`memory/project_server_disk_clickhouse.md` that the suppression was a SQL `TTL`
and would not survive a restart. A ClickHouse major upgrade must re-verify it.

## Rollback

- **Kernel:** the previous kernel stays installed until `--verify` passes and
  autoremove runs, so a bad boot can be recovered by picking the older entry in
  grub via the Hetzner console. `GRUB_TIMEOUT=0` and `GRUB_TIMEOUT_STYLE=hidden`,
  so hold `Shift` / `Esc` at boot.
- **Data:** `/opt/dale/backups/data-YYYY-Wnn.tar.gz`, weekly, ~16 h before each
  window. These are on the same disk, so they cover an application-level mistake,
  not a dead box.
- **Whole box:** a Hetzner snapshot, taken by hand before an unusually large
  upgrade. Deliberately not in the monthly script — snapshots carry a recurring
  per-GB cost, and the monthly delta does not justify one.
