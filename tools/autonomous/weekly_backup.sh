#!/bin/bash
# Weekly backup of /opt/dale/data/ to /opt/dale/backups/
# Keeps last 4 weekly backups, deletes older ones.
# Run via cron: 0 2 * * 0 /opt/dale/autonomous/weekly_backup.sh
#
# Built 2026-03-14 (DEC-045) and deployed straight to the box, where it then
# lived untracked for five months: deploy.sh rsyncs autonomous/ WITHOUT
# --delete, so a server-only file survives there indefinitely and invisibly.
# Recovered into the repo by DAL-281, unchanged.
#
# Known limitation, deliberately not fixed here: the archive lands on the same
# disk as the data it is backing up, so it protects against accidental deletion
# and not against losing the volume. Hetzner's daily snapshots cover that case.

BACKUP_DIR="/opt/dale/backups"
DATA_DIR="/opt/dale/data"
TIMESTAMP=$(date +%Y-W%V)
ARCHIVE="$BACKUP_DIR/data-$TIMESTAMP.tar.gz"

mkdir -p "$BACKUP_DIR"

# Create the backup
tar -czf "$ARCHIVE" -C /opt/dale data/ 2>&1
if [ $? -eq 0 ]; then
    SIZE=$(du -sh "$ARCHIVE" | cut -f1)
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Backup created: $ARCHIVE ($SIZE)"
else
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR: Backup failed for $ARCHIVE"
    exit 1
fi

# Keep only last 4 backups (delete oldest if more than 4 exist)
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/data-*.tar.gz 2>/dev/null | wc -l)
if [ "$BACKUP_COUNT" -gt 4 ]; then
    EXCESS=$((BACKUP_COUNT - 4))
    ls -1t "$BACKUP_DIR"/data-*.tar.gz | tail -$EXCESS | xargs rm -f
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Pruned $EXCESS old backup(s), keeping 4"
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Backups in $BACKUP_DIR:"
ls -lh "$BACKUP_DIR"/data-*.tar.gz 2>/dev/null || echo "  (none)"
