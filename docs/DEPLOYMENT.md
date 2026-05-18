# Déploiement — backend-vizhome

Guide de mise en production du backend Django.

## Stack de production

`docker-compose.prod.yml` orchestre 7 services :

| Service | Rôle |
|---|---|
| `traefik` | Reverse proxy + HTTPS automatique Let's Encrypt |
| `postgres` | DB principale, volume persistant |
| `redis` | Broker Celery + cache + 2FA challenges, persistance activée |
| `minio` | Storage S3-compatible, exposé sur cdn.vizhome.fr |
| `minio-init` | Job one-shot : crée le bucket + policy publique |
| `api` | Django via Gunicorn (4 workers) |
| `celery` | Worker async pour les rendus IA |
| `celery-beat` | Cron jobs (reset compteurs mensuels) |

## Prérequis serveur

- **Linux** (Debian / Ubuntu / Rocky) avec **Docker Engine** + **Compose v2**
- **2 vCPU, 4 Go RAM** minimum (8 Go recommandé)
- **40 Go disque** (système + DB + MinIO + logs)
- **Ports 80/443** ouverts
- **Domaines DNS** :
  - `api.vizhome.fr` → IP serveur
  - `cdn.vizhome.fr` → IP serveur
  - `minio.vizhome.fr` → IP serveur (optionnel, console MinIO)

## Premier déploiement

### 1. Préparer le repo

```bash
ssh root@vizhome.fr
cd /opt
git clone https://github.com/VizHome/backend-vizhome.git
cd backend-vizhome
```

### 2. Configurer l'environnement

```bash
cp .env.prod.example .env.prod
nano .env.prod
```

Champs **obligatoires** à remplir :

| Variable | Comment |
|---|---|
| `DJANGO_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `POSTGRES_PASSWORD` | Mot de passe Postgres fort |
| `MINIO_S3_ACCESS_KEY` + `MINIO_S3_SECRET_KEY` | Identifiants MinIO (forts) |
| `ACME_EMAIL` | Email pour Let's Encrypt |
| `API_HOST`, `MINIO_PUBLIC_HOST`, `MINIO_CONSOLE_HOST` | Domaines DNS |

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

### 3. Démarrer

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Le premier démarrage :
- Build l'image Django (~1-2 min)
- Pull Postgres, Redis, MinIO, Traefik
- Applique les migrations (entrypoint.sh)
- Initialise le bucket MinIO
- Traefik récupère les certificats Let's Encrypt (~30s)

### 4. Vérifier

```bash
# Healthcheck
curl -fsS https://api.vizhome.fr/health/ready
# → {"status":"ok","checks":{"postgres":"ok","redis":"ok"}}

# Logs en cas de pépin
docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f api
```

### 5. Setup initial

```bash
# Superuser admin Django
docker compose -f docker-compose.prod.yml --env-file .env.prod exec api \
    python manage.py createsuperuser

# Products + Prices Stripe (si Stripe configuré)
docker compose -f docker-compose.prod.yml --env-file .env.prod exec api \
    python manage.py setup_stripe_products
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
