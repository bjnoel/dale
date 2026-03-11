#!/usr/bin/env bash
# Deploy scripts from repo to server locations.
# Source of truth: /opt/dale/repo/tools/
# Targets: /opt/dale/scrapers/, /opt/dale/autonomous/
#
# Called by dale-runner.sh after git pull, and by run-all-scrapers.sh.
# Can also be run manually: ./deploy.sh

set -uo pipefail

REPO_TOOLS="/opt/dale/repo/tools"
LOG="/opt/dale/autonomous/logs/deploy.log"

log() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) deploy: $1" >> "$LOG"
}

if [ ! -d "$REPO_TOOLS" ]; then
    echo "ERROR: Repo tools dir not found at $REPO_TOOLS" >&2
    exit 1
fi

# Sync scrapers (exclude data, logs, __pycache__)
rsync -a --delete \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    "$REPO_TOOLS/scrapers/" /opt/dale/scrapers/
log "Synced scrapers"

# Sync autonomous scripts (exclude logs, approvals, __pycache__, STOP file)
rsync -a \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='logs/' \
    --exclude='approvals/' \
    --exclude='STOP' \
    "$REPO_TOOLS/autonomous/" /opt/dale/autonomous/
log "Synced autonomous"

# Ensure executables
chmod +x /opt/dale/scrapers/run-all-scrapers.sh 2>/dev/null
chmod +x /opt/dale/autonomous/dale-runner.sh 2>/dev/null

log "Deploy complete"
