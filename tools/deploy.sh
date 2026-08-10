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

# Checksum the modules subscribe-server holds in memory, so we can tell whether
# this deploy actually needs a restart. Python imports at process start, so a
# changed admin_view.py or stocklib module sits on disk doing nothing until the
# service is bounced -- which is how the DEC-263 /admin work deployed "successfully"
# on 2026-08-06 and never appeared on the page (the process had been up since
# 2026-08-03). DAL-263.
server_modules_sum() {
    cat /opt/dale/scrapers/subscribe_server.py \
        /opt/dale/scrapers/admin_view.py \
        /opt/dale/scrapers/digest_archive.py \
        /opt/dale/scrapers/stocklib/*.py 2>/dev/null | md5sum | cut -d' ' -f1
}
SERVER_SUM_BEFORE=$(server_modules_sum)

# Sync scrapers (exclude data, logs, __pycache__)
rsync -a --delete \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    "$REPO_TOOLS/scrapers/" /opt/dale/scrapers/
log "Synced scrapers"

# Restart only when one of those modules actually changed. Gating on the
# checksum rather than on "did we deploy" matters because dale-runner.sh runs
# deploy.sh every hour; gating on the latter would bounce the service 24 times a
# day and drop whatever subscribe request was in flight each time.
SERVER_SUM_AFTER=$(server_modules_sum)
if [ "$SERVER_SUM_BEFORE" != "$SERVER_SUM_AFTER" ]; then
    if sudo -n systemctl restart subscribe-server 2>>"$LOG"; then
        log "subscribe-server modules changed: restarted subscribe-server"
    else
        # Non-fatal, but it must be loud: the symptom otherwise is a deploy that
        # reports success while the live page keeps serving the old code.
        log "WARNING: subscribe-server modules changed but restart FAILED. /admin and the subscribe routes are still running old code."
        echo "WARNING: subscribe-server restart failed after deploy; live code is stale." >&2
    fi
else
    log "subscribe-server modules unchanged: no restart"
fi

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
chmod +x /opt/dale/autonomous/treesmith_analytics.py 2>/dev/null
chmod +x /opt/dale/autonomous/merge-nursery-inbound.sh 2>/dev/null

# Publish the nursery relationship register to the data dir so the /admin page
# can render it (DAL-80). The repo copy stays the source of truth: git history is
# the audit log for who we contacted and when.
REPO_CONTACTS="$REPO_TOOLS/../data/nursery-contacts.json"
if [ -f "$REPO_CONTACTS" ]; then
    cp -a "$REPO_CONTACTS" /opt/dale/data/nursery-contacts.json
    log "Published nursery register to data dir"
fi

# Sync weekly updates from repo to data dir (allows submitting updates via git)
REPO_UPDATES="$REPO_TOOLS/../weekly-updates"
DATA_UPDATES="/opt/dale/data/weekly-updates"
if [ -d "$REPO_UPDATES" ]; then
    mkdir -p "$DATA_UPDATES"
    cp -n "$REPO_UPDATES"/*.md "$DATA_UPDATES/" 2>/dev/null
    log "Synced weekly updates from repo"
fi

# Post-deploy verification: check live dashboard is still healthy. The dataset now
# lives in data.js (the big file); index.html is small by design, so sanity-check both.
DASHBOARD="/opt/dale/dashboard/index.html"
DATA_JS="/opt/dale/dashboard/data.js"
if [ -f "$DASHBOARD" ] && [ -f "$DATA_JS" ]; then
    HTML_SIZE=$(stat -c%s "$DASHBOARD" 2>/dev/null || stat -f%z "$DASHBOARD" 2>/dev/null || echo 0)
    DATA_SIZE=$(stat -c%s "$DATA_JS" 2>/dev/null || stat -f%z "$DATA_JS" 2>/dev/null || echo 0)
    if [ "$HTML_SIZE" -lt 8000 ] || [ "$DATA_SIZE" -lt 500000 ]; then
        log "WARNING: dashboard looks corrupt after deploy (index.html ${HTML_SIZE}b, data.js ${DATA_SIZE}b)!"
        echo "WARNING: treestock.com.au dashboard suspiciously small (html ${HTML_SIZE}b, data ${DATA_SIZE}b). Check immediately." >&2
    else
        log "Deploy verified: index.html ${HTML_SIZE}b, data.js ${DATA_SIZE}b OK"
    fi
else
    log "WARNING: dashboard index.html or data.js not found after deploy!"
fi

# Purge the Cloudflare edge cache when a NEW commit was deployed, so static-asset,
# robots.txt and page changes go live immediately instead of waiting out the 1-day
# edge TTL. Gated on the deployed commit SHA so dale-runner's hourly no-op deploys
# don't flush the edge every hour. (The nightly run-all-scrapers.sh purges on its
# own after rebuilding pages.)
SHA_FILE="/opt/dale/.cf-last-deploy-sha"
NEW_SHA="$(git -C /opt/dale/repo rev-parse HEAD 2>/dev/null || echo unknown)"
OLD_SHA="$(cat "$SHA_FILE" 2>/dev/null || echo none)"
if [ "$NEW_SHA" != "unknown" ] && [ "$NEW_SHA" != "$OLD_SHA" ]; then
    log "New deploy ($OLD_SHA -> $NEW_SHA): purging Cloudflare cache"
    bash "$REPO_TOOLS/scrapers/purge_cloudflare.sh" >>"$LOG" 2>&1
    echo "$NEW_SHA" > "$SHA_FILE"
else
    log "No new commit since last deploy ($NEW_SHA): skipping Cloudflare purge"
fi

log "Deploy complete"
