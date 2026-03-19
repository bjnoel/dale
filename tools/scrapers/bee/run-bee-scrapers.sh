#!/bin/bash
# Run all beekeeping supply scrapers, build dashboard + digest
# Intended to be run daily via cron (after nursery scrapers)
#
# Usage: ./run-bee-scrapers.sh
# Cron:  30 6 * * * /opt/dale/scrapers/bee/run-bee-scrapers.sh >> /opt/dale/data/bee-scraper.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="/opt/dale"
export DALE_DATA_DIR="$PROJECT_DIR/data"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

echo "$LOG_PREFIX Starting beekeeping supply scrape..."

# Shopify retailers
echo "$LOG_PREFIX Scraping Shopify bee retailers..."
cd "$SCRIPT_DIR"
python3 "$SCRIPT_DIR/shopify_bee_scraper.py" 2>&1

echo "$LOG_PREFIX Scrape complete."

# Backup previous dashboard before rebuilding
BEE_DASHBOARD_DIR="$PROJECT_DIR/bee-dashboard"
mkdir -p "$BEE_DASHBOARD_DIR"
DASHBOARD_FILE="$BEE_DASHBOARD_DIR/index.html"
DASHBOARD_BACKUP="$BEE_DASHBOARD_DIR/index.html.bak"
if [ -f "$DASHBOARD_FILE" ]; then
    cp "$DASHBOARD_FILE" "$DASHBOARD_BACKUP"
fi

# Build dashboard
echo "$LOG_PREFIX Building bee dashboard..."
if python3 "$SCRIPT_DIR/build_bee_dashboard.py" "$PROJECT_DIR/data/bee-stock" "$BEE_DASHBOARD_DIR" 2>&1; then
    echo "$LOG_PREFIX Dashboard build complete."
else
    BUILD_EXIT=$?
    echo "$LOG_PREFIX ERROR: Dashboard build failed (exit $BUILD_EXIT)."
    if [ -f "$DASHBOARD_BACKUP" ]; then
        cp "$DASHBOARD_BACKUP" "$DASHBOARD_FILE"
        echo "$LOG_PREFIX Rollback complete."
    fi
fi

# Generate daily digest
echo "$LOG_PREFIX Generating daily digest..."
TODAY=$(date '+%Y-%m-%d')
ARCHIVE_DIR="$BEE_DASHBOARD_DIR/archive"
mkdir -p "$ARCHIVE_DIR"

# Text digest
python3 "$SCRIPT_DIR/bee_daily_digest.py" "$PROJECT_DIR/data/bee-stock" \
    --save "$BEE_DASHBOARD_DIR/digest.txt" 2>&1

# Shareable web page digest
python3 "$SCRIPT_DIR/bee_daily_digest.py" "$PROJECT_DIR/data/bee-stock" \
    --page --save "$BEE_DASHBOARD_DIR/digest.html" 2>&1

# Archive dated copy
cp "$BEE_DASHBOARD_DIR/digest.html" "$ARCHIVE_DIR/digest-$TODAY.html"
echo "$LOG_PREFIX Digest complete (archived as $TODAY)."

echo "$LOG_PREFIX Bee pipeline complete."
