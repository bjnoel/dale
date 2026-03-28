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
    JS_CHECK=$(awk '/<script>/{p=1; next} /<\/script>/{p=0} p' "$DASHBOARD_FILE" | node --check /dev/stdin 2>&1)
    if [ $? -eq 0 ]; then
        echo "$LOG_PREFIX Dashboard build complete. JS syntax verified."
    else
        echo "$LOG_PREFIX ERROR: Dashboard JS syntax error: $JS_CHECK"
        if [ -f "$DASHBOARD_BACKUP" ]; then
            cp "$DASHBOARD_BACKUP" "$DASHBOARD_FILE"
            echo "$LOG_PREFIX Rollback complete."
        fi
    fi
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
YESTERDAY=$(date -d 'yesterday' '+%Y-%m-%d' 2>/dev/null || date -v-1d '+%Y-%m-%d')
DIGEST_DIR="$BEE_DASHBOARD_DIR/digest"
mkdir -p "$DIGEST_DIR"

# Text digest (plain, for email)
python3 "$SCRIPT_DIR/bee_daily_digest.py" "$PROJECT_DIR/data/bee-stock" \
    --save "$BEE_DASHBOARD_DIR/digest.txt" 2>&1

# Dated shareable page at /digest/YYYY-MM-DD.html
PREV_ARG=""
if [ -f "$DIGEST_DIR/$YESTERDAY.html" ]; then
    PREV_ARG="--prev-date $YESTERDAY"
fi
python3 "$SCRIPT_DIR/bee_daily_digest.py" "$PROJECT_DIR/data/bee-stock" \
    --page --date "$TODAY" $PREV_ARG \
    --save "$DIGEST_DIR/$TODAY.html" 2>&1

# Update yesterday's page to add a "next" link pointing to today
if [ -f "$DIGEST_DIR/$YESTERDAY.html" ]; then
    DAY_BEFORE=$(date -d '2 days ago' '+%Y-%m-%d' 2>/dev/null || date -v-2d '+%Y-%m-%d')
    PREV2_ARG=""
    if [ -f "$DIGEST_DIR/$DAY_BEFORE.html" ]; then
        PREV2_ARG="--prev-date $DAY_BEFORE"
    fi
    python3 "$SCRIPT_DIR/bee_daily_digest.py" "$PROJECT_DIR/data/bee-stock" \
        --page --date "$YESTERDAY" $PREV2_ARG --next-date "$TODAY" \
        --save "$DIGEST_DIR/$YESTERDAY.html" 2>&1
fi

# Also write a non-dated /digest.html that redirects to today's dated page
cat > "$BEE_DASHBOARD_DIR/digest.html" << HTMLEOF
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="0; url=/digest/$TODAY.html">
<title>Redirecting...</title>
</head>
<body>
<p>Redirecting to <a href="/digest/$TODAY.html">today's digest</a>...</p>
</body>
</html>
HTMLEOF

# Build archive index page
python3 "$SCRIPT_DIR/bee_daily_digest.py" --build-index "$DIGEST_DIR" 2>&1

echo "$LOG_PREFIX Digest complete (dated page at /digest/$TODAY.html)."

# Build category landing pages (SEO)
echo "$LOG_PREFIX Building category pages..."
if python3 "$SCRIPT_DIR/build_bee_category_pages.py" "$PROJECT_DIR/data/bee-stock" "$BEE_DASHBOARD_DIR" 2>&1; then
    echo "$LOG_PREFIX Category pages complete."
else
    echo "$LOG_PREFIX WARNING: Category page build failed (non-fatal)."
fi

# Build retailer profile pages
echo "$LOG_PREFIX Building retailer pages..."
if python3 "$SCRIPT_DIR/build_bee_retailer_pages.py" "$PROJECT_DIR/data/bee-stock" "$BEE_DASHBOARD_DIR" 2>&1; then
    echo "$LOG_PREFIX Retailer pages complete."
else
    echo "$LOG_PREFIX WARNING: Retailer page build failed (non-fatal)."
fi

# Build Tailwind CSS (purged, scans all generated HTML for used classes)
echo "$LOG_PREFIX Building Tailwind CSS..."
TREESTOCK_SCRIPT_DIR="$(dirname "$SCRIPT_DIR")"
if tailwindcss --input "$TREESTOCK_SCRIPT_DIR/tailwind-input.css" \
    --output "$BEE_DASHBOARD_DIR/styles.css" \
    --content "$BEE_DASHBOARD_DIR/**/*.html" --minify 2>&1; then
    echo "$LOG_PREFIX Tailwind CSS complete ($(wc -c < "$BEE_DASHBOARD_DIR/styles.css") bytes)."
else
    echo "$LOG_PREFIX WARNING: Tailwind CSS build failed (non-fatal)"
fi

echo "$LOG_PREFIX Bee pipeline complete."
