#!/bin/sh
set -e

# Attend que Postgres soit dispo
echo "→ Waiting for postgres..."
until pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" >/dev/null 2>&1; do
  sleep 1
done
echo "✓ Postgres is up"

# Applique les migrations au démarrage en dev
if [ "$DJANGO_DEBUG" = "True" ]; then
  echo "→ Running migrations..."
  python manage.py migrate --noinput
fi

exec "$@"
