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

# Copy static assets (favicon, OG image) to dashboard dir
if [ -d "$REPO_TOOLS/scrapers/static" ]; then
    cp -a "$REPO_TOOLS/scrapers/static/"* /opt/dale/dashboard/ 2>/dev/null
    log "Copied static assets to dashboard"
fi

# Ensure executables
chmod +x /opt/dale/scrapers/run-all-scrapers.sh 2>/dev/null
chmod +x /opt/dale/autonomous/dale-runner.sh 2>/dev/null
chmod +x /opt/dale/autonomous/weekly-pester.py 2>/dev/null
chmod +x /opt/dale/autonomous/check-weekly-update.py 2>/dev/null

# Sync weekly updates from repo to data dir (allows submitting updates via git)
REPO_UPDATES="$REPO_TOOLS/../weekly-updates"
DATA_UPDATES="/opt/dale/data/weekly-updates"
if [ -d "$REPO_UPDATES" ]; then
    mkdir -p "$DATA_UPDATES"
    cp -n "$REPO_UPDATES"/*.md "$DATA_UPDATES/" 2>/dev/null
    log "Synced weekly updates from repo"
fi

log "Deploy complete"
