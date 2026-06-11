# VizHome Backend

<div align="center">
  <img src="./public/images/logo/LogoBlack.png" alt="VizHome" width="120">
</div>


> API REST Django pour la plateforme SaaS **VizHome** — génération de rendus 3D
> par IA (Gemini), forum communautaire, support helpdesk, billing Stripe.

[![CI](https://github.com/VizHome/backend-vizhome/actions/workflows/ci.yml/badge.svg)](https://github.com/VizHome/backend-vizhome/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/VizHome/backend-vizhome)](https://github.com/VizHome/backend-vizhome/releases)
[![Docker](https://img.shields.io/badge/ghcr.io-vizhome--backend-blue)](https://github.com/VizHome/backend-vizhome/pkgs/container/vizhome-backend)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=VizHome_backend-vizhome&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=VizHome_backend-vizhome)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=VizHome_backend-vizhome&metric=coverage)](https://sonarcloud.io/summary/new_code?id=VizHome_backend-vizhome)

---

## ✨ Features

- 🔐 **Auth complète** : email/password, JWT (15 min access + refresh blacklist), 2FA TOTP, OAuth Google + GitHub
- 🎨 **Génération IA** : pipeline async `prompt → Gemini image API → MinIO → galerie user`
- 🧱 **Projets 3D** : CRUD + scene Three.js sérialisée en JSONField + upload presigned MinIO (modèles GLB/OBJ/FBX/STL)
- 💬 **Forum** : catégories, topics, replies, modération staff (pin/lock/solution), édition 15 min, sanitisation HTML
- 🆘 **Support helpdesk** : tickets utilisateur ↔ staff, threading, transitions auto status, notifications email
- 👨‍💼 **Admin panel** : overview consolidé, drill-downs, audit log, CSV exports, snapshots quotidiens
- 💳 **Billing Stripe** : checkout sessions, webhooks dj-stripe, subscriptions + invoices sync, MRR
- 📦 **Storage S3** : MinIO (dev) / S3 compatible (prod) avec presigned uploads
- ⚡ **Async** : Celery + Redis pour les tâches longues (renders IA, emails, cleanup)

## 🛠 Stack

| Couche | Tech |
|---|---|
| Framework | Django 6 + DRF + simple-jwt |
| DB | PostgreSQL 16 (psycopg 3) |
| Cache + broker | Redis 7 |
| Storage | MinIO / S3 via django-storages |
| Tâches | Celery + django-celery-beat |
| Auth | django-axes, django-otp, google-auth |
| Billing | dj-stripe + Stripe SDK (+ patch compat `apps/billing/compat.py`) |
| Monitoring | Sentry (prod) |
| IA | Google GenAI (Gemini) |
| Tests | pytest + pytest-django + pytest-cov |
| Lint | ruff |
| Doc API | drf-spectacular (OpenAPI 3) |

## 🚀 Quick start (Docker)

```bash
git clone https://github.com/VizHome/backend-vizhome.git
cd backend-vizhome

cp .env.example .env
# Édite .env : ajoute GEMINI_API_KEY, STRIPE_TEST_SECRET_KEY, etc.
# (cf SETUP_KEYS.md)

docker compose up -d

# Migrations + superuser (une fois)
docker compose exec api python manage.py migrate
docker compose exec api python manage.py createsuperuser

# Setup Stripe products (si configuré)
docker compose exec api python manage.py setup_stripe_products
docker compose exec api python manage.py setup_webhook_endpoint
```

### Services exposés

| URL | Service |
|---|---|
| http://localhost:8000 | API Django |
| http://localhost:8000/api/docs/ | Swagger UI |
| http://localhost:8000/admin/ | Django admin |
| http://localhost:8081 | pgweb (UI Postgres) |
| http://localhost:9000 / :9001 | MinIO API / Console |
| http://localhost:8025 | Mailpit (mails dev) |

## 📜 Commandes utiles

```bash
# Tests + coverage
docker compose exec api pytest -v
docker compose exec api pytest apps/forum -k "edit_window"
docker compose exec api pytest --cov=apps --cov-report=term

# Lint + format
docker compose exec api ruff check src/
docker compose exec api ruff format src/

# Type check
docker compose exec api mypy --config-file pyproject.toml src/

# Shell Django (autoreload)
docker compose exec api python manage.py shell

# Migrations
docker compose exec api python manage.py makemigrations
docker compose exec api python manage.py migrate

# Reset complet (DESTRUCTIF)
docker compose down -v && docker compose up -d
```

## 🧪 Stripe webhook en local

Le pipeline `customer.subscription.*` requiert que **Stripe CLI** tourne :

```bash
# 1. Install + auth
stripe login

# 2. Créer un WebhookEndpoint en DB (une fois)
docker compose exec api python manage.py setup_webhook_endpoint
# → affiche l'URL avec UUID

# 3. Forwarding (terminal séparé)
stripe listen --forward-to http://localhost:8000/webhooks/stripe/webhook/<UUID>/
# → copie le whsec_xxx dans .env (STRIPE_WEBHOOK_SECRET)
# → docker compose up -d --force-recreate api
```

Détails : `docs/DEVELOPMENT.md > Stripe : webhook en local`.

## 📂 Architecture

```
src/
├── config/                Settings (base, dev, prod, test) + routing
├── apps/
│   ├── core/              healthchecks
│   ├── accounts/          User + 2FA + OAuth + sessions
│   ├── projects/          Project + Scene + ImportedModel + Annotation
│   ├── renders/           Render + providers IA (Gemini)
│   ├── gallery/           endpoints galerie (réutilise renders)
│   ├── billing/           dj-stripe + plans + handlers + compat.py
│   ├── forum/             Category + Topic + Reply + uploads
│   ├── support/           SupportTicket + SupportMessage + notifications
│   └── admin_panel/       AdminAuditLog + AdminDailySnapshot + 9 endpoints
└── manage.py
```

Détails dans `docs/STRUCTURE.md`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`.

## 🔁 CI / CD

| Trigger | Workflow | Action |
|---|---|---|
| Push `main`/`dev` ou PR | `ci.yml` | lint, typecheck, tests+coverage, build Docker, smoke, Trivy |
| Push `main` | `release.yml` | release-please PR → tag + GitHub Release + image GHCR multi-arch + SBOM |
| Push `dev` | `pre-release.yml` | image `dev-<sha>` + GitHub Pre-Release |
| PR | `pr-checks.yml` | titre Conventional Commits + size label + TruffleHog |

Tous les commits doivent suivre **[Conventional Commits](https://www.conventionalcommits.org/)** — détails dans `.github/CONTRIBUTING_CI.md`.

### Secrets GitHub requis

- `GH_PAT` : Personal Access Token (scopes `repo`, `write:packages`)
- `SONAR_TOKEN` + `SONAR_HOST_URL` : SonarCloud/SonarQube
- `CODECOV_TOKEN` (optionnel)

## 📊 Endpoints principaux

Swagger : http://localhost:8000/api/docs/ — quelques highlights :

```
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/oauth/{google,github}/exchange

GET    /api/v1/me/                            profil + stats + prefs
GET    /api/v1/me/subscription
POST   /api/v1/me/subscription/checkout

POST   /api/v1/renders/                       create render (async)
GET    /api/v1/renders/                       gallery paginée

GET    /api/v1/forum/topics
POST   /api/v1/forum/topics
POST   /api/v1/forum/topics/{id}/replies

GET    /api/v1/support/tickets
POST   /api/v1/support/tickets

GET    /api/v1/admin/overview                 staff-only
GET    /api/v1/admin/audit-log
```

## 🤝 Contribution

1. Crée une branche `feat/<nom>` ou `fix/<nom>` depuis `dev`
2. Code + tests + docs (cf règle "même commit" dans `CLAUDE.md`)
3. PR vers `dev` avec un titre Conventional Commits (`feat(auth): …`)
4. Merge sur `dev` → pre-release auto
5. Quand prêt : PR `dev → main` → release-please prend le relais

## 📄 License

[MIT](LICENSE)
