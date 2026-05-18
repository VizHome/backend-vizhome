#!/bin/sh
# Backup MinIO via mc mirror → dossier local horodaté
# Cette approche fait un snapshot complet ; pour de gros volumes, préférer
# une réplication MinIO native (mc replicate) vers un autre bucket.

set -e

BACKUP_DIR="${BACKUP_DIR:-./backups/minio}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
DEST="$BACKUP_DIR/$TIMESTAMP"
mkdir -p "$DEST"

echo "→ Mirror MinIO → $DEST"
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm minio-init \
  /bin/sh -c "mc mirror --overwrite local/$MINIO_S3_BUCKET_NAME /backup" \
  -v "$DEST:/backup"

echo "✓ Mirror terminé : $(du -sh "$DEST" | cut -f1)"

# Nettoie les vieux snapshots
find "$BACKUP_DIR" -maxdepth 1 -type d -name '20*' -mtime +"$RETENTION_DAYS" -exec rm -rf {} +

echo "✓ Backup MinIO terminé"
