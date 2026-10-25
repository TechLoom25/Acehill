#!/usr/bin/env bash
# Nightly PostgreSQL backup, keeping 14 days.   Install: see DEPLOY.md
set -euo pipefail
DEST=/var/backups/acehill
mkdir -p "$DEST"
sudo -u postgres pg_dump acehill | gzip > "$DEST/acehill-$(date +%F).sql.gz"
find "$DEST" -name 'acehill-*.sql.gz' -mtime +14 -delete
