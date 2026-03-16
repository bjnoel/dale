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

# Build dashboard
echo "$LOG_PREFIX Building dashboard..."
python3 "$SCRIPT_DIR/build-dashboard.py" "$PROJECT_DIR/data/nursery-stock" "$PROJECT_DIR/dashboard" 2>&1
echo "$LOG_PREFIX Dashboard build complete."

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

# Email HTML digests
python3 "$SCRIPT_DIR/daily_digest.py" "$PROJECT_DIR/data/nursery-stock" \
    --html --save "$DIGEST_DIR/digest-email.html" 2>&1
python3 "$SCRIPT_DIR/daily_digest.py" "$PROJECT_DIR/data/nursery-stock" \
    --html --wa-only --save "$DIGEST_DIR/digest-wa-email.html" 2>&1

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

# Build sample digest preview page (subscriber conversion)
echo "$LOG_PREFIX Building sample digest page..."
python3 "$SCRIPT_DIR/build_sample_digest.py" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Sample digest page build failed (non-fatal)"
echo "$LOG_PREFIX Sample digest page complete."

# Build sitemap
echo "$LOG_PREFIX Building sitemap..."
python3 "$SCRIPT_DIR/build_sitemap.py" "$DIGEST_DIR/species" "$DIGEST_DIR" 2>&1 || echo "$LOG_PREFIX WARNING: Sitemap build failed (non-fatal)"
echo "$LOG_PREFIX Sitemap complete."

# Send digest to email subscribers
echo "$LOG_PREFIX Sending digest to email subscribers..."
python3 "$SCRIPT_DIR/send_digest.py" 2>&1 || echo "$LOG_PREFIX WARNING: Digest email send failed (non-fatal)"
echo "$LOG_PREFIX Subscriber send complete."

# Send species restock alerts to watchers
echo "$LOG_PREFIX Sending species restock alerts..."
python3 "$SCRIPT_DIR/send_species_alerts.py" "$PROJECT_DIR/data/nursery-stock" 2>&1 || echo "$LOG_PREFIX WARNING: Species alert send failed (non-fatal)"
echo "$LOG_PREFIX Species alert send complete."
