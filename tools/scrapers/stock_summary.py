#!/usr/bin/env python3
"""Print a quick summary of nursery stock data."""
import json
import sys
from pathlib import Path

data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/opt/dale/data/nursery-stock")

for f in sorted(data_dir.glob("*/latest.json")):
    d = json.load(open(f))
    print(f"  {d['nursery_name']}: {d['in_stock_count']}/{d['product_count']} in stock")
