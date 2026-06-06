# Déploiement — backend-vizhome

Guide de mise en production du backend Django.

## Stack de production

`docker-compose.prod.yml` orchestre 7 services backend, plus le service Nuxt
du repo `frontend-vizhome` qui rejoint le même network Traefik.

| Service | Rôle | Exposé Traefik ? |
|---|---|---|
| `traefik` | Reverse proxy + TLS auto Let's Encrypt + HTTP/3 | — |
| `postgres` | DB principale, volume persistant | non |
| `redis` | Broker Celery + cache + lock bootstrap, persistance | non |
| `minio` | Storage S3-compatible | `cdn.vizhome.fr` + `minio.vizhome.fr` |
| `minio-init` | Job one-shot : crée le bucket + policy publique | — |
| `api` | Django via Gunicorn (4 workers) | `api.vizhome.fr` |
| `celery` | Worker async (rendus IA, emails) | non |
| `celery-beat` | Cron jobs (reset compteurs, snapshots admin) | non |
| `frontend` (autre repo) | Nuxt 4 SSR | `vizhome.fr`, `www.vizhome.fr` |

### Architecture réseau

```
              Internet (HTTPS + HTTP/3)
                       │
                       ▼
              ┌──────────────────┐
              │     Traefik      │  TLS, security headers,
              │   (vizhome_proxy)│  compress, rate-limit, métriques
              └────────┬─────────┘
                       │
       ┌──────────┬────┴─────┬──────────┐
       ▼          ▼          ▼          ▼
   frontend     api       minio    minio-console
   (Nuxt)    (Django)   (S3 API)   (admin UI)
       │          │          │
       │          ▼          │
       │     ┌────────────┐  │      vizhome_internal
       │     │ postgres   │  │      (pas exposé)
       │     │ redis      │  │
       │     │ celery*    │  │
       │     └────────────┘  │
       │                     │
       └──────► /api/* proxy backend Nitro (côté Nuxt)
```

Deux networks Docker :
- `vizhome_proxy` (external) : Traefik + services exposés
- `vizhome_internal` (bridge) : DB, cache, workers, pas de routage externe

### Configuration Traefik

La config statique est dans `traefik/traefik.yml` (entrypoints, ACME,
métriques Prometheus). Les middlewares réutilisables, les options TLS et
le router du dashboard sont dans `traefik/dynamic/*.yml` — **hot-reloadés**
sans restart quand tu édites ces fichiers.

| Middleware | Effet |
|---|---|
| `security-headers` | HSTS preload, CSP de base, X-Frame-Options, Permissions-Policy, COOP/CORP |
| `compress` | Brotli + gzip selon Accept-Encoding (skip images/vidéos) |
| `rate-limit-global` | 100 req/s en moyenne, burst 200, par IP source |
| `rate-limit-strict` | 5 req/min sur endpoints sensibles (login, register, contact) |
| `redirect-www-to-apex` | Force vizhome.fr (sans www) comme canonical |
| `dashboard-auth` | Basic Auth pour `traefik.vizhome.fr` |
| `api-cors` | CORS pour appels mobiles directs à l'API (futur) |

## Prérequis serveur

- **Linux** (Debian / Ubuntu / Rocky) avec **Docker Engine** + **Compose v2**
- **2 vCPU, 4 Go RAM** minimum (8 Go recommandé pour Three.js)
- **40 Go disque** (système + DB + MinIO + logs)
- **Ports 80/443 TCP + 443/UDP** (HTTP/3) ouverts
- **Domaines DNS** A records pointant vers le serveur :
  - `vizhome.fr` + `www.vizhome.fr` (frontend)
  - `api.vizhome.fr` (backend)
  - `cdn.vizhome.fr` (assets MinIO publics)
  - `minio.vizhome.fr` (console MinIO admin)
  - `traefik.vizhome.fr` (dashboard Traefik)

## Premier déploiement

### 1. Préparer le serveur + clone des repos

```bash
ssh root@vizhome.fr
cd /opt

# Clone les deux repos
git clone https://github.com/VizHome/backend-vizhome.git
git clone https://github.com/VizHome/frontend-vizhome.git
cd backend-vizhome

# Crée le network partagé Traefik (une seule fois)
docker network create vizhome_proxy
```

### 2. Configurer l'environnement

```bash
cp .env.example .env.prod
nano .env.prod
```

Champs **obligatoires** à remplir :

| Variable | Comment |
|---|---|
| `DJANGO_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `POSTGRES_PASSWORD` | Mot de passe Postgres fort |
| `MINIO_S3_ACCESS_KEY` + `MINIO_S3_SECRET_KEY` | Identifiants MinIO (forts) |
| `ACME_EMAIL` | Email pour notifications Let's Encrypt |
| `API_HOST` | `api.vizhome.fr` |
| `FRONTEND_HOST` | `vizhome.fr` |
| `MINIO_PUBLIC_HOST` | `cdn.vizhome.fr` |
| `MINIO_CONSOLE_HOST` | `minio.vizhome.fr` |
| `TRAEFIK_DASHBOARD_HOST` | `traefik.vizhome.fr` |
| `TRAEFIK_DASHBOARD_AUTH` | `htpasswd -nbB admin "MOT_DE_PASSE_FORT"` |

**Services tiers** (au choix d'activer) :

| Variable | Source |
|---|---|
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| `STRIPE_LIVE_SECRET_KEY` + `STRIPE_LIVE_PUBLISHABLE_KEY` | dashboard.stripe.com |
| `STRIPE_WEBHOOK_SECRET` | Stripe dashboard → Webhooks → Add endpoint |
| `GOOGLE_OAUTH_CLIENT_ID` | Google Cloud Console → Credentials |
| `GITHUB_OAUTH_CLIENT_ID` + `_SECRET` | github.com → Settings → Developers |
| `SENTRY_DSN` | sentry.io (optionnel) |
| `EMAIL_HOST` + `EMAIL_HOST_USER` + `EMAIL_HOST_PASSWORD` | SMTP (SendGrid, Mailgun, SES…) |

Voir [SETUP_KEYS.md](../SETUP_KEYS.md) pour le guide détaillé.

### 3. Démarrer le backend

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

Le premier démarrage exécute automatiquement (entrypoint + bootstrap) :
- Attente Postgres + Redis
- `migrate` : applique toutes les migrations
- `collectstatic` : agrège les statiques Django admin
- `seed_forum_categories` : crée les catégories forum
- `setup_stripe_products` + `setup_webhook_endpoint` (si Stripe configuré)
- `gunicorn` démarre sur le port 8000

Traefik récupère les certificats Let's Encrypt en parallèle (~30s).

**Zéro commande manuelle** : pas besoin de lancer `migrate`, `collectstatic`, etc.
Tout passe par `manage.py bootstrap` dans l'entrypoint. Pour scaler le service
`api` à N replicas, un verrou Redis garantit qu'une seule instance fait le
bootstrap, les autres attendent puis exec gunicorn.

### 4. Démarrer le frontend

```bash
cd /opt/frontend-vizhome
cp .env.example .env.prod  # renseigner les OAuth client IDs
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

### 5. Vérifier

```bash
# Healthcheck API
curl -fsS https://api.vizhome.fr/health/ready
# → {"status":"ok","checks":{"postgres":"ok","redis":"ok"}}

# Frontend
curl -fsS -o /dev/null -w "%{http_code}\n" https://vizhome.fr
# → 200

# Dashboard Traefik (basic auth depuis le navigateur)
open https://traefik.vizhome.fr

# Logs combinés
docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f traefik api
```

### 6. Setup initial (1 seul superuser admin Django)

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec api \
    python manage.py createsuperuser
```

### 6. Configurer le webhook Stripe

Dashboard Stripe → Webhooks → **Add endpoint** :

- **URL** : `https://api.vizhome.fr/webhooks/stripe/webhook/`
- **Events** :
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `checkout.session.completed`
  - `invoice.payment_succeeded`
  - `invoice.payment_failed`

Copier le **Signing secret** dans `.env.prod` → `STRIPE_WEBHOOK_SECRET`,
puis recréer le container `api` :

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --force-recreate api
```

### 7. Configurer Celery Beat

Tâches cron à ajouter via l'admin Django (`/admin/django_celery_beat/periodictask/add/`) :

- **Task** : `apps.accounts.tasks.reset_monthly_render_counters`
- **Crontab** : `0 0 1 * *` (le 1er de chaque mois à 00:00)

## Backups automatisés

### Postgres (quotidien)

```bash
# /etc/cron.d/vizhome-backups
0 3 * * * root cd /opt/backend-vizhome && ./scripts/backup_postgres.sh
```

Le script :
- Dumpe la DB compressée dans `./backups/backup-YYYYMMDD-HHMMSS.sql.gz`
- Supprime les backups > 30 jours

### MinIO (hebdomadaire)

```bash
0 4 * * 0 root cd /opt/backend-vizhome && ./scripts/backup_minio.sh
```

Mirror complet du bucket. Rétention 7 jours par défaut.

::: tip Recommandation
Off-site : copie hebdomadaire des backups vers un stockage froid
(Backblaze B2, AWS S3 Glacier, Hetzner Storage Box…) via `rclone`.
:::

## Mise à jour

```bash
cd /opt/backend-vizhome
git pull origin main
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Le `entrypoint.sh` applique automatiquement les migrations au démarrage
du container api. Aucune action manuelle requise pour les schemas.

## Monitoring

### Sentry (recommandé)

Si `SENTRY_DSN` est défini, toutes les exceptions Django / Celery
remontent automatiquement à Sentry, avec :
- Stack traces
- User context (depuis JWT)
- Tags Celery (task name, retry count)

### Healthchecks Docker

Tous les services ont un `healthcheck` dans le compose. Surveiller avec :

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod ps
# STATUS = "Up X (healthy)"
```

### Métriques avancées (optionnel)

Pour aller plus loin :
- **Prometheus** + **Grafana** via `django-prometheus`
- **Loki** pour l'agrégation de logs
- **Uptime Kuma** pour le monitoring externe

## Rollback

```bash
# Revert au commit précédent
cd /opt/backend-vizhome
git log --oneline -5
git checkout <commit-hash>
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

::: warning
Les migrations Django sont **forward-only** par défaut. Si tu rollback
sur un code qui n'a plus la dernière migration, il faut explicitement
unmigrate via `python manage.py migrate <app> <migration>`.
:::

## Sécurité — checklist

- [ ] `DJANGO_DEBUG=False` en prod
- [ ] `DJANGO_SECRET_KEY` généré aléatoirement, jamais commit
- [ ] Mots de passe Postgres + MinIO forts (32+ caractères)
- [ ] HTTPS forcé via Traefik (`HSTS` 30 jours dans `prod.py`)
- [ ] Webhook Stripe avec signature validée (`DJSTRIPE_WEBHOOK_VALIDATION='verify_signature'`)
- [ ] Rate limiting actif (`django-axes` + DRF throttling)
- [ ] CORS limité à `app.vizhome.fr` uniquement
- [ ] Console MinIO protégée (firewall / IP allowlist / VPN)
- [ ] Backups testés (restore vérifié au moins 1 fois)
- [ ] Logs Sentry configurés (alertes sur erreurs critiques)
