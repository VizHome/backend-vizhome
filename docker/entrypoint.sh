#!/bin/sh
set -e

# Toujours attendre Postgres avant de démarrer
echo "→ Waiting for postgres..."
until pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" >/dev/null 2>&1; do
  sleep 1
done
echo "✓ Postgres is up"

# Migrations uniquement si demandé (l'API les lance, pas le worker Celery)
if [ "$RUN_MIGRATIONS" = "1" ]; then
  echo "→ Running migrations..."
  python manage.py migrate --noinput
fi

exec "$@"
