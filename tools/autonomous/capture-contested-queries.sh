#!/usr/bin/env bash
# Weekly reading of how many queries treestock answers with two of its own pages.
#
# DEC-309 differentiated /species/ from /compare/ on 2026-08-20. This is what
# decides whether that worked, and it runs weekly rather than once because a
# single after-reading has nothing to be compared against. The pre-change arm
# was backfilled from GSC history on 2026-08-20 so the spread of this number is
# known before the change is judged.
#
# INSTALLED in the live crontab 2026-08-20, first run Thursday 2026-08-27 20:40 UTC:
#
#   40 20 * * 4 /opt/dale/repo/tools/autonomous/capture-contested-queries.sh >> /opt/dale/autonomous/logs/contested_queries.log 2>&1
#
# Installed by editing the crontab on the box, NOT `infrastructure/crontab.txt`.
# That file is a recording captured server-to-repo by snapshot-server-config.sh
# on Mondays at 04:20 UTC; editing it changes nothing and would fake an install.
#
# Thursday because 2026-08-27 (the 7-day check Benedict asked for) and
# 2026-09-17 (DAL-287's verdict) are both Thursdays, so the same line covers
# both without a one-shot cron that leaves a dead entry behind. 20:40 UTC:
# nothing else runs on Thursdays, it is clear of the 22:00 digest, and minute 40
# keeps it off the hourly dale-runner push at :00 and the inbound merge at :15.
#
# Weekly, not daily: GSC finalises slowly and the signal moves over weeks.

set -uo pipefail

REPO="${DALE_REPO:-/opt/dale/repo}"
LOG="${DALE_LOG:-/opt/dale/autonomous/logs/cron.log}"
PYTHON="${DALE_PYTHON:-/usr/bin/python3}"
CSV_REL="data/contested-queries.csv"
READER="$REPO/tools/scrapers/contested_queries.py"

log() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) capture-contested-queries: $1" >> "$LOG"
}

cd "$REPO" || { echo "repo not found at $REPO" >&2; exit 1; }

if ! OUT=$("$PYTHON" "$READER" --csv "$REPO/$CSV_REL" record 2>&1); then
    log "reader FAILED: $OUT"
    "$PYTHON" "$REPO/tools/autonomous/notify.py" alert \
        "capture-contested-queries: the GSC reader failed, so no reading was taken this week. A gap in the series weakens the DEC-309 verdict. Check /opt/dale/autonomous/logs/contested_queries.log." \
        >/dev/null 2>&1 || log "alert email also failed"
    exit 1
fi
log "$(echo "$OUT" | tr '\n' ' ')"

# Only commit when the series actually grew. Re-running on the same day appends
# nothing (append() dedupes on window+end) and should stay silent.
#
# Staged first, and the emptiness test is against the INDEX, not the worktree.
# `git diff --quiet -- <path>` reports an untracked file as unchanged, so on the
# first ever run this said "series unchanged" about a file it had just created
# and the series would never have been committed at all. Caught by running the
# wrapper by hand on 2026-08-20, when the backfilled CSV was still untracked.
#
# `git add -- <path>` and `git commit -- <path>` are both pathspec-limited on
# purpose: three writers share this checkout, and a bare `git commit` would
# sweep whatever another session happened to have staged.
git add -- "$CSV_REL"
if git diff --cached --quiet -- "$CSV_REL"; then
    log "series unchanged; nothing committed"
else
    ROWS=$(git diff --cached --numstat -- "$CSV_REL" | awk '{print $1}')
    if git commit -q -m "data: contested-query reading $(date -u +%Y-%m-%d)

$ROWS row(s) appended to $CSV_REL.

Automated by capture-contested-queries.sh (DEC-309, DAL-287)." -- "$CSV_REL"; then
        # Three writers push to origin/main, so a rejection is routine. A commit
        # left local breaks the next autonomous session's pull.
        source "$REPO/tools/autonomous/git_sync.sh"
        git_sync_push "$LOG"
        PUSH_STATUS=$?
        if [ "$PUSH_STATUS" -eq 0 ]; then
            log "captured $ROWS row(s) and pushed"
        else
            REASON=$(git_sync_explain "$PUSH_STATUS")
            log "PUSH FAILED ($REASON). The commit is local and autonomous Dale will fail its hourly pull until this is resolved."
            "$PYTHON" "$REPO/tools/autonomous/notify.py" alert \
                "capture-contested-queries could not push to origin/main: $REASON. Fix: cd /opt/dale/repo && git rebase origin/main && git push." \
                >/dev/null 2>&1 || log "alert email also failed"
        fi
    else
        log "commit failed"
    fi
fi

# Email only when a reading leaves the pre-change band. A weekly "still normal"
# message is a new inbox nobody asked for, and the whole series is on disk for
# anyone who wants to look. --alert-only exits non-zero when there is nothing
# worth saying, which is the quiet case and not an error.
if VERDICT=$("$PYTHON" "$READER" --csv "$REPO/$CSV_REL" report --alert-only 2>/dev/null); then
    log "MOVED: $(echo "$VERDICT" | tr '\n' ' ')"
    "$PYTHON" "$REPO/tools/autonomous/notify.py" alert \
        "treestock contested queries moved outside their pre-change range (DEC-309):

$VERDICT

The full series is in data/contested-queries.csv. DAL-287 is the verdict ticket." \
        >/dev/null 2>&1 || log "alert email failed"
else
    log "reading is inside the pre-change band; staying quiet"
fi

exit 0
