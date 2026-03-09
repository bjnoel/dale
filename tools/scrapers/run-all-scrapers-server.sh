#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="/opt/dale"
export DALE_DATA_DIR="$PROJECT_DIR/data"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

echo "$LOG_PREFIX Starting nursery stock scrape..."

# Shopify nurseries (Ross Creek, Ladybird, Fruitopia, Fruit Salad Trees, Diggers)
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

echo "$LOG_PREFIX Scrape complete."

# Update availability history
echo "$LOG_PREFIX Updating availability history..."
python3 "$SCRIPT_DIR/availability_tracker.py" "$PROJECT_DIR/data/nursery-stock" 2>&1

# Quick summary
echo "$LOG_PREFIX Stock summary:"
python3 "$SCRIPT_DIR/stock_summary.py" "$PROJECT_DIR/data/nursery-stock" 2>&1

# Build dashboard
echo "$LOG_PREFIX Building dashboard..."
python3 "$SCRIPT_DIR/build-dashboard.py" "$PROJECT_DIR/data/nursery-stock" /opt/dale/dashboard 2>&1
echo "$LOG_PREFIX Dashboard build complete."
