#!/usr/bin/env bash
# Fold BCC'd nursery touches into the register and commit them (DAL-273).
#
# The webhook cannot do this itself. deploy.sh copies the repo copy of
# data/nursery-contacts.json over the data-dir copy on every deploy, and
# dale-runner deploys hourly, so anything the webhook wrote to the data dir
# would be gone within the hour. The webhook appends to a JSONL nothing
# overwrites; this merges it into the repo copy, where git history stays the
# audit log for who we contacted and when.
#
# Runs hourly from cron. A no-op when nothing new has arrived, which is most
# hours, so it stays quiet.

set -uo pipefail

REPO="/opt/dale/repo"
LOG="/opt/dale/autonomous/logs/cron.log"

log() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) merge-nursery-inbound: $1" >> "$LOG"
}

cd "$REPO" || { log "repo not found at $REPO"; exit 1; }

# Nothing to do if the webhook has never fired.
[ -s /opt/dale/data/nursery-inbound.jsonl ] || exit 0

OUT=$(python3 "$REPO/tools/autonomous/nursery_crm.py" merge-inbound 2>&1)
STATUS=$?
if [ "$STATUS" -ne 0 ]; then
    log "merge failed: $OUT"
    exit 1
fi

# Only commit when the register actually changed. `merge-inbound` is a no-op on
# a re-run, so this is the common path and it should stay silent.
if git diff --quiet -- data/nursery-contacts.json; then
    exit 0
fi

log "$OUT"

git add data/nursery-contacts.json
git commit -q -m "chore: log nursery touches from BCC'd inbound mail

$OUT

Automated by merge-nursery-inbound.sh (DAL-273). Source records are in
/opt/dale/data/nursery-inbound.jsonl on the VPS." || {
    log "commit failed"
    exit 1
}

# Push, healing the ordinary case where another writer got there first.
#
# This used to log "commit is local and will go with the next session" and carry
# on. It did not go with the next session: it broke the next session, whose
# `git pull --ff-only` cannot resolve a divergence. See git_sync.sh.
source "$REPO/tools/autonomous/git_sync.sh"

git_sync_push "$LOG"
PUSH_STATUS=$?

if [ "$PUSH_STATUS" -eq 0 ]; then
    if [ "$GIT_SYNC_REBASED" = "1" ]; then
        log "push was rejected, rebased onto origin/main and pushed"
    fi
else
    REASON=$(git_sync_explain "$PUSH_STATUS")
    log "PUSH FAILED ($REASON). The commit is local, and every autonomous session will fail its pull until this is resolved."
    python3 "$REPO/tools/autonomous/notify.py" alert \
        "merge-nursery-inbound could not push to origin/main: $REASON. /opt/dale/repo is ahead of origin and autonomous Dale will fail its hourly pull until someone resolves it. Fix: cd /opt/dale/repo && git rebase origin/main && git push." \
        >/dev/null 2>&1 || log "alert email also failed"
fi

# Republish to the data dir so /admin reflects the new touch before the next
# deploy would have done it anyway.
cp -a "$REPO/data/nursery-contacts.json" /opt/dale/data/nursery-contacts.json
log "register updated and republished"
