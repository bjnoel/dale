#!/bin/bash
# Email-safe rebuild: regenerate the product-listing pages AND the curated guide/
# static pages so content and shared-chrome changes (e.g. the nav) appear on the
# site, WITHOUT touching anything that emails subscribers or shows the additions
# as false "new listings". Originally the DEC-209 listing rebuild; extended to the
# guides so a site-wide chrome change lands everywhere it can email-safely.
#
# RUN ONLY AFTER the baseline scrapes for the three fixed nurseries have written
# today's snapshots. Sends no emails.
#
# SKIPPED on purpose: availability_tracker, daily_digest (all variants),
# build_history, detect_stock_surges, send_digest, send_weekly_digest,
# send_variety_alerts.
set -uo pipefail
SCRIPT_DIR=/opt/dale/scrapers
PROJECT_DIR=/opt/dale
export DALE_DATA_DIR="$PROJECT_DIR/data"
DATA="$PROJECT_DIR/data/nursery-stock"
DIGEST_DIR="$PROJECT_DIR/dashboard"
cd "$SCRIPT_DIR"

run() { echo ">>> $*"; "$@" 2>&1 | tail -3; echo; }

run python3 build-dashboard.py "$DATA" "$DIGEST_DIR" --needs-review-out "$PROJECT_DIR/data/needs-review.json"
mkdir -p "$DIGEST_DIR/bush-tucker"
run python3 build-dashboard.py "$DATA" "$DIGEST_DIR/bush-tucker" --category bush_tucker
run python3 build_nursery_pages.py "$DATA" "$DIGEST_DIR"
run python3 build_nursery_compare.py "$DATA" "$DIGEST_DIR"
run python3 build_species_pages.py "$DATA" "$DIGEST_DIR"        # species BEFORE variety
run python3 build_compare_pages.py "$DATA" "$DIGEST_DIR"
run python3 build_rare_finds.py "$DATA" "$DIGEST_DIR"
run python3 build_variety_pages.py "$DATA" "$DIGEST_DIR"        # variety AFTER species
run python3 build_location_pages.py "$DATA" "$DIGEST_DIR"
run python3 build_species_state_pages.py "$DATA" "$DIGEST_DIR"

# Curated guide + static pages. No email side effects, so they are email-safe to
# rebuild here. Needed whenever the shared chrome changes (e.g. the nav), so the
# guides reachable from the Guides menu do not lag behind the listing pages.
run python3 build_companion_guide.py "$DIGEST_DIR"
run python3 build_pollination_guide.py "$DIGEST_DIR"
run python3 build_when_to_plant.py "$DIGEST_DIR"
run python3 build_bare_root_page.py "$DATA" "$DIGEST_DIR"
run python3 build_treesmith_page.py "$DIGEST_DIR"
run python3 build_404_page.py "$DIGEST_DIR"
run python3 build_llms.py "$DIGEST_DIR"

run python3 build_sitemap.py "$DIGEST_DIR/species" "$DIGEST_DIR"

echo ">>> tailwind"
tailwindcss --input "$SCRIPT_DIR/tailwind-input.css" --output "$DIGEST_DIR/styles.css" \
    --content "$DIGEST_DIR/**/*.html" --minify 2>&1 | tail -2
echo

echo ">>> purge cloudflare"
bash "$SCRIPT_DIR/purge_cloudflare.sh" 2>&1 | tail -3
echo "REBUILD DONE"
