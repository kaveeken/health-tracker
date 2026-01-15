#!/bin/bash
# Simple database backup script
# Run manually or via cron: 0 2 * * * /home/pi/proj/health-tracker/backup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB="$SCRIPT_DIR/health_tracker.db"
BACKUP_DIR="$SCRIPT_DIR/backups"

mkdir -p "$BACKUP_DIR"

cp "$DB" "$BACKUP_DIR/health_tracker_$(date +%Y%m%d_%H%M%S).db"

# Delete backups older than 30 days
find "$BACKUP_DIR" -name "health_tracker_*.db" -mtime +30 -delete

echo "Backup complete: $BACKUP_DIR"
