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
trap 'rm -f "$LOCK_FILE"' EXIT

# 3. Consecutive failures
FAILURE_COUNT=$(python3 "$SCRIPT_DIR/budget-tracker.py" failure-count 2>/dev/null | tail -1)
if [ "${FAILURE_COUNT:-0}" -ge 3 ]; then
    log "3+ consecutive failures ($FAILURE_COUNT). Halting."
    python3 "$SCRIPT_DIR/notify.py" alert "3 consecutive failures — autonomous run halted. Check logs."
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

git fetch origin 2>>"$LOG_DIR/git-errors.log" || {
    log "Git fetch failed."
    python3 "$SCRIPT_DIR/budget-tracker.py" log-failure "git-fetch-failed"
    exit 1
}

git pull --ff-only origin main 2>>"$LOG_DIR/git-errors.log" || {
    log "Git pull failed (possible conflicts)."
    python3 "$SCRIPT_DIR/budget-tracker.py" log-failure "git-pull-conflict"
    exit 1
}

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

# --- Fetch Linear tickets ---

log "Fetching Linear tickets"
python3 "$SCRIPT_DIR/linear_poller.py" 2>>"$LOG_DIR/cron.log" || {
    log "Warning: Linear poller failed (will proceed with stale data if available)"
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
    exit 0
fi

# Determine session type
if [ "$TODO_COUNT" = "0" ]; then
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

# Build the session prompt
PROMPT=$(python3 "$SCRIPT_DIR/session-prompt.py" --session-type "$SESSION_TYPE" 2>>"$LOG_DIR/prompt-errors.log") || {
    log "Failed to build session prompt."
    python3 "$SCRIPT_DIR/budget-tracker.py" log-failure "prompt-build-failed"
    exit 1
}

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

    timeout "${SECONDS_LIMIT}" claude -p "$PROMPT" \
        --dangerously-skip-permissions \
        --output-format json \
        --max-turns "$MAX_TURNS" \
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
    git push origin main 2>>"$LOG_DIR/git-errors.log" || {
        log "Git push failed (will retry next session)"
    }
fi

# Clear failure counter on successful completion
if [ "$EXIT_CODE" -eq 0 ] || [ "$EXIT_CODE" -eq 124 ]; then
    python3 "$SCRIPT_DIR/budget-tracker.py" clear-failures 2>/dev/null
fi

log "=== Session complete (exit: $EXIT_CODE) ==="
