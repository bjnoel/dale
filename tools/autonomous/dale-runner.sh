#!/usr/bin/env bash
# Autonomous Dale — hourly ticket runner
# Called by cron every hour. Polls Linear for Todo/In Progress tickets.
# If no work exists, exits immediately (no cost). Otherwise runs a focused
# Claude session to process tickets.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$SCRIPT_DIR/config.json"
LOG_DIR="$SCRIPT_DIR/logs"
STOP_FILE="$SCRIPT_DIR/STOP"
LOCK_FILE="$SCRIPT_DIR/locks/session.lock"
NOW_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TODAY=$(date -u +%Y-%m-%d)
HOUR=$(date -u +%H)
SESSION_LOG="$LOG_DIR/session-$TODAY-$HOUR.json"
TASKS_FILE="/opt/dale/data/linear-tasks.json"

mkdir -p "$LOG_DIR" "$(dirname "$LOCK_FILE")"

log() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) — $1" >> "$LOG_DIR/cron.log"
}

# --- Pre-checks ---

# 1. STOP file
if [ -f "$STOP_FILE" ]; then
    log "STOP file exists. Skipping."
    exit 0
fi

# 2. Lock file (prevent overlapping sessions)
if [ -f "$LOCK_FILE" ]; then
    LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null)
    if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null; then
        log "Session already running (PID $LOCK_PID), skipping"
        exit 0
    fi
    # Stale lock, remove it
    rm -f "$LOCK_FILE"
fi
echo $$ > "$LOCK_FILE"
PROMPT_FILE=""
trap 'rm -f "$LOCK_FILE" ${PROMPT_FILE:+"$PROMPT_FILE"}' EXIT

# 3. Consecutive failures
#
# The halt alert fires ONCE per halt, not once per cron tick. The 2026-08-10
# halt sent 48 identical emails over two days, which is how you teach someone
# to filter the alert that actually matters. The flag is cleared on the next
# successful session, so a fresh halt still gets a fresh email.
HALT_FLAG="$SCRIPT_DIR/locks/halt-notified.flag"
FAILURE_COUNT=$(python3 "$SCRIPT_DIR/budget-tracker.py" failure-count 2>/dev/null | tail -1)
if [ "${FAILURE_COUNT:-0}" -ge 3 ]; then
    log "3+ consecutive failures ($FAILURE_COUNT). Halting."
    if [ ! -f "$HALT_FLAG" ]; then
        python3 "$SCRIPT_DIR/notify.py" alert "3 consecutive failures — autonomous run halted. Check logs."
        touch "$HALT_FLAG"
    fi
    exit 0
fi

# 4. Read config
REPO_DIR=$(python3 -c "import json; print(json.load(open('$CONFIG'))['paths']['repo'])")
MAX_MINUTES=$(python3 -c "import json; print(json.load(open('$CONFIG'))['budget']['max_session_duration_minutes'])")
MAX_TURNS=$(python3 -c "import json; print(json.load(open('$CONFIG'))['budget']['max_turns'])")

# 5. Repo health + pull + deploy
if [ ! -d "$REPO_DIR/.git" ]; then
    log "Repo not found at $REPO_DIR. Aborting."
    python3 "$SCRIPT_DIR/budget-tracker.py" log-failure "repo-not-found"
    exit 1
fi

cd "$REPO_DIR"

# Prefer the deployed copy: this runs before deploy.sh, so the repo copy may be
# whatever the last pull left behind. Fall back to the repo for a fresh box.
if [ -f "$SCRIPT_DIR/git_sync.sh" ]; then
    source "$SCRIPT_DIR/git_sync.sh"
elif [ -f "$REPO_DIR/tools/autonomous/git_sync.sh" ]; then
    source "$REPO_DIR/tools/autonomous/git_sync.sh"
else
    log "git_sync.sh not found. Aborting."
    python3 "$SCRIPT_DIR/budget-tracker.py" log-failure "git-sync-missing"
    exit 1
fi

# Was `git fetch` + `git pull --ff-only`. ff-only is right for a pure deploy
# target and wrong here, because this box also pushes: one rejected push left it
# permanently unable to pull, which halted Dale via the 3-failure breaker.
git_sync_pull "$LOG_DIR/git-errors.log"
PULL_STATUS=$?

if [ "$PULL_STATUS" -ne 0 ]; then
    REASON=$(git_sync_explain "$PULL_STATUS")
    log "Git pull failed ($REASON). See $LOG_DIR/git-errors.log."
    python3 "$SCRIPT_DIR/budget-tracker.py" log-failure "git-pull-conflict"
    # The reason is an exit code, and on 2026-08-17 (DEC-299) it sent a human to
    # `git status`, which reported a clean tree one commit behind because the
    # failure was a race in a file that no longer existed by the time anyone
    # looked. git's own sentence was in git-errors.log all along. Name it first.
    python3 "$SCRIPT_DIR/notify.py" alert \
        "Autonomous Dale cannot pull: $REASON. Sessions will keep failing and the 3-failure breaker will halt Dale entirely. Read the error first: tail $LOG_DIR/git-errors.log. Then: cd /opt/dale/repo && git status." \
        >/dev/null 2>&1 || true
    exit 1
fi

if [ "$GIT_SYNC_REBASED" = "1" ]; then
    log "Pull rebased local commits onto origin/main (another writer got there first)."
fi

# Deploy scripts from repo to server locations
if [ -f "$REPO_DIR/tools/deploy.sh" ]; then
    bash "$REPO_DIR/tools/deploy.sh" 2>>"$LOG_DIR/cron.log"
fi

# 6. Weekly update check (Dale strikes Wed-Sun if no update from Benedict)
python3 "$SCRIPT_DIR/check-weekly-update.py" || {
    log "Weekly update missing. Dale is on strike."
    STRIKE_FLAG="$(dirname "$LOCK_FILE")/strike-notified-$(date -u +%Y-W%V).flag"
    if [ ! -f "$STRIKE_FLAG" ]; then
        python3 "$SCRIPT_DIR/notify.py" alert "Dale is on strike! No weekly update from Benedict. Write /opt/dale/data/weekly-updates/$(date -u +%Y)-W$(date -u +%V).md"
        touch "$STRIKE_FLAG"
    fi
    exit 0
}

# 7. Refresh the read-only Treesmith mirrors (DAL-179). Non-fatal: a stale
# manifest still beats no visibility, and the manifest records its own staleness.
python3 "$SCRIPT_DIR/refresh_treesmith_status.py" >>"$LOG_DIR/cron.log" 2>&1 || {
    log "Warning: Treesmith mirror refresh failed (manifest may be stale)"
}

# --- Fetch Linear tickets ---

log "Fetching Linear tickets"
POLLER_OK=1
python3 "$SCRIPT_DIR/linear_poller.py" 2>>"$LOG_DIR/cron.log" || {
    POLLER_OK=0
    log "Warning: Linear poller failed (tickets on file are stale)"
}

# --- Check if there's work to do ---

TODO_COUNT=0
BACKLOG_COUNT=0
MIN_BACKLOG=$(python3 -c "import json; print(json.load(open('$CONFIG')).get('linear', {}).get('min_backlog', 15))")

if [ -f "$TASKS_FILE" ]; then
    TODO_COUNT=$(python3 -c "
import json; d = json.load(open('$TASKS_FILE'))
print(len(d.get('todo', [])) + len(d.get('in_progress', [])))" 2>/dev/null || echo 0)
    BACKLOG_COUNT=$(python3 -c "
import json; d = json.load(open('$TASKS_FILE'))
print(d.get('backlog_count', 0))" 2>/dev/null || echo 0)
fi

if [ "$TODO_COUNT" = "0" ] && [ "$BACKLOG_COUNT" -ge "$MIN_BACKLOG" ]; then
    log "No todo tickets, backlog is healthy ($BACKLOG_COUNT/$MIN_BACKLOG). Exiting."
    # A no-op run is a *successful* run, and the breaker counts consecutive
    # failed runs. Reaching this line proves every component the breaker guards
    # is working: the repo synced, deploy ran, and Linear answered.
    #
    # Without this the counter reset only after a session that did work, so
    # failures accumulated across days with healthy runs in between. On
    # 2026-08-13 it still held a git-pull-conflict whose cause had been fixed
    # hours earlier, and the history carried entries from 30 Jul, 6 Aug and
    # 10 Aug all counting toward the same three strikes. Two unrelated hiccups
    # next month would have halted Dale on a tally that was mostly archaeology.
    #
    # Deliberately NOT cleared on the other early exits: the STOP file and the
    # halt flag mean nothing ran at all, and the strike and poller-failed paths
    # are degraded runs that prove less than this one does.
    python3 "$SCRIPT_DIR/budget-tracker.py" clear-failures 2>/dev/null
    rm -f "$HALT_FLAG"
    exit 0
fi

# Determine session type
if [ "$TODO_COUNT" = "0" ]; then
    # A generation session exists to create tickets, and its only defence
    # against duplicates is the backlog list in the prompt. If the poll failed,
    # that list is stale or absent and Dale proposes blind: on 2026-07-27 this
    # produced 13 tickets in three minutes, three of them duplicates of tickets
    # created four days earlier. Skip rather than guess.
    if [ "$POLLER_OK" != "1" ]; then
        log "Linear poll failed. Skipping generation session (would propose tickets blind)."
        exit 0
    fi
    SESSION_TYPE="generation"
    GEN_TURNS=$(python3 -c "import json; print(json.load(open('$CONFIG')).get('linear', {}).get('generation_session_max_turns', 40))")
    MAX_TURNS="$GEN_TURNS"
    log "=== Starting GENERATION session (backlog $BACKLOG_COUNT/$MIN_BACKLOG, ${MAX_TURNS} turns) ==="
else
    SESSION_TYPE="normal"
    log "=== Starting session ($TODO_COUNT ticket(s), ${MAX_MINUTES}min cap, ${MAX_TURNS} turns) ==="
fi

# --- Run Claude ---

# Load Claude auth
if [ -f /opt/dale/secrets/claude.env ]; then
    source /opt/dale/secrets/claude.env
    export CLAUDE_CODE_OAUTH_TOKEN
fi

# Model and effort. Both are pinned in config.json rather than left to the CLI
# default: an autonomous job that runs hourly should not silently change model
# (and cost profile) when the default moves. Empty values fall back to the
# default, so clearing the config key is the rollback.
CLAUDE_MODEL=$(python3 -c "
import json; print(json.load(open('$CONFIG')).get('claude', {}).get('model', '') or '')" 2>/dev/null || echo "")
CLAUDE_EFFORT=$(python3 -c "
import json; print(json.load(open('$CONFIG')).get('claude', {}).get('effort', '') or '')" 2>/dev/null || echo "")

# Generation sessions think harder. A bad ticket costs Benedict triage time and
# then sits in the backlog for weeks; a longer generation session costs tokens
# once. The backlog cap means these sessions now produce fewer tickets, so the
# extra effort is spent on the ones that survive.
if [ "$SESSION_TYPE" = "generation" ]; then
    GEN_EFFORT=$(python3 -c "
import json; print(json.load(open('$CONFIG')).get('claude', {}).get('generation_effort', '') or '')" 2>/dev/null || echo "")
    [ -n "$GEN_EFFORT" ] && CLAUDE_EFFORT="$GEN_EFFORT"
fi

# Expanded as ${MODEL_ARGS[@]+...} at the call site: an empty array under
# `set -u` is an unbound-variable error on bash < 4.4, and clearing both config
# keys is exactly the documented rollback.
MODEL_ARGS=()
[ -n "$CLAUDE_MODEL" ] && MODEL_ARGS+=(--model "$CLAUDE_MODEL")
[ -n "$CLAUDE_EFFORT" ] && MODEL_ARGS+=(--effort "$CLAUDE_EFFORT")
log "Model: ${CLAUDE_MODEL:-<cli default>} (effort: ${CLAUDE_EFFORT:-<cli default>})"

# Build the session prompt.
#
# It goes to a file and is fed to claude on stdin, NOT as `claude -p "$PROMPT"`.
# A single argv string is capped at MAX_ARG_STRLEN (32 pages = 131072 bytes on
# this box), which is a separate, much smaller limit than ARG_MAX (2MB). The
# prompt grew past it on 2026-08-10 and every session died at exec() with
# "Argument list too long" (exit 126) until the 3-failure breaker halted the
# runner. Nothing in the prompt is meant to be size-bounded, so the fix is to
# stop routing it through argv rather than to trim it. Redirect, not a pipe:
# under `set -o pipefail` a SIGPIPE'd writer would overwrite claude's exit code
# and break the "124 means a normal timeout" branch below.
PROMPT_FILE=$(mktemp "${TMPDIR:-/tmp}/dale-prompt-XXXXXX")
python3 "$SCRIPT_DIR/session-prompt.py" --session-type "$SESSION_TYPE" \
    > "$PROMPT_FILE" 2>>"$LOG_DIR/prompt-errors.log" || {
    log "Failed to build session prompt."
    python3 "$SCRIPT_DIR/budget-tracker.py" log-failure "prompt-build-failed"
    exit 1
}
PROMPT_BYTES=$(stat -c%s "$PROMPT_FILE" 2>/dev/null || stat -f%z "$PROMPT_FILE" 2>/dev/null || echo 0)
log "Prompt: ${PROMPT_BYTES}B ($SESSION_TYPE)"

# Run with timeout + retry on empty output
SECONDS_LIMIT=$((MAX_MINUTES * 60))
MAX_ATTEMPTS=3
ATTEMPT=0
EXIT_CODE=1

while [ "$ATTEMPT" -lt "$MAX_ATTEMPTS" ]; do
    ATTEMPT=$((ATTEMPT + 1))

    if [ "$ATTEMPT" -gt 1 ]; then
        log "Retry attempt $ATTEMPT/$MAX_ATTEMPTS (waiting 30s)"
        sleep 30
    fi

    timeout "${SECONDS_LIMIT}" claude -p \
        --dangerously-skip-permissions \
        --output-format json \
        --max-turns "$MAX_TURNS" \
        ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} \
        < "$PROMPT_FILE" \
        > "$SESSION_LOG" 2>"$LOG_DIR/claude-stderr-$TODAY-$HOUR.log"

    EXIT_CODE=$?
    OUTPUT_SIZE=$(stat -c%s "$SESSION_LOG" 2>/dev/null || stat -f%z "$SESSION_LOG" 2>/dev/null || echo 0)

    if [ "$EXIT_CODE" -eq 0 ] || [ "$EXIT_CODE" -eq 124 ]; then
        if [ "$EXIT_CODE" -eq 124 ]; then
            log "Session timed out after ${MAX_MINUTES} minutes (this is normal)"
        fi
        break
    fi

    # Non-zero exit with empty output = transient failure, worth retrying
    if [ "$OUTPUT_SIZE" -le 1 ] && [ "$ATTEMPT" -lt "$MAX_ATTEMPTS" ]; then
        log "Claude exited with code $EXIT_CODE, empty output (${OUTPUT_SIZE}B). Will retry."
    else
        log "Claude exited with code $EXIT_CODE (attempt $ATTEMPT, output ${OUTPUT_SIZE}B)"
        python3 "$SCRIPT_DIR/budget-tracker.py" log-failure "claude-exit-$EXIT_CODE"
        break
    fi
done

# --- Post-run ---

# Log token usage
python3 "$SCRIPT_DIR/budget-tracker.py" log-session "$SESSION_LOG" 2>>"$LOG_DIR/cron.log"

# Push any commits
cd "$REPO_DIR"
UNPUSHED=$(git log origin/main..HEAD --oneline 2>/dev/null)
if [ -n "$UNPUSHED" ]; then
    log "Pushing commits: $(echo "$UNPUSHED" | wc -l | tr -d ' ') commit(s)"

    # Was a bare push whose failure logged "will retry next session". It did not
    # retry; it stranded the commits and broke the next session's pull.
    git_sync_push "$LOG_DIR/git-errors.log"
    PUSH_STATUS=$?

    if [ "$PUSH_STATUS" -eq 0 ]; then
        if [ "$GIT_SYNC_REBASED" = "1" ]; then
            log "Push was rejected, rebased onto origin/main and pushed."
        fi
    else
        REASON=$(git_sync_explain "$PUSH_STATUS")
        log "Git push FAILED ($REASON). Commits are local and the next session will fail its pull."
        python3 "$SCRIPT_DIR/notify.py" alert \
            "Autonomous Dale could not push: $REASON. /opt/dale/repo is ahead of origin and the next session will fail its pull. Fix: cd /opt/dale/repo && git rebase origin/main && git push." \
            >/dev/null 2>&1 || true
    fi
fi

# Clear failure counter on successful completion
if [ "$EXIT_CODE" -eq 0 ] || [ "$EXIT_CODE" -eq 124 ]; then
    python3 "$SCRIPT_DIR/budget-tracker.py" clear-failures 2>/dev/null
    rm -f "$HALT_FLAG"
fi

log "=== Session complete (exit: $EXIT_CODE) ==="
