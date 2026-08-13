# infrastructure/

Recordings of the live server's configuration, captured from the Hetzner box
(`ssh dale-server`) every Monday by `tools/autonomous/snapshot-server-config.sh`.

**These files are recordings, not deploy sources. Do not copy them onto the
server.** Nothing in this directory is applied automatically, in either
direction, and that is deliberate. Restoring any of it is a human decision with
a procedure below.

## Why this exists

Before DAL-281 the entire automation schedule, 21 cron jobs, lived on one box
and was written down nowhere. The only tracked file was `Caddyfile`, and it had
drifted 38 lines behind the live one, so restoring it would have silently
deleted a working webhook receiver.

Hetzner snapshots (daily, 7 day retention) already cover "the box dies". What
they cannot give you is a diff. This directory exists so that `git log -p
infrastructure/` answers: when did the crontab change, what changed, and is the
box still what we think it is. The useful week is the one where something
changes that nobody decided to change, which is why the job emails on drift
rather than only committing it.

## What is captured

| File | Source on the box |
| --- | --- |
| `crontab.txt` | `crontab -l` for the `dale` user |
| `Caddyfile` | `/etc/caddy/Caddyfile` |
| `systemd/subscribe-server.service` | `/etc/systemd/system/` |
| `systemd/bee-subscribe-server.service` | `/etc/systemd/system/` |
| `plausible/docker-compose.yml` | `/opt/dale/plausible/` |
| `plausible/clickhouse/*.xml` | `/opt/dale/plausible/clickhouse/` |
| `logrotate.d/dale` | `/etc/logrotate.d/dale` |

Captured **verbatim, byte for byte**. Every note about these files belongs in
this README and never in the file itself, because an annotated capture shows
drift every single week and the diff stops meaning anything.

## What is deliberately not captured

- **Secrets.** Nothing under `/opt/dale/secrets/`, and no `.env` file. The
  snapshot runs into a public repo, so `tools/autonomous/config_scan.py` scans
  every captured byte first and aborts the whole run on a literal credential.
  It does not redact and continue: a redacted capture cannot be diffed.
- **`gandon-hook.service`** and, in spirit, the `hook.gandongully.com.au` block
  inside `Caddyfile`. Those belong to `bjnoel/gandon-calendar`, which tracks its
  own copy. The Caddy block is captured only because it is physically inside a
  file we capture whole. **Treat gandon-calendar's repo as the source of truth
  for it**, and do not hand-edit it here.
- **`.bak` files**, of which the box has several generations.
- **Scraper and autonomous code**, which already deploys from this repo via
  `tools/deploy.sh` and would be a circular capture.

## Restoring

There is no restore script on purpose. Each artifact wants a different amount of
care, and the failure mode we are guarding against is exactly an unattended
wholesale copy.

- **`crontab.txt`** — `crontab -l > /tmp/now.txt`, diff it against this file,
  and apply the lines you actually want with `crontab -e`. Note the file mixes
  Dale's jobs with two `gandon-calendar` jobs.
- **`Caddyfile`** — never `cp` this over `/etc/caddy/Caddyfile` wholesale. Diff
  first, patch the hunks you want in place, then
  `sudo caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile` and
  `sudo systemctl reload caddy`. A failed reload leaves systemd stuck in
  `reload-notify` while the old config keeps serving;
  `sudo caddy reload --config /etc/caddy/Caddyfile` clears it without a restart.
- **`systemd/*.service`** — copy into `/etc/systemd/system/`, then
  `sudo systemctl daemon-reload`. `bee-subscribe-server` is recorded **stopped
  and disabled on purpose** (DEC-230, beestock discontinued). Do not enable it.
- **`plausible/`** — the compose file references `POSTGRES_PASSWORD`,
  `SECRET_KEY_BASE` and `BASE_URL` from `/opt/dale/plausible/.env` (mode 0600),
  and MaxMind credentials from `/opt/dale/secrets/maxmind.env`. Restoring the
  compose file alone will not start the stack; those two files have to exist
  first, and they are not in this repo.

## Checking for drift by hand

```
ssh dale-server /opt/dale/autonomous/snapshot-server-config.sh --check
```

Writes nothing, touches no git state. Exits 0 when the box matches this
directory, 1 when it does not, listing each file that differs.
