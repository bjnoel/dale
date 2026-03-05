#!/bin/bash
# Run all nursery stock scrapers
# Intended to be run daily via cron or launchd
#
# Usage: ./run-all-scrapers.sh
# Cron:  0 6 * * * /Users/bjnoel/Projects/Dale/tools/scrapers/run-all-scrapers.sh >> /Users/bjnoel/Projects/Dale/data/scraper.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

echo "$LOG_PREFIX Starting nursery stock scrape..."

# Shopify nurseries (Ross Creek, Ladybird, Fruitopia)
echo "$LOG_PREFIX Scraping Shopify nurseries..."
python3 "$SCRIPT_DIR/shopify_scraper.py" 2>&1

# Daleys (custom scraper)
if [ -f "$SCRIPT_DIR/daleys_scraper.py" ]; then
    echo "$LOG_PREFIX Scraping Daleys..."
    python3 "$SCRIPT_DIR/daleys_scraper.py" 2>&1
else
    echo "$LOG_PREFIX Daleys scraper not yet built, skipping"
fi

echo "$LOG_PREFIX Scrape complete."

# Quick summary
echo "$LOG_PREFIX Stock summary:"
for f in "$PROJECT_DIR"/data/nursery-stock/*/latest.json; do
    if [ -f "$f" ]; then
        nursery=$(python3 -c "import json; print(json.load(open('$f'))['nursery_name'])")
        count=$(python3 -c "import json; d=json.load(open('$f')); print(f\"{d['in_stock_count']}/{d['product_count']} in stock\")")
        echo "$LOG_PREFIX   $nursery: $count"
    fi
done
