#!/usr/bin/env bash
# Capture TreeSmith's store keyword rank into the append-only series (DAL-257).
#
# Both readers already worked and nothing scheduled them, so every comparison
# was a hand-run two-file diff and the 2026-08-13 pre-rename baseline nearly
# went to waste. This runs them weekly and commits what they measured; the
# Monday digest reads the series and reports what moved.
#
# INSTALLED in the live crontab 2026-08-20, first run Sunday 2026-08-23 21:40 UTC:
#
#   40 21 * * 0 /opt/dale/repo/tools/autonomous/capture-treesmith-rank.sh >> /opt/dale/autonomous/logs/treesmith_rank.log 2>&1
#
# Installed by editing the crontab on the box, NOT by editing
# `infrastructure/crontab.txt`. That file is a recording, captured
# server-to-repo by snapshot-server-config.sh on Mondays at 04:20 UTC, so
# editing it changes nothing on the box and would fake an install. The Monday
# snapshot picks the real line up on its own.
#
# Weekly, because the signal moves over weeks and daily would be noise. Sundays,
# 2h20m ahead of treesmith_analytics.py at Monday 00:00, with margin for a ~5
# minute run (72 Play page fetches at a 1.0s pause dominate). Minute 40, off the
# top of the hour, so it does not race the hourly dale-runner push -- the same
# reason the config snapshot sits at 04:20. Nothing else occupies the 21:00 hour.

set -uo pipefail

REPO="${DALE_REPO:-/opt/dale/repo}"
LOG="${DALE_LOG:-/opt/dale/autonomous/logs/cron.log}"
PYTHON="${DALE_PYTHON:-/usr/bin/python3}"
CSV_REL="data/treesmith-rank-history.csv"

log() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) capture-treesmith-rank: $1" >> "$LOG"
}

cd "$REPO" || { echo "repo not found at $REPO" >&2; exit 1; }

# One timestamp for BOTH stores. Two calls to `date` would stamp the readers
# minutes apart -- the Play pass alone is 72 fetches at a 1s pause -- and while
# the diff selects captures per store and would survive that, a shared stamp is
# what makes "the 2026-08-20 capture" mean one thing across both stores.
CAPTURED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

FAILURES=0
for reader in appstore_rank playstore_rank; do
    # stdout is the human table and is discarded; the append confirmation goes
    # to stderr, which is what we log.
    OUT=$("$PYTHON" "$REPO/tools/autonomous/$reader.py" \
              --csv "$REPO/$CSV_REL" --captured-at "$CAPTURED_AT" 2>&1 >/dev/null)
    if [ $? -ne 0 ]; then
        log "$reader FAILED: $OUT"
        FAILURES=$((FAILURES + 1))
    else
        log "$reader: $(echo "$OUT" | tr -d '\n')"
    fi
done

if [ "$FAILURES" -eq 2 ]; then
    # Neither store was read. The digest's stale flag would catch this, but not
    # for another week, and by then the gap is in the series.
    log "both readers failed; nothing captured at $CAPTURED_AT"
    "$PYTHON" "$REPO/tools/autonomous/notify.py" alert \
        "capture-treesmith-rank: both rank readers failed at $CAPTURED_AT, so no rank was captured this week. Check /opt/dale/autonomous/logs/treesmith_rank.log." \
        >/dev/null 2>&1 || log "alert email also failed"
fi

# Only commit when the series actually grew. A failed run leaves the file
# untouched and should stay silent rather than committing an empty change.
if git diff --quiet -- "$CSV_REL"; then
    log "series unchanged at $CAPTURED_AT; nothing committed"
    exit "$FAILURES"
fi

ROWS=$(git diff --numstat -- "$CSV_REL" | awk '{print $1}')

git add "$CSV_REL"
git commit -q -m "data: TreeSmith rank capture $CAPTURED_AT

$ROWS rows appended to $CSV_REL.

Automated by capture-treesmith-rank.sh (DAL-257)." || {
    log "commit failed"
    exit 1
}

# Push, healing the ordinary case where another writer got there first. Three
# writers push to origin/main, so a rejection is routine, not exceptional -- and
# a commit left local breaks the next autonomous session's pull. See git_sync.sh.
source "$REPO/tools/autonomous/git_sync.sh"

git_sync_push "$LOG"
PUSH_STATUS=$?

if [ "$PUSH_STATUS" -eq 0 ]; then
    if [ "$GIT_SYNC_REBASED" = "1" ]; then
        log "push was rejected, rebased onto origin/main and pushed"
    fi
    log "captured $ROWS rows at $CAPTURED_AT and pushed"
else
    REASON=$(git_sync_explain "$PUSH_STATUS")
    log "PUSH FAILED ($REASON). The commit is local, and every autonomous session will fail its pull until this is resolved."
    "$PYTHON" "$REPO/tools/autonomous/notify.py" alert \
        "capture-treesmith-rank could not push to origin/main: $REASON. /opt/dale/repo is ahead of origin and autonomous Dale will fail its hourly pull until someone resolves it. Fix: cd /opt/dale/repo && git rebase origin/main && git push." \
        >/dev/null 2>&1 || log "alert email also failed"
fi

exit "$FAILURES"
