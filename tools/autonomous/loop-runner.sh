#!/usr/bin/env bash
# Loop runner — keeps running dale-runner.sh until no Todo tickets remain
# Safety cap: 10 iterations max
#
# Recovered into the repo by DAL-281, unchanged. It had been sitting on the box
# untracked because deploy.sh rsyncs autonomous/ WITHOUT --delete, so a
# server-only file survives there indefinitely and invisibly.
#
# Nothing invokes it: it is not in the crontab and no other script calls it. It
# is a manual tool for draining a backlog of Todo tickets in one sitting. Kept
# rather than deleted because it still works and the hourly runner does not
# cover that case, but do not assume it is on a schedule.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$SCRIPT_DIR/logs/cron.log"
MAX_RUNS=10

for i in $(seq 1 $MAX_RUNS); do
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) — === Loop iteration $i/$MAX_RUNS ===" >> "$LOG"

    bash "$SCRIPT_DIR/dale-runner.sh"

    if [ -f "$SCRIPT_DIR/STOP" ]; then
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) — STOP file found, ending loop" >> "$LOG"
        break
    fi

    # Re-poll Linear for fresh Todo count
    source /opt/dale/secrets/linear.env 2>/dev/null
    TODO_COUNT=$(python3 "$SCRIPT_DIR/linear_poller.py" --dry-run 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)[\"todo\"]))" 2>/dev/null)

    if [ "${TODO_COUNT:-0}" -eq 0 ]; then
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) — No Todo tickets remaining, loop complete" >> "$LOG"
        break
    fi

    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) — $TODO_COUNT Todo tickets remaining, continuing..." >> "$LOG"
    sleep 10
done

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) — === Loop runner finished ($i iterations) ===" >> "$LOG"
