#!/bin/bash
# Generate an audit report from a JSON data file
# Usage: ./generate-report.sh data/clients/example.json

set -euo pipefail

if [ $# -eq 0 ]; then
  echo "Usage: $0 <client-data.json>"
  echo "Creates an HTML report from client assessment data."
  exit 1
fi

DATA_FILE="$1"
TEMPLATE_DIR="$(cd "$(dirname "$0")/../templates" && pwd)"
TEMPLATE="$TEMPLATE_DIR/audit-report.html"
OUTPUT_DIR="$(cd "$(dirname "$0")/../../deliverables" && pwd)"

if [ ! -f "$DATA_FILE" ]; then
  echo "Error: Data file not found: $DATA_FILE"
  exit 1
fi

# Extract business name for the output filename
BIZ_NAME=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['business_name'])" "$DATA_FILE")
SAFE_NAME=$(echo "$BIZ_NAME" | tr ' ' '-' | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9-')
DATE=$(date +%Y-%m-%d)
OUTPUT_FILE="$OUTPUT_DIR/${SAFE_NAME}-assessment-${DATE}.html"

mkdir -p "$OUTPUT_DIR"

# Replace all {{PLACEHOLDER}} tokens with values from JSON
python3 - "$DATA_FILE" "$TEMPLATE" "$OUTPUT_FILE" << 'PYEOF'
import json, sys, re

data_file = sys.argv[1]
template_file = sys.argv[2]
output_file = sys.argv[3]

with open(data_file) as f:
    data = json.load(f)

with open(template_file) as f:
    html = f.read()

# Flatten nested data into PLACEHOLDER: value mapping
placeholders = {}
for key, value in data.items():
    if isinstance(value, str):
        placeholders[key.upper()] = value
    elif isinstance(value, dict):
        for k2, v2 in value.items():
            placeholders[f"{key.upper()}_{k2.upper()}"] = str(v2)
    elif isinstance(value, list):
        for i, item in enumerate(value, 1):
            if isinstance(item, dict):
                for k2, v2 in item.items():
                    placeholders[f"F{i}_{k2.upper()}"] = str(v2)

# Replace tokens
for placeholder, value in placeholders.items():
    html = html.replace(f"{{{{{placeholder}}}}}", value)

# Remove any unfilled optional findings (F4, F5 etc)
# If a finding still has {{F*_ placeholders, remove the whole finding div
html = re.sub(
    r'<!-- FINDING \d+ \(optional\) -->\s*<div class="finding">.*?</div>\s*</div>',
    '',
    html,
    flags=re.DOTALL
)

with open(output_file, 'w') as f:
    f.write(html)

print(f"Report generated: {output_file}")
PYEOF
