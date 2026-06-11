#!/bin/bash
# Run all nursery stock scrapers, update history, build dashboard + digest
# Intended to be run daily via cron
#
# Usage: ./run-all-scrapers.sh
# Cron:  0 6 * * * /opt/dale/scrapers/run-all-scrapers.sh >> /opt/dale/data/scraper.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="/opt/dale"
export DALE_DATA_DIR="$PROJECT_DIR/data"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

echo "$LOG_PREFIX Starting nursery stock scrape..."

# Shopify nurseries (Ross Creek, Ladybird, Fruitopia, Fruit Salad Trees, Diggers, All Season Plants WA, Aus Nurseries, Fruit Tree Cottage)
echo "$LOG_PREFIX Scraping Shopify nurseries..."
python3 "$SCRIPT_DIR/shopify_scraper.py" 2>&1

# Daleys (custom scraper)
echo "$LOG_PREFIX Scraping Daleys..."
python3 "$SCRIPT_DIR/daleys_scraper.py" 2>&1

# Ecwid nurseries (Primal Fruits)
echo "$LOG_PREFIX Scraping Ecwid nurseries..."
python3 "$SCRIPT_DIR/ecwid_scraper.py" 2>&1

# WooCommerce nurseries (Guildford Garden Centre)
echo "$LOG_PREFIX Scraping WooCommerce nurseries..."
python3 "$SCRIPT_DIR/woocommerce_scraper.py" 2>&1

# BigCommerce nurseries (Heritage Fruit Trees)
echo "$LOG_PREFIX Scraping BigCommerce nurseries..."
python3 "$SCRIPT_DIR/bigcommerce_scraper.py" 2>&1

echo "$LOG_PREFIX Scrape complete."

# Update availability history
echo "$LOG_PREFIX Updating availability history..."
python3 "$SCRIPT_DIR/availability_tracker.py" "$PROJECT_DIR/data/nursery-stock" 2>&1

# Backup previous dashboard before rebuilding (keep last-known-good for rollback)
DASHBOARD_FILE="$PROJECT_DIR/dashboard/index.html"
DASHBOARD_BACKUP="$PROJECT_DIR/dashboard/index.html.bak"
if [ -f "$DASHBOARD_FILE" ]; then
    cp "$DASHBOARD_FILE" "$DASHBOARD_BACKUP"
fi

# Build dashboard (atomic write + post-build verification built into script).
# --needs-review-out runs the categorize ladder (DEC-200) and feeds the /admin
# needs-review queue; it does not change the dashboard output.
echo "$LOG_PREFIX Building dashboard..."
if python3 "$SCRIPT_DIR/build-dashboard.py" "$PROJECT_DIR/data/nursery-stock" "$PROJECT_DIR/dashboard" \
    --needs-review-out "$PROJECT_DIR/data/needs-review.json" 2>&1; then
    # Verify JS syntax of the dashboard client app (now external: static/dashboard.js,
    # copied to the dashboard dir by deploy.sh). Temp copy because `node --check
    # /dev/stdin` is broken on Node 22 (ENOENT on /proc fd path).
    JS_TMP=$(mktemp --suffix=.js)
    cp "$SCRIPT_DIR/static/dashboard.js" "$JS_TMP"
    JS_ERR_TMP=$(mktemp)
    if node --check "$JS_TMP" >"$JS_ERR_TMP" 2>&1; then
        echo "$LOG_PREFIX Dashboard build complete. JS syntax verified."
    else
        echo "$LOG_PREFIX ERROR: Dashboard JS syntax error: $(cat "$JS_ERR_TMP")"
        echo "$LOG_PREFIX Rolling back to backup."
        if [ -f "$DASHBOARD_BACKUP" ]; then
            cp "$DASHBOARD_BACKUP" "$DASHBOARD_FILE"
            echo "$LOG_PREFIX Rollback complete. Serving previous dashboard."
        else
            echo "$LOG_PREFIX ERROR: No backup available. Dashboard may have broken JS!"
        fi
    fi
    rm -f "$JS_TMP" "$JS_ERR_TMP"
else
    BUILD_EXIT=$?
    echo "$LOG_PREFIX ERROR: Dashboard build failed (exit $BUILD_EXIT). Rolling back to backup."
    if [ -f "$DASHBOARD_BACKUP" ]; then
        cp "$DASHBOARD_BACKUP" "$DASHBOARD_FILE"
        echo "$LOG_PREFIX Rollback complete. Serving previous dashboard."
    else
        echo "$LOG_PREFIX ERROR: No backup available. Dashboard may be missing!"
    fi
fi

# Build the /bush-tucker/ category landing page (DEC-200 / DAL-198): same
# dashboard components, scoped to bush tucker stock, into dashboard/bush-tucker/.
# Non-fatal: a failure here must not block the homepage or the rest of the run.
echo "$LOG_PREFIX Building bush tucker landing page..."
mkdir -p "$PROJECT_DIR/dashboard/bush-tucker"
python3 "$SCRIPT_DIR/build-dashboard.py" "$PROJECT_DIR/data/nursery-stock" \
    "$PROJECT_DIR/dashboard/bush-tucker" --category bush_tucker 2>&1 \
    || echo "$LOG_PREFIX WARNING: Bush tucker landing build failed (non-fatal)"

# Generate daily digest (text + HTML + shareable web page versions)
echo "$LOG_PREFIX Generating daily digest..."
TODAY=$(date '+%Y-%m-%d')
DIGEST_DIR="$PROJECT_DIR/dashboard"
ARCHIVE_DIR="$DIGEST_DIR/archive"
mkdir -p "$ARCHIVE_DIR"

# Text digests (for FB groups)
python3 "$SCRIPT_DIR/daily_digest.py" "$PROJECT_DIR/data/nursery-stock" \
    --save "$DIGEST_DIR/digest.txt" 2>&1
python3 "$SCRIPT_DIR/daily_digest.py" "$PROJECT_DIR/data/nursery-stock" \
    --wa-only --save "$DIGEST_DIR/digest-wa.txt" 2>&1

# Email HTML digest (unfiltered; send_digest.py handles per-subscriber state filtering)
python3 "$SCRIPT_DIR/daily_digest.py" "$PROJECT_DIR/data/nursery-stock" \
    --html --save "$DIGEST_DIR/digest-email.html" 2>&1

# Shareable web page digests (main ones served at /digest.html)
python3 "$SCRIPT_DIR/daily_digest.py" "$PROJECT_DIR/data/nursery-stock" \
    --page --save "$DIGEST_DIR/digest.html" 2>&1
python3 "$SCRIPT_DIR/daily_digest.py" "$PROJECT_DIR/data/nursery-stock" \
    --page --wa-only --save "$DIGEST_DIR/digest-wa.html" 2>&1

# Archive dated copies
cp "$DIGEST_DIR/digest.html" "$ARCHIVE_DIR/digest-$TODAY.html"
cp "$DIGEST_DIR/digest-wa.html" "$ARCHIVE_DIR/digest-wa-$TODAY.html"
echo "$LOG_PREFIX Digest complete (archived as $TODAY)."

# Build price/stock change history page
echo "$LOG_PREFIX Building history page..."
python3 "$SCRIPT_DIR/build_history.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" 2>&1
python3 "$SCRIPT_DIR/build_history.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" --wa-only 2>&1
echo "$LOG_PREFIX History page complete."

# Build nursery profile pages (SEO)
echo "$LOG_PREFIX Building nursery pages..."
python3 "$SCRIPT_DIR/build_nursery_pages.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Nursery page build failed (non-fatal)"
echo "$LOG_PREFIX Nursery pages complete."

# Build nursery comparison page (SEO)
echo "$LOG_PREFIX Building nursery comparison page..."
python3 "$SCRIPT_DIR/build_nursery_compare.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Nursery compare page build failed (non-fatal)"
echo "$LOG_PREFIX Nursery comparison page complete."

# Build species pages (SEO)
echo "$LOG_PREFIX Building species pages..."
python3 "$SCRIPT_DIR/build_species_pages.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Species page build failed (non-fatal)"
echo "$LOG_PREFIX Species pages complete."

# Build compare pages (price comparison, SEO)
echo "$LOG_PREFIX Building compare pages..."
python3 "$SCRIPT_DIR/build_compare_pages.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Compare page build failed (non-fatal)"
echo "$LOG_PREFIX Compare pages complete."

# Build rare finds page
echo "$LOG_PREFIX Building rare finds page..."
python3 "$SCRIPT_DIR/build_rare_finds.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Rare finds page build failed (non-fatal)"
echo "$LOG_PREFIX Rare finds page complete."

# Build variety pages (cultivar-level SEO)
echo "$LOG_PREFIX Building variety pages..."
python3 "$SCRIPT_DIR/build_variety_pages.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Variety page build failed (non-fatal)"
echo "$LOG_PREFIX Variety pages complete."

# Build companion planting guide (SEO content)
echo "$LOG_PREFIX Building companion planting guide..."
python3 "$SCRIPT_DIR/build_companion_guide.py" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Companion guide build failed (non-fatal)"
echo "$LOG_PREFIX Companion guide complete."

# Build "when to plant" seasonal planting calendar (SEO content)
echo "$LOG_PREFIX Building when-to-plant calendar..."
python3 "$SCRIPT_DIR/build_when_to_plant.py" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: When-to-plant build failed (non-fatal)"
echo "$LOG_PREFIX When-to-plant calendar complete."

# Build sample digest preview page (subscriber conversion)
echo "$LOG_PREFIX Building sample digest page..."
python3 "$SCRIPT_DIR/build_sample_digest.py" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Sample digest page build failed (non-fatal)"
echo "$LOG_PREFIX Sample digest page complete."

# Build Treesmith app landing page (cross-promotion)
echo "$LOG_PREFIX Building Treesmith landing page..."
python3 "$SCRIPT_DIR/build_treesmith_page.py" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Treesmith landing page build failed (non-fatal)"
echo "$LOG_PREFIX Treesmith landing page complete."

# Build sitemap
echo "$LOG_PREFIX Building sitemap..."
python3 "$SCRIPT_DIR/build_sitemap.py" "$DIGEST_DIR/species" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Sitemap build failed (non-fatal)"
echo "$LOG_PREFIX Sitemap complete."

# Build llms.txt (curated AI/LLM site map; robots.txt ships as a static asset)
echo "$LOG_PREFIX Building llms.txt..."
python3 "$SCRIPT_DIR/build_llms.py" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: llms.txt build failed (non-fatal)"
echo "$LOG_PREFIX llms.txt complete."

# Detect significant stock count changes (surges/drops) across nurseries
echo "$LOG_PREFIX Checking for stock surges..."
python3 "$SCRIPT_DIR/detect_stock_surges.py" "$PROJECT_DIR/data/nursery-stock" 2>&1 || echo "$LOG_PREFIX WARNING: Stock surge detection failed (non-fatal)"
echo "$LOG_PREFIX Stock surge check complete."

# Send digest to email subscribers (frequency=daily only — others handled below).
echo "$LOG_PREFIX Sending digest to email subscribers..."
python3 "$SCRIPT_DIR/send_digest.py" 2>&1 || echo "$LOG_PREFIX WARNING: Digest email send failed (non-fatal)"
echo "$LOG_PREFIX Subscriber send complete."

# On Sundays, also send the weekly summary to subscribers with frequency=weekly.
# date +%u: 1=Mon ... 7=Sun
if [ "$(date +%u)" = "7" ]; then
    echo "$LOG_PREFIX Sending weekly digest to weekly subscribers..."
    python3 "$SCRIPT_DIR/send_weekly_digest.py" 2>&1 || echo "$LOG_PREFIX WARNING: Weekly digest send failed (non-fatal)"
    echo "$LOG_PREFIX Weekly digest send complete."
fi

# Send per-variety restock alerts to watchers
# (Species-level alerts deprecated 2026-04-19: trigger condition was too strict
# to ever fire in practice, and only variety watches are meaningful.)
echo "$LOG_PREFIX Sending variety restock alerts..."
python3 "$SCRIPT_DIR/send_variety_alerts.py" "$PROJECT_DIR/data/nursery-stock" 2>&1 || echo "$LOG_PREFIX WARNING: Variety alerts failed (non-fatal)"
echo "$LOG_PREFIX Variety alert send complete."

# Build location pages (WA/QLD/NSW/VIC, fruit-species-filtered)
echo "$LOG_PREFIX Building location pages..."
python3 "$SCRIPT_DIR/build_location_pages.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Location page build failed (non-fatal)"
echo "$LOG_PREFIX Location pages complete."

# Build species+state combo pages (buy-[species]-trees-[state].html)
echo "$LOG_PREFIX Building species+state combo pages..."
python3 "$SCRIPT_DIR/build_species_state_pages.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" 2>&1 | tail -3 || echo "$LOG_PREFIX WARNING: Species+state page build failed (non-fatal)"
echo "$LOG_PREFIX Species+state combo pages complete."

# Build 404 page (served by Caddy handle_errors)
echo "$LOG_PREFIX Building 404 page..."
python3 "$SCRIPT_DIR/build_404_page.py" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: 404 page build failed (non-fatal)"
echo "$LOG_PREFIX 404 page complete."

# Build Tailwind CSS (purged, scans all generated HTML for used classes)
echo "$LOG_PREFIX Building Tailwind CSS..."
if tailwindcss --input "$SCRIPT_DIR/tailwind-input.css" \
    --output "$DIGEST_DIR/styles.css" \
    --content "$DIGEST_DIR/**/*.html" --minify 2>&1; then
    echo "$LOG_PREFIX Tailwind CSS complete ($(wc -c < "$DIGEST_DIR/styles.css") bytes)."
else
    echo "$LOG_PREFIX WARNING: Tailwind CSS build failed (non-fatal)"
fi

# Purge Cloudflare edge cache so the rebuilt pages go live immediately. HTML is
# edge-cached for 1 day via a Cache Rule; without this the edge would keep serving
# yesterday's pages until the TTL expires. Runs before the smoke test so that
# re-warms the cache with the fresh pages.
echo "$LOG_PREFIX Purging Cloudflare cache..."
bash "$SCRIPT_DIR/purge_cloudflare.sh" 2>&1 || echo "$LOG_PREFIX WARNING: Cloudflare purge failed (non-fatal)"
echo "$LOG_PREFIX Cloudflare purge complete."

# Post-deploy smoke test — check key pages are up and correct size
echo "$LOG_PREFIX Running post-deploy smoke test..."
python3 "$SCRIPT_DIR/smoke_test.py" --quiet 2>&1 || echo "$LOG_PREFIX WARNING: Smoke test failed — alert sent to Benedict"
echo "$LOG_PREFIX Smoke test complete."

# Scrape-health anomaly check (failed runs, zero-product days, 403/429 blocks,
# failure streaks) — alerts Benedict, idempotent per day
echo "$LOG_PREFIX Checking scrape health..."
python3 "$SCRIPT_DIR/detect_scrape_anomalies.py" 2>&1 || echo "$LOG_PREFIX WARNING: Scrape anomaly check failed (non-fatal)"
echo "$LOG_PREFIX Scrape health check complete."
