#!/usr/bin/env bash
# Turn the browser's curation queue into a commit, nightly, 30 minutes before
# the build that applies it.
#
# Benedict folds varieties on /admin/varieties/review. That queues an intent in
# variety-decisions.json and nothing more, because variety_overrides.json is
# git-tracked and deploy.sh rsyncs it, so a browser writing it on the server is
# overwritten within the hour. promote_curation.py is what turns the queue into
# a commit, and until DAL-286 someone had to run it by hand, which meant a fold
# sat queued until Benedict remembered to ask.
#
# Timing (23:30 UTC, with run-all-scrapers.sh at 00:00):
#
#   any time    fold on /admin/varieties/review, Cancel still works
#   23:30 UTC   this script: promote, test, commit, push, deploy
#   00:00 UTC   the build reads the new overrides and moves the products
#   +2 nights   the page ledger emits the redirect on its own
#
# So a decision keeps the whole day in which changing your mind costs a click.
# The half hour after 23:30 is the only window where undoing needs a git revert,
# and it is deliberately short.
#
# We deploy here rather than leaving it to dale-runner.sh, which also runs
# deploy.sh but at :00, the same minute the scrape starts. The build reads
# /opt/dale/scrapers/variety_overrides.json, so losing that race means the
# commit lands and the build ignores it for a day.
set -uo pipefail

REPO="/opt/dale/repo"
DATA="/opt/dale/data"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cd "$REPO" || { echo "$STAMP promote-curation: no repo at $REPO"; exit 1; }

OUT="$(python3 tools/scrapers/promote_curation.py --data-dir "$DATA" \
        --execute --push 2>&1)"
CODE=$?

# Silence when there is nothing to do, which is most nights. A log that says
# "nothing queued" 364 times is a log nobody reads on the night it matters.
if [ "$CODE" -eq 0 ] && printf '%s' "$OUT" | grep -q '^Nothing queued\.'; then
    exit 0
fi

echo "$STAMP promote-curation: exit=$CODE"
printf '%s\n' "$OUT"

if [ "$CODE" -ne 0 ]; then
    # promote_curation.py reverts the override file when the suite fails and
    # leaves the queue intact either way, so the next night retries. The visible
    # symptom is rows staying in "Queued for tonight" on /admin/varieties/review,
    # which is a better alarm than an email nobody wired up: it is in front of
    # the person whose decision is stuck, on the page they made it.
    echo "$STAMP promote-curation: queue left intact, retrying tomorrow"
fi

# Deploy regardless. After a failed suite the file is already reverted, so this
# is a no-op; after a failed push the commit is local and correct, and the build
# reads the deployed copy rather than GitHub.
bash "$REPO/tools/deploy.sh"
exit "$CODE"
