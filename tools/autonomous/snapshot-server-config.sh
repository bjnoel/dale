#!/usr/bin/env bash
# Record the server's own configuration into the repo, weekly (DAL-281).
#
# The box runs 21 cron jobs, two systemd units, a Plausible stack and Caddy, and
# almost none of it was written down anywhere. The one infra file we did track,
# infrastructure/Caddyfile, had drifted 38 lines behind the live one, so
# restoring it would have deleted a working webhook receiver. A backup you are
# forbidden to restore is not a backup.
#
# Hetzner snapshots already cover "the box dies". What they cannot give you is a
# diff: when the crontab last changed, what changed, and whether the box is
# still what we think it is. So the output of this job is a git history, not an
# archive, and the useful moment is the week something changes that nobody
# decided to change.
#
# Direction is server to repo, never repo to server. These files are recordings.
# Restoring one is a human decision with a procedure in infrastructure/README.md,
# which is what keeps the "never cp the Caddyfile over the live one" rule intact
# instead of fighting it.
#
# Captured verbatim, byte for byte. Every note lives in infrastructure/README.md
# rather than in the captured file, because a file we annotate is a file that
# shows spurious drift every single week.
#
# It runs unattended into a PUBLIC repo, so it fails closed: config_scan.py
# checks every captured byte first, and one literal credential aborts the whole
# run without committing anything. See tests/test_config_scan.py.
#
# Runs Mondays 04:20 UTC from cron. Silent when nothing changed, which is most
# weeks. `--check` diffs live against the repo and writes nothing.

set -uo pipefail

REPO="${DALE_REPO:-/opt/dale/repo}"
LOG="${DALE_LOG:-/opt/dale/autonomous/logs/cron.log}"
NOTIFY="${DALE_NOTIFY:-$REPO/tools/autonomous/notify.py}"
SCANNER="${DALE_SCANNER:-$REPO/tools/autonomous/config_scan.py}"
DEST_REL="infrastructure"

MODE="publish"
case "${1:-}" in
    --check) MODE="check" ;;
    "")      ;;
    *)       echo "usage: $0 [--check]" >&2; exit 2 ;;
esac

log() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) snapshot-server-config: $1" >> "$LOG"
}

alert() {
    python3 "$NOTIFY" alert "$1" >/dev/null 2>&1 || log "alert email also failed"
}

# Capture the live config into $1. Everything here is read-only against the
# system. gandon-hook.service is deliberately absent: it belongs to
# bjnoel/gandon-calendar, which tracks its own copy. So are the .bak files, and
# anything under /opt/dale/secrets.
capture_to() {
    local dest="$1"
    mkdir -p "$dest/systemd" "$dest/plausible/clickhouse" "$dest/logrotate.d" || return 1

    crontab -l > "$dest/crontab.txt" 2>/dev/null || return 1
    sudo -n cat /etc/caddy/Caddyfile > "$dest/Caddyfile" 2>/dev/null || return 1

    local unit
    for unit in subscribe-server bee-subscribe-server; do
        sudo -n cat "/etc/systemd/system/$unit.service" \
            > "$dest/systemd/$unit.service" 2>/dev/null || return 1
    done

    cp /opt/dale/plausible/docker-compose.yml "$dest/plausible/docker-compose.yml" || return 1

    local xml
    for xml in clickhouse-config.xml clickhouse-user-config.xml ipv4-only.xml; do
        cp "/opt/dale/plausible/clickhouse/$xml" "$dest/plausible/clickhouse/$xml" || return 1
    done

    if [ -f /etc/logrotate.d/dale ]; then
        sudo -n cat /etc/logrotate.d/dale > "$dest/logrotate.d/dale" 2>/dev/null || return 1
    else
        rmdir "$dest/logrotate.d" 2>/dev/null
    fi

    return 0
}

cd "$REPO" || { log "repo not found at $REPO"; exit 1; }

STAGING="$(mktemp -d)" || { log "cannot create staging dir"; exit 1; }
trap 'rm -rf "$STAGING"' EXIT

# DALE_SNAPSHOT_STAGING lets the tests exercise the gate and the commit path
# with fixture files instead of a live server. Unset in production.
if [ -n "${DALE_SNAPSHOT_STAGING:-}" ]; then
    cp -a "$DALE_SNAPSHOT_STAGING/." "$STAGING/" || { log "fixture copy failed"; exit 1; }
else
    if ! capture_to "$STAGING"; then
        log "capture failed, nothing committed"
        alert "snapshot-server-config could not read the server's config (crontab, Caddyfile, systemd or Plausible). Nothing was committed. Check sudo -n and the paths in tools/autonomous/snapshot-server-config.sh."
        exit 1
    fi
fi

FILES=()
while IFS= read -r f; do
    FILES+=("$f")
done < <(find "$STAGING" -type f | sort)

if [ "${#FILES[@]}" -eq 0 ]; then
    log "captured nothing, refusing to continue"
    alert "snapshot-server-config captured zero files. That is never correct. Nothing was committed."
    exit 1
fi

# The gate. A captured credential must never reach a public repo, so this runs
# before anything is written into the working tree, and a finding stops the run
# rather than being filtered out. The output names the file and the key and
# never the value.
SCAN_OUT="$(python3 "$SCANNER" "${FILES[@]}" 2>&1)"
SCAN_STATUS=$?
if [ "$SCAN_STATUS" -ne 0 ]; then
    SCAN_SUMMARY="$(echo "$SCAN_OUT" | sed "s|$STAGING/||g")"
    log "BLOCKED, live config contains a literal secret: $(echo "$SCAN_SUMMARY" | tr '\n' '; ')"
    alert "snapshot-server-config REFUSED to commit: the live server config now contains a literal credential, and this repo is public. Nothing was committed and the snapshot is stale until this is fixed.

$SCAN_SUMMARY

Fix: move the value into /opt/dale/secrets/ or the service's .env and reference it, the way POSTGRES_PASSWORD is handled (DAL-281)."
    exit 1
fi

# --check: report drift, write nothing, touch no git state.
if [ "$MODE" = "check" ]; then
    DRIFT=0
    for src in "${FILES[@]}"; do
        rel="${src#"$STAGING"/}"
        if ! diff -q "$src" "$REPO/$DEST_REL/$rel" >/dev/null 2>&1; then
            echo "DRIFT: $rel"
            DRIFT=1
        fi
    done
    [ "$DRIFT" -eq 0 ] && echo "clean: live config matches $DEST_REL/"
    exit "$DRIFT"
fi

for src in "${FILES[@]}"; do
    rel="${src#"$STAGING"/}"
    mkdir -p "$REPO/$DEST_REL/$(dirname "$rel")"
    cp "$src" "$REPO/$DEST_REL/$rel" || { log "copy of $rel failed"; exit 1; }
done

git add "$DEST_REL" 2>/dev/null

# The common path: nothing on the box changed this week, so say nothing.
if git diff --cached --quiet -- "$DEST_REL"; then
    git reset -q HEAD -- "$DEST_REL" >/dev/null 2>&1
    exit 0
fi

DIFFSTAT="$(git diff --cached --stat -- "$DEST_REL")"
log "server config drifted: $(echo "$DIFFSTAT" | tail -1 | sed 's/^ *//')"

git commit -q -m "chore: record server config drift

$DIFFSTAT

Automated by snapshot-server-config.sh (DAL-281). Captured from the live box;
these files are recordings, not deploy sources. See infrastructure/README.md." || {
    log "commit failed"
    alert "snapshot-server-config staged a config change but could not commit it. /opt/dale/repo needs a look."
    exit 1
}

source "$REPO/tools/autonomous/git_sync.sh"

git_sync_push "$LOG"
PUSH_STATUS=$?

if [ "$PUSH_STATUS" -eq 0 ]; then
    if [ "$GIT_SYNC_REBASED" = "1" ]; then
        log "push was rejected, rebased onto origin/main and pushed"
    fi
    # Drift is the whole point of the job, so it goes to a person and not only
    # to a log. DEC-285: a thing written to a log and not to a person is a thing
    # nobody learns.
    alert "The server's configuration changed this week and has been committed to infrastructure/.

$DIFFSTAT

If you expected this, nothing to do. If you did not, the diff is in git log -p infrastructure/."
else
    REASON=$(git_sync_explain "$PUSH_STATUS")
    log "PUSH FAILED ($REASON). The commit is local, and every autonomous session will fail its pull until this is resolved."
    alert "snapshot-server-config could not push to origin/main: $REASON. /opt/dale/repo is ahead of origin and autonomous Dale will fail its hourly pull until someone resolves it. Fix: cd /opt/dale/repo && git rebase origin/main && git push."
fi
