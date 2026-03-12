#!/usr/bin/env bash
# Enable automatic backups on the Dale server (ID: 122794972)
# Cost: ~€0.76/month for daily rolling 7-day backups
#
# Requires: HETZNER_TOKEN in /opt/dale/secrets/hetzner.env
# Run once: bash enable-hetzner-backups.sh

set -euo pipefail

if [ -f /opt/dale/secrets/hetzner.env ]; then
    source /opt/dale/secrets/hetzner.env
fi

if [ -z "${HETZNER_TOKEN:-}" ]; then
    echo "ERROR: HETZNER_TOKEN not set. Add it to /opt/dale/secrets/hetzner.env"
    exit 1
fi

SERVER_ID=122794972

echo "Enabling automatic backups on server $SERVER_ID..."
curl -s -X POST \
    -H "Authorization: Bearer $HETZNER_TOKEN" \
    -H "Content-Type: application/json" \
    "https://api.hetzner.cloud/v1/servers/$SERVER_ID/actions/enable_backup" | python3 -m json.tool

echo "Done. Backups will be taken daily, retained for 7 days."
