#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Automated Postgres backup with local retention.
#
# Usage:
#   ./scripts/backup-postgres.sh            # Manual run
#   crontab: 0 3 * * * /path/to/scripts/backup-postgres.sh >> /var/log/sku-ops-backup.log 2>&1
#
# Requires: docker compose, gzip.
# Reads BACKUP_RETENTION_DAYS from .env (default: 7).
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Load .env for BACKUP_RETENTION_DAYS
if [ -f .env ]; then
  set -a; source .env; set +a
fi

BACKUP_DIR="${PROJECT_DIR}/backups"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/sku_ops-${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date -Iseconds)] Starting Postgres backup..."

docker compose exec -T db pg_dump \
  -U sku_ops \
  -d sku_ops \
  --no-owner \
  --no-privileges \
  --format=plain \
  | gzip > "$BACKUP_FILE"

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "[$(date -Iseconds)] Backup complete: $BACKUP_FILE ($SIZE)"

# Prune old backups
PRUNED=0
while IFS= read -r old_file; do
  rm -f "$old_file"
  PRUNED=$((PRUNED + 1))
done < <(find "$BACKUP_DIR" -name "sku_ops-*.sql.gz" -mtime "+${RETENTION_DAYS}" -type f 2>/dev/null)

if [ "$PRUNED" -gt 0 ]; then
  echo "[$(date -Iseconds)] Pruned $PRUNED backup(s) older than $RETENTION_DAYS days"
fi

TOTAL=$(find "$BACKUP_DIR" -name "sku_ops-*.sql.gz" -type f | wc -l | tr -d ' ')
echo "[$(date -Iseconds)] Total backups retained: $TOTAL"
