#!/usr/bin/env bash
# Autonomous Dale — cron wrapper
# Called by cron at 18:00 UTC (2:00 AWST)
# Pre-checks, runs Claude headlessly, handles post-run tasks.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$SCRIPT_DIR/config.json"
LOG_DIR="$SCRIPT_DIR/logs"
STOP_FILE="$SCRIPT_DIR/STOP"
TODAY=$(date -u +%Y-%m-%d)
SESSION_LOG="$LOG_DIR/session-$TODAY.json"

mkdir -p "$LOG_DIR"

log() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) — $1" >> "$LOG_DIR/cron.log"
}

log "=== Starting autonomous session ==="

# --- Pre-checks ---

# 1. STOP file
if [ -f "$STOP_FILE" ]; then
    log "STOP file exists. Aborting."
    python3 "$SCRIPT_DIR/notify.py" alert "STOP file exists — autonomous run halted"
    exit 0
fi

# 2. Consecutive failures
FAILURE_COUNT=$(python3 "$SCRIPT_DIR/budget-tracker.py" failure-count 2>/dev/null | tail -1)
if [ "${FAILURE_COUNT:-0}" -ge 3 ]; then
    log "3+ consecutive failures ($FAILURE_COUNT). Halting."
    python3 "$SCRIPT_DIR/notify.py" alert "3 consecutive failures — autonomous run halted. Check logs."
    exit 0
fi

# 3. Time window check (17:00-01:00 UTC)
HOUR=$(date -u +%-H)
if [ "$HOUR" -ge 1 ] && [ "$HOUR" -lt 17 ]; then
    log "Outside run window (UTC hour: $HOUR). Skipping."
    exit 0
fi

# 4. Read config
REPO_DIR=$(python3 -c "import json; print(json.load(open('$CONFIG'))['paths']['repo'])")
MAX_MINUTES=$(python3 -c "import json; print(json.load(open('$CONFIG'))['budget']['max_session_duration_minutes'])")
MAX_TURNS=$(python3 -c "import json; print(json.load(open('$CONFIG'))['budget']['max_turns'])")

# 5. Repo health
if [ ! -d "$REPO_DIR/.git" ]; then
    log "Repo not found at $REPO_DIR. Aborting."
    python3 "$SCRIPT_DIR/notify.py" alert "Git repo not found at $REPO_DIR"
    python3 "$SCRIPT_DIR/budget-tracker.py" log-failure "repo-not-found"
    exit 1
fi

cd "$REPO_DIR"

# Pull latest
git fetch origin 2>>"$LOG_DIR/git-errors.log" || {
    log "Git fetch failed."
    python3 "$SCRIPT_DIR/notify.py" alert "Git fetch failed"
    python3 "$SCRIPT_DIR/budget-tracker.py" log-failure "git-fetch-failed"
    exit 1
}

git pull --ff-only origin main 2>>"$LOG_DIR/git-errors.log" || {
    log "Git pull failed (possible conflicts)."
    python3 "$SCRIPT_DIR/notify.py" alert "Git pull --ff-only failed — possible conflicts on main"
    python3 "$SCRIPT_DIR/budget-tracker.py" log-failure "git-pull-conflict"
    exit 1
}

# --- Run Claude ---

log "Running Claude (${MAX_MINUTES}min cap, ${MAX_TURNS} max turns)"

# Load Claude auth
if [ -f /opt/dale/secrets/claude.env ]; then
    source /opt/dale/secrets/claude.env
    export CLAUDE_CODE_OAUTH_TOKEN
fi

# Build the session prompt
PROMPT=$(python3 "$SCRIPT_DIR/session-prompt.py" 2>>"$LOG_DIR/prompt-errors.log") || {
    log "Failed to build session prompt."
    python3 "$SCRIPT_DIR/budget-tracker.py" log-failure "prompt-build-failed"
    exit 1
}

# Run with timeout
SECONDS_LIMIT=$((MAX_MINUTES * 60))
timeout "${SECONDS_LIMIT}" claude -p "$PROMPT" \
    --output-format json \
    --max-turns "$MAX_TURNS" \
    > "$SESSION_LOG" 2>"$LOG_DIR/claude-stderr-$TODAY.log"

EXIT_CODE=$?

if [ "$EXIT_CODE" -eq 124 ]; then
    log "Session timed out after ${MAX_MINUTES} minutes (this is normal)"
elif [ "$EXIT_CODE" -ne 0 ]; then
    log "Claude exited with code $EXIT_CODE"
    python3 "$SCRIPT_DIR/budget-tracker.py" log-failure "claude-exit-$EXIT_CODE"
    # Still try to send summary of whatever happened
fi

# --- Post-run ---

# Log token usage
python3 "$SCRIPT_DIR/budget-tracker.py" log-session "$SESSION_LOG" 2>>"$LOG_DIR/cron.log"

# Push any commits
cd "$REPO_DIR"
UNPUSHED=$(git log origin/main..HEAD --oneline 2>/dev/null)
if [ -n "$UNPUSHED" ]; then
    log "Pushing commits: $(echo "$UNPUSHED" | wc -l | tr -d ' ') commit(s)"
    git push origin main 2>>"$LOG_DIR/git-errors.log" || {
        log "Git push failed"
        python3 "$SCRIPT_DIR/notify.py" alert "Git push failed after autonomous session"
    }
fi

# Send summary email
python3 "$SCRIPT_DIR/notify.py" summary "$SESSION_LOG" 2>>"$LOG_DIR/cron.log"

# Clear failure counter on successful completion
if [ "$EXIT_CODE" -eq 0 ] || [ "$EXIT_CODE" -eq 124 ]; then
    python3 "$SCRIPT_DIR/budget-tracker.py" clear-failures 2>/dev/null
fi

log "=== Session complete (exit: $EXIT_CODE) ==="
