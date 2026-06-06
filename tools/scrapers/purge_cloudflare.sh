#!/usr/bin/env bash
# Purge the Cloudflare edge cache for treestock after a full site regen.
#
# We cache HTML at the edge for 1 day via a Cache Rule, so the nightly rebuild
# MUST purge or the edge keeps serving yesterday's pages until the TTL expires.
# Static assets (css/js/images) are version-busted, so purge_everything is safe
# and simplest: the next request re-warms each page from the freshly built origin.
#
# Reads secrets from /opt/dale/secrets/cloudflare.env (override with CLOUDFLARE_ENV):
#   CLOUDFLARE_API_TOKEN          token with Zone.Cache Purge
#   CLOUDFLARE_ZONE_ID_TREESTOCK  the treestock zone id (falls back to CLOUDFLARE_ZONE_ID)
#
# Non-fatal by design: a missing secret or an API error logs a warning and exits
# 0, so a purge hiccup never breaks the build pipeline. The secret value is never
# printed (token is sent only in the Authorization header).
#
# Usage: purge_cloudflare.sh [zone_id]   # defaults to the treestock zone
set -uo pipefail

SECRET="${CLOUDFLARE_ENV:-/opt/dale/secrets/cloudflare.env}"
if [ ! -f "$SECRET" ]; then
    echo "purge_cloudflare: $SECRET not found; skipping cache purge" >&2
    exit 0
fi
set -a; . "$SECRET"; set +a

ZONE="${1:-${CLOUDFLARE_ZONE_ID_TREESTOCK:-${CLOUDFLARE_ZONE_ID:-}}}"
TOKEN="${CLOUDFLARE_API_TOKEN:-}"
if [ -z "$TOKEN" ] || [ -z "$ZONE" ]; then
    echo "purge_cloudflare: CLOUDFLARE_API_TOKEN or zone id missing in $SECRET; skipping" >&2
    exit 0
fi

resp=$(curl -sS -X POST \
    "https://api.cloudflare.com/client/v4/zones/${ZONE}/purge_cache" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    --data '{"purge_everything":true}' --max-time 30 2>&1)

if printf '%s' "$resp" | grep -qE '"success"[[:space:]]*:[[:space:]]*true'; then
    echo "purge_cloudflare: treestock edge cache purged"
else
    echo "purge_cloudflare: purge FAILED: $resp" >&2
fi
exit 0
