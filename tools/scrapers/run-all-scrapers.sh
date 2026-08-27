#!/bin/bash
# Run all nursery stock scrapers, update history, build dashboard + digest
# Intended to be run daily via cron
#
# Usage: ./run-all-scrapers.sh
# Cron:  0 6 * * * /opt/dale/scrapers/run-all-scrapers.sh >> /opt/dale/data/scraper.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# /opt/dale in production. Overridable so tests/test_run_all_scrapers.py can run
# the real script against a temp tree instead of asserting on a copy of it.
PROJECT_DIR="${DALE_PROJECT_DIR:-/opt/dale}"
export DALE_DATA_DIR="$PROJECT_DIR/data"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

# Number of platform scraper families below, and how many may fail before we
# stop instead of publishing. One family down is a nursery having a bad night;
# most of them down at once is us (our network, our IP blocked, a shared
# dependency), and then yesterday's published site is more truthful than one
# rebuilt from mostly-stale data.
SCRAPER_COUNT=7
MAX_SCRAPER_FAILURES=3

# The alarm must not sit downstream of the failure it exists to report.
# detect_scrape_anomalies.py used to be the last step of this script, below the
# smoke test. On 2026-08-12 the run aborted at the BigCommerce call, so the
# alarm never ran: ok=false was recorded correctly in data/scraper-health/ on
# both dead nights and nobody was told. It now runs the moment the scrapers
# finish, and an EXIT trap fires it even if a later step aborts the run.
SCRAPE_HEALTH_REPORTED=""
report_scrape_health() {
    if [ -n "$SCRAPE_HEALTH_REPORTED" ]; then
        return 0
    fi
    SCRAPE_HEALTH_REPORTED=1
    echo "$LOG_PREFIX Checking scrape health..."
    python3 "$SCRIPT_DIR/detect_scrape_anomalies.py" 2>&1 \
        || echo "$LOG_PREFIX WARNING: Scrape anomaly check failed (non-fatal)"
}
trap report_scrape_health EXIT

# One nursery's outage must degrade that nursery, not the whole publish. These
# six calls were bare under `set -e` until 2026-08-13: Heritage Fruit Trees
# began serving HTTP 503 on every URL, bigcommerce_scraper.py correctly refused
# to write a 0-product snapshot and exited 1, and the run died there, taking
# availability_tracker, the dashboard, all twenty-odd page builders and both
# subscriber sends with it. The site froze for two days (DEC-293).
#
# A failure is never silent: each scraper records ok=false via
# stocklib.scrape_health, and report_scrape_health turns that into an email.
SCRAPER_FAILURES=()

run_scraper() {
    local label="$1"; shift
    if python3 "$@" 2>&1; then
        return 0
    fi
    SCRAPER_FAILURES+=("$label")
    echo "$LOG_PREFIX WARNING: $label scrape failed (continuing with other nurseries)"
}

echo "$LOG_PREFIX Starting nursery stock scrape..."

# Shopify nurseries (Ross Creek, Ladybird, Fruitopia, Fruit Salad Trees, Diggers, All Season Plants WA, Aus Nurseries, Fruit Tree Cottage)
echo "$LOG_PREFIX Scraping Shopify nurseries..."
run_scraper "Shopify" "$SCRIPT_DIR/shopify_scraper.py"

# Daleys (supplier CSV feed, replaced the Plant-List.php scrape 2026-08-20).
# The feed URL is semi-private (obscured path, noindex) so it lives in the
# secrets dir and is never committed. Without it the scraper fails loudly rather
# than writing a short snapshot.
echo "$LOG_PREFIX Scraping Daleys (feed)..."
if [ -f "$PROJECT_DIR/secrets/feeds.env" ]; then
    set -a; . "$PROJECT_DIR/secrets/feeds.env"; set +a
fi
run_scraper "Daleys" "$SCRIPT_DIR/csv_feed_scraper.py"

# Ecwid nurseries (Primal Fruits)
echo "$LOG_PREFIX Scraping Ecwid nurseries..."
run_scraper "Ecwid" "$SCRIPT_DIR/ecwid_scraper.py"

# Wix nurseries (Heaven On Earth)
echo "$LOG_PREFIX Scraping Wix nurseries..."
run_scraper "Wix" "$SCRIPT_DIR/wix_scraper.py"

# WooCommerce nurseries (Guildford Garden Centre)
echo "$LOG_PREFIX Scraping WooCommerce nurseries..."
run_scraper "WooCommerce" "$SCRIPT_DIR/woocommerce_scraper.py"

# BigCommerce nurseries (Heritage Fruit Trees)
echo "$LOG_PREFIX Scraping BigCommerce nurseries..."
run_scraper "BigCommerce" "$SCRIPT_DIR/bigcommerce_scraper.py"

# Squarespace nurseries (Perry's Fruit & Nut, our first South Australian one)
echo "$LOG_PREFIX Scraping Squarespace nurseries..."
run_scraper "Squarespace" "$SCRIPT_DIR/squarespace_scraper.py"

echo "$LOG_PREFIX Scrape complete."

# Tell Benedict what failed before any later step gets the chance to abort.
report_scrape_health

FAILED_COUNT=${#SCRAPER_FAILURES[@]}
if [ "$FAILED_COUNT" -gt "$MAX_SCRAPER_FAILURES" ]; then
    echo "$LOG_PREFIX ERROR: $FAILED_COUNT of $SCRAPER_COUNT scrapers failed (${SCRAPER_FAILURES[*]}), above the floor of $MAX_SCRAPER_FAILURES. Not publishing; keeping yesterday's site."
    exit 1
fi
if [ "$FAILED_COUNT" -gt 0 ]; then
    echo "$LOG_PREFIX $FAILED_COUNT of $SCRAPER_COUNT scrapers failed (${SCRAPER_FAILURES[*]}). Those nurseries keep their last-known-good data; continuing."
fi

# Update availability history
echo "$LOG_PREFIX Updating availability history..."
python3 "$SCRIPT_DIR/availability_tracker.py" "$PROJECT_DIR/data/nursery-stock" 2>&1 \
    || echo "$LOG_PREFIX WARNING: Availability history update failed (non-fatal; history page may be stale)"

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
# Guarded for the same reason as the scrapers: these were bare under `set -e`
# too, so a digest build failure would have taken every page builder below it
# and both subscriber sends with it.
python3 "$SCRIPT_DIR/daily_digest.py" "$PROJECT_DIR/data/nursery-stock" \
    --save "$DIGEST_DIR/digest.txt" 2>&1 || echo "$LOG_PREFIX WARNING: digest.txt build failed (non-fatal)"
python3 "$SCRIPT_DIR/daily_digest.py" "$PROJECT_DIR/data/nursery-stock" \
    --wa-only --save "$DIGEST_DIR/digest-wa.txt" 2>&1 || echo "$LOG_PREFIX WARNING: digest-wa.txt build failed (non-fatal)"

# Email HTML digest (unfiltered; send_digest.py handles per-subscriber state filtering)
python3 "$SCRIPT_DIR/daily_digest.py" "$PROJECT_DIR/data/nursery-stock" \
    --html --save "$DIGEST_DIR/digest-email.html" 2>&1 || echo "$LOG_PREFIX WARNING: digest-email.html build failed (non-fatal)"

# Shareable web page digests (main ones served at /digest.html)
python3 "$SCRIPT_DIR/daily_digest.py" "$PROJECT_DIR/data/nursery-stock" \
    --page --save "$DIGEST_DIR/digest.html" 2>&1 || echo "$LOG_PREFIX WARNING: digest.html build failed (non-fatal)"
python3 "$SCRIPT_DIR/daily_digest.py" "$PROJECT_DIR/data/nursery-stock" \
    --page --wa-only --save "$DIGEST_DIR/digest-wa.html" 2>&1 || echo "$LOG_PREFIX WARNING: digest-wa.html build failed (non-fatal)"

# Archive dated copies. Only archive what actually exists, so a failed digest
# build above does not abort the run here (and does not archive a stale page
# under today's date).
if [ -f "$DIGEST_DIR/digest.html" ]; then
    cp "$DIGEST_DIR/digest.html" "$ARCHIVE_DIR/digest-$TODAY.html"
fi
if [ -f "$DIGEST_DIR/digest-wa.html" ]; then
    cp "$DIGEST_DIR/digest-wa.html" "$ARCHIVE_DIR/digest-wa-$TODAY.html"
fi
echo "$LOG_PREFIX Digest complete (archived as $TODAY)."

# Build price/stock change history page
echo "$LOG_PREFIX Building history page..."
python3 "$SCRIPT_DIR/build_history.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: History page build failed (non-fatal)"
python3 "$SCRIPT_DIR/build_history.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" --wa-only 2>&1 || echo "$LOG_PREFIX WARNING: History page (WA) build failed (non-fatal)"
echo "$LOG_PREFIX History page complete."

# Build market trends page (30-day rolling availability + price trends per species).
# The builder is designed to run daily ("Run daily after scrapers"); without this it
# went stale between rare manual rebuilds. No email side effects, reads snapshots only.
echo "$LOG_PREFIX Building trends page..."
python3 "$SCRIPT_DIR/build_species_trends.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Trends page build failed (non-fatal)"
echo "$LOG_PREFIX Trends page complete."

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
# --ledger, and deliberately NOT --allow-delete. A compare page that drops
# below MIN_NURSERIES redirects to its species page, which always exists;
# nothing in this family is ever unlinked. See build_compare_pages.run_lifecycle.
python3 "$SCRIPT_DIR/build_compare_pages.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" \
    --ledger "$PROJECT_DIR/data/page-ledger/compare.json" --seed 2>&1 | tail -5 || echo "$LOG_PREFIX WARNING: Compare page build failed (non-fatal)"
echo "$LOG_PREFIX Compare pages complete."

# Build rare finds page
echo "$LOG_PREFIX Building rare finds page..."
python3 "$SCRIPT_DIR/build_rare_finds.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Rare finds page build failed (non-fatal)"
echo "$LOG_PREFIX Rare finds page complete."

# Build variety pages (cultivar-level SEO)
# --ledger is what turns a disappearing slug into a tombstone or a redirect stub
# instead of a 404; without it this builder is stateless and deletes nothing.
# --allow-delete permits the only two irreversible outcomes (a variety that has
# left the taxonomy, and a page that never met the 7-day entry guard), which is
# why an ad-hoc run must not pass it.
# --seed-reviewed adopts rows a human has approved in the recovery proposals,
# and is the ONLY thing that makes an approval reach the site. Rows without an
# explicit approved:true are ignored, so pointing at the file is not the same as
# publishing it, and a missing file is a warning rather than a failed build.
# --decisions is the same contract for the buttons on /admin/varieties/review:
# the UI queues an intent, this is where it becomes a page, and without this
# flag every click in that screen reaches nothing at all.
echo "$LOG_PREFIX Building variety pages..."
python3 "$SCRIPT_DIR/build_variety_pages.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" \
    --ledger "$PROJECT_DIR/data/page-ledger/variety.json" --allow-delete \
    --seed-reviewed "$PROJECT_DIR/data/variety-redirect-proposals.json" \
    --decisions "$PROJECT_DIR/data/variety-decisions.json" 2>&1 || echo "$LOG_PREFIX WARNING: Variety page build failed (non-fatal)"
echo "$LOG_PREFIX Variety pages complete."

# Build companion planting guide (SEO content)
echo "$LOG_PREFIX Building companion planting guide..."
python3 "$SCRIPT_DIR/build_companion_guide.py" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Companion guide build failed (non-fatal)"
echo "$LOG_PREFIX Companion guide complete."

# Build fruit-tree pollination guide (SEO content)
echo "$LOG_PREFIX Building pollination guide..."
python3 "$SCRIPT_DIR/build_pollination_guide.py" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Pollination guide build failed (non-fatal)"
echo "$LOG_PREFIX Pollination guide complete."

# Build "when to plant" seasonal planting calendar (SEO content)
echo "$LOG_PREFIX Building when-to-plant calendar..."
python3 "$SCRIPT_DIR/build_when_to_plant.py" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: When-to-plant build failed (non-fatal)"
echo "$LOG_PREFIX When-to-plant calendar complete."

# Build bare-root season page (seasonal SEO content, season-aware)
echo "$LOG_PREFIX Building bare-root season page..."
python3 "$SCRIPT_DIR/build_bare_root_page.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Bare-root page build failed (non-fatal)"
echo "$LOG_PREFIX Bare-root season page complete."

# Build the shipping-reachability dataset page (DAL-254). This is the one page
# on the site built to be CITED rather than to convert: it publishes what every
# tracked nursery x every day since March says about which species each state
# can actually buy. It also writes /shipping-reachability.json, which is the
# half a machine links to.
echo "$LOG_PREFIX Building shipping reachability dataset..."
python3 "$SCRIPT_DIR/build_shipping_reachability.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Shipping reachability build failed (non-fatal)"
echo "$LOG_PREFIX Shipping reachability dataset complete."

# Build rootstock and grafting guide (SEO content, curated per-species JSON layer)
echo "$LOG_PREFIX Building rootstock guide..."
python3 "$SCRIPT_DIR/build_rootstock_page.py" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Rootstock guide build failed (non-fatal)"
echo "$LOG_PREFIX Rootstock guide complete."

# Build sample digest preview page (subscriber conversion)
echo "$LOG_PREFIX Building sample digest page..."
python3 "$SCRIPT_DIR/build_sample_digest.py" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Sample digest page build failed (non-fatal)"
echo "$LOG_PREFIX Sample digest page complete."

# Build Treesmith app landing page (cross-promotion)
echo "$LOG_PREFIX Building Treesmith landing page..."
python3 "$SCRIPT_DIR/build_treesmith_page.py" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Treesmith landing page build failed (non-fatal)"
echo "$LOG_PREFIX Treesmith landing page complete."

# Build location pages (WA/QLD/NSW/VIC, fruit-species-filtered)
echo "$LOG_PREFIX Building location pages..."
python3 "$SCRIPT_DIR/build_location_pages.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Location page build failed (non-fatal)"
echo "$LOG_PREFIX Location pages complete."

# Build species+state combo pages (buy-[species]-trees-[state].html)
# The ledger is what stops a combo freezing: below RETAIN_MIN_PRODUCTS it
# tombstones instead of serving last season's in-stock table forever. The
# trailing JSON page list this pipes to `tail -3` is still the last stdout line;
# everything the lifecycle prints goes to stderr.
echo "$LOG_PREFIX Building species+state combo pages..."
python3 "$SCRIPT_DIR/build_species_state_pages.py" "$PROJECT_DIR/data/nursery-stock" "$DIGEST_DIR" \
    --ledger "$PROJECT_DIR/data/page-ledger/species-state.json" --allow-delete 2>&1 | tail -3 || echo "$LOG_PREFIX WARNING: Species+state page build failed (non-fatal)"
echo "$LOG_PREFIX Species+state combo pages complete."

# Build sitemap. MUST come after every page builder: it globs the output dir and
# reads each page's declared lifecycle state, so running it earlier described
# last night's combo files. That was harmless while page states did not exist
# and wrong the moment they did.
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

# Check nobody has silently fallen out of the send loop (DAL-262). Runs AFTER
# both senders on purpose: it reads their send logs, so running it earlier would
# always judge them one night stale.
echo "$LOG_PREFIX Checking subscriber delivery..."
python3 "$SCRIPT_DIR/detect_silent_subscribers.py" 2>&1 || echo "$LOG_PREFIX WARNING: Subscriber delivery check failed (non-fatal)"
echo "$LOG_PREFIX Subscriber delivery check complete."

# Send per-variety restock alerts to watchers
# (Species-level alerts deprecated 2026-04-19: trigger condition was too strict
# to ever fire in practice, and only variety watches are meaningful.)
echo "$LOG_PREFIX Sending variety restock alerts..."
python3 "$SCRIPT_DIR/send_variety_alerts.py" "$PROJECT_DIR/data/nursery-stock" 2>&1 || echo "$LOG_PREFIX WARNING: Variety alerts failed (non-fatal)"
echo "$LOG_PREFIX Variety alert send complete."

# Build 404 page (served by Caddy handle_errors)
echo "$LOG_PREFIX Building 404 page..."
python3 "$SCRIPT_DIR/build_404_page.py" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: 404 page build failed (non-fatal)"
echo "$LOG_PREFIX 404 page complete."

# Affiliate disclosure. Generated from stocklib.utm.AFFILIATES, so it stays in
# step with which nurseries actually pay us. Every page footer links to it.
echo "$LOG_PREFIX Building affiliate disclosure page..."
python3 "$SCRIPT_DIR/build_affiliate_disclosure.py" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: affiliate disclosure build failed (non-fatal)"
echo "$LOG_PREFIX Affiliate disclosure complete."

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
# failure streaks) already ran, right after the scrapers, and the EXIT trap
# would have run it even if a step above aborted. It used to live here, which
# is precisely why two dead scrape nights went unreported: everything that can
# report a failure must sit upstream of the things that can fail.
echo "$LOG_PREFIX Scrape health check complete (reported above)."
