#!/bin/sh
# Backup Postgres → fichier compressé daté dans ./backups/
# À planifier via cron sur le serveur prod, ex :
#   0 3 * * * cd /opt/vizhome && ./scripts/backup_postgres.sh
#
# Restauration :
#   gunzip -c backup-20260601-030000.sql.gz | docker compose exec -T postgres \
#     psql -U $POSTGRES_USER -d $POSTGRES_DB

set -e

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
FILE="$BACKUP_DIR/backup-$TIMESTAMP.sql.gz"

echo "→ Dump Postgres → $FILE"
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$FILE"

echo "✓ Backup créé : $(du -h "$FILE" | cut -f1)"

# Nettoie les vieux backups
echo "→ Suppression des backups > $RETENTION_DAYS jours"
find "$BACKUP_DIR" -name 'backup-*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

echo "✓ Backup terminé"
