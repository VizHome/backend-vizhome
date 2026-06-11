#!/bin/sh
set -e

# =============================================================================
# entrypoint.sh — Zéro commande manuelle au deploy.
#
# Étapes :
#   1. Attendre Postgres (retry jusqu'à 60s)
#   2. Attendre Redis (retry jusqu'à 60s) si REDIS_URL défini
#   3. Lancer `python manage.py bootstrap` (sauf si BOOTSTRAP_SKIP=1) qui :
#        - migrate
#        - collectstatic (si STATIC_ROOT)
#        - compilemessages
#        - seed_forum_categories
#        - setup_stripe_products (si Stripe configuré)
#        - setup_webhook_endpoint (idem)
#      Avec lock Redis pour rester safe en multi-replica.
#   4. exec "$@" (gunicorn par défaut, override pour celery worker/beat)
#
# Variables d'env reconnues :
#   POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER : pour pg_isready
#   REDIS_URL                                    : pour test connect Redis
#   BOOTSTRAP_SKIP=1                             : skip totalement (workers Celery)
#   BOOTSTRAP_STRIPE_SKIP=1                      : skip uniquement les commandes Stripe
#   BOOTSTRAP_WAIT_LOCK_SECONDS=60               : timeout d'attente du lock
# =============================================================================

# Couleurs minimales pour logs lisibles
GREEN=$(printf '\033[0;32m')
YELLOW=$(printf '\033[1;33m')
RED=$(printf '\033[0;31m')
NC=$(printf '\033[0m')

log() { echo "${GREEN}[entrypoint]${NC} $1"; }
warn() { echo "${YELLOW}[entrypoint]${NC} $1" >&2; }
err() { echo "${RED}[entrypoint]${NC} $1" >&2; }

# ─── 1. Attendre Postgres ────────────────────────────────────────────────────
log "Waiting for Postgres ($POSTGRES_HOST:$POSTGRES_PORT)..."
i=0
until pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" >/dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 60 ]; then
        err "Postgres still down after 60s — aborting"
        exit 1
    fi
    sleep 1
done
log "✓ Postgres is up"

# ─── 2. Attendre Redis ───────────────────────────────────────────────────────
if [ -n "$REDIS_URL" ]; then
    # Parsing robuste de l'URL via urllib (gère redis://[:pwd@]host:port[/db],
    # rediss://, IPv6, port absent). Le sed maison cassait sur l'absence de
    # mot de passe : le groupe optionnel mangeait le hostname et REDIS_HOST
    # devenait le port (d'où "Waiting for Redis (6379:6379)").
    REDIS_HOST=$(python -c "import os,urllib.parse as u; p=u.urlparse(os.environ['REDIS_URL']); print(p.hostname or 'redis')")
    REDIS_PORT=$(python -c "import os,urllib.parse as u; p=u.urlparse(os.environ['REDIS_URL']); print(p.port or 6379)")

    log "Waiting for Redis ($REDIS_HOST:$REDIS_PORT)..."
    i=0
    # Pas de redis-cli dans l'image runtime → test TCP via python
    until python -c "import socket; s = socket.socket(); s.settimeout(1); s.connect(('$REDIS_HOST', $REDIS_PORT)); s.close()" >/dev/null 2>&1; do
        i=$((i + 1))
        if [ "$i" -ge 60 ]; then
            err "Redis still down after 60s — aborting"
            exit 1
        fi
        sleep 1
    done
    log "✓ Redis is up"
fi

# ─── 3. Bootstrap idempotent ─────────────────────────────────────────────────
if [ "$BOOTSTRAP_SKIP" = "1" ]; then
    log "BOOTSTRAP_SKIP=1 → skip bootstrap (workers Celery typiquement)"
else
    log "Running bootstrap..."
    BOOTSTRAP_ARGS=""
    if [ "$BOOTSTRAP_STRIPE_SKIP" = "1" ]; then
        BOOTSTRAP_ARGS="$BOOTSTRAP_ARGS --skip-stripe"
    fi
    if [ -n "$BOOTSTRAP_WAIT_LOCK_SECONDS" ]; then
        BOOTSTRAP_ARGS="$BOOTSTRAP_ARGS --wait-for-lock $BOOTSTRAP_WAIT_LOCK_SECONDS"
    fi
    # shellcheck disable=SC2086
    python manage.py bootstrap $BOOTSTRAP_ARGS
fi

# ─── 4. Exec command (gunicorn par défaut) ───────────────────────────────────
log "Starting: $*"
exec "$@"
