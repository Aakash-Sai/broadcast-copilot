#!/usr/bin/env bash
set -euo pipefail
cd /opt/broadcast
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
file="editorial-${stamp}.sqlite3"
install -d -m 0700 /opt/broadcast/backups
docker compose -p broadcast -f compose.azure.yaml exec -T broadcast \
  python -m scripts.backup_editorial "/var/lib/broadcast/backups/$file"
docker compose -p broadcast -f compose.azure.yaml cp \
  "broadcast:/var/lib/broadcast/backups/$file" "/opt/broadcast/backups/$file"
chmod 0600 "/opt/broadcast/backups/$file"
echo 'Daily SQLite backup completed. Copy backups off this VM separately.'
