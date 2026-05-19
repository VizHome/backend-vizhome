# VizHome — Backend

API REST Django + DRF qui propulse [VizHome](https://vizhome.fr) :
authentification, projets 3D, génération IA d'images, facturation Stripe et
stockage objet S3-compatible.

> Frontend : [`frontend-vizhome`](../frontend-vizhome) (Nuxt 4) ·
> Doc publique : [`docs-vizehome`](../docs-vizehome)

## Stack

| Couche | Choix |
|---|---|
| Framework | Django 5 + DRF 3.16 |
| Auth | JWT (`djangorestframework-simplejwt`) + 2FA TOTP (`django-otp`) + OAuth Google/GitHub |
| Base de données | PostgreSQL 16 (via `psycopg[binary]` v3) |
| Cache & broker | Redis 7 |
| Tâches async | Celery 5.4 + `django-celery-beat` |
| Provider IA | Google Gemini (`google-genai`) — pluggable via registry |
| Stockage objet | MinIO (S3-compatible) via `django-storages[s3]` + `boto3` |
| Paiement | Stripe via `dj-stripe` 2.9 |
| Documentation API | `drf-spectacular` (OpenAPI 3) |
| Sécurité | `django-axes` (lockout), `django-cors-headers`, JWT rotation + blacklist |
| Monitoring | Sentry SDK (optionnel) |
| Serveur prod | Gunicorn |

## Architecture en 5 lignes

- Un user envoie `POST /api/v1/renders/` → DRF retourne `202 pending`
- Une tâche Celery prend le relais : appelle Gemini, upload vers MinIO, marque `done`
- Le frontend poll `GET /api/v1/renders/{id}` toutes les 2s jusqu'au terminal state
- Pour les uploads de modèles 3D, le frontend obtient une **URL pré-signée**
  MinIO et envoie le binaire en direct (le backend ne voit jamais le fichier)
- Stripe webhook → `dj-stripe` synchronise les subscriptions → `UserStats`
  mis à jour via signaux

Voir [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) pour les diagrammes
détaillés.

## Démarrage rapide

### Prérequis

- Docker Desktop (Compose v2)
- Rien d'autre — toute la stack tourne en conteneurs

### Lancer la stack

```bash
cp .env.example .env
# (édite .env si tu veux changer les ports / secrets)

docker compose up -d
```

5 services démarrent :

| Service | Port | Rôle |
|---|---|---|
| `api` | 8000 | Django + DRF (Gunicorn en prod, runserver en dev) |
| `celery` | — | Worker async (renders IA) |
| `postgres` | 5432 | PostgreSQL 16 |
| `redis` | 6379 | Cache Django + broker Celery |
| `minio` | 9000 / 9001 | API S3 + console web |

Premier lancement : les migrations s'appliquent automatiquement via le
`entrypoint.sh`. Vérifie :

```bash
curl http://localhost:8000/health/ready
# → {"status":"ok","checks":{"postgres":"ok","redis":"ok"}}
```

### Créer un superuser

```bash
docker compose exec api python manage.py createsuperuser
```

Puis admin Django sur http://localhost:8000/admin/

### Documentation API live

- Swagger UI : http://localhost:8000/api/docs/
- ReDoc : http://localhost:8000/api/redoc/
- Schéma brut : http://localhost:8000/api/schema/

### Tester l'API avec Bruno

Une collection [Bruno](https://www.usebruno.com/) prête à l'emploi est
dans [`bruno/`](bruno/) — 57 requêtes pour les 48 endpoints, avec
chaînage automatique des tokens JWT et fixtures pré-remplies. Voir
[`bruno/README.md`](bruno/README.md) pour le workflow.

## Endpoints principaux

| Préfixe | Domaine |
|---|---|
| `/api/v1/auth/` | register, login, refresh, logout, 2FA verify, OAuth exchange |
| `/api/v1/me/` | profil, préférences, sessions, 2FA setup, change-password |
| `/api/v1/me/subscription/` | état Stripe, checkout, cancel |
| `/api/v1/me/invoices`, `/me/payment-methods` | facturation |
| `/api/v1/billing/plans` | catalogue public des plans |
| `/api/v1/projects/` | CRUD + scène 3D + modèles importés + annotations + share links |
| `/api/v1/renders/` | création + historique + détail |
| `/api/v1/shared/{token}` | accès public read-only via lien partagé |
| `/health/live`, `/health/ready` | liveness + readiness probes |
| `/webhooks/stripe/` | webhook dj-stripe (signature vérifiée) |

48 endpoints au total. Voir Swagger pour le détail.

## Configuration des intégrations tierces

Le backend démarre **sans aucune clé tierce** (mode dégradé). Chaque
intégration retourne une erreur explicite si non configurée, mais ne fait
pas planter le serveur.

Pour activer :

- **Gemini** : `GEMINI_API_KEY=...` dans `.env` → générations IA fonctionnent
- **Stripe** : `STRIPE_TEST_SECRET_KEY=...` + `setup_stripe_products` → checkout fonctionne
- **Google OAuth** : `GOOGLE_OAUTH_CLIENT_ID=...` → login Google fonctionne
- **GitHub OAuth** : `GITHUB_OAUTH_CLIENT_ID/SECRET` → login GitHub fonctionne
- **SMTP** : `EMAIL_HOST*` → vrais emails (sinon affichés en console)
- **Sentry** : `SENTRY_DSN=...` → tracking des erreurs en prod

Guide pas-à-pas pour chaque clé : [`SETUP_KEYS.md`](SETUP_KEYS.md)

## Commandes courantes

```bash
# Tests (pytest)
docker compose exec api pytest
docker compose exec api pytest apps/projects -k presigned   # filtré
docker compose exec api pytest --cov=apps                   # avec coverage

# Lint + format + types
docker compose exec api ruff check src/
docker compose exec api ruff format src/
docker compose exec api mypy src/

# Migrations
docker compose exec api python manage.py makemigrations
docker compose exec api python manage.py migrate

# Shell Django interactif
docker compose exec api python manage.py shell

# Setup Stripe (crée Products + Prices à partir de plans.py)
docker compose exec api python manage.py setup_stripe_products

# Export OpenAPI
docker compose exec api python manage.py spectacular --file schema.yml
```

## Structure du repo

```
backend-vizhome/
├── src/
│   ├── apps/
│   │   ├── accounts/      ← User + 2FA + OAuth + sessions
│   │   ├── projects/      ← Project + Scene + ImportedModel + presigned uploads
│   │   ├── renders/       ← Render + providers (Gemini) + tasks Celery
│   │   ├── billing/       ← dj-stripe + plans + checkout
│   │   ├── gallery/       ← endpoints sur Render filtrés par status=done
│   │   └── core/          ← healthchecks
│   ├── config/
│   │   ├── settings/      ← base / dev / prod / test (split)
│   │   ├── urls.py
│   │   ├── celery.py
│   │   └── wsgi.py
│   ├── manage.py
│   ├── requirements.txt
│   └── entrypoint.sh
├── docker/
│   └── Dockerfile         ← multi-stage (dev + prod)
├── docker-compose.yml     ← stack dev complète
├── docker-compose.prod.yml ← prod avec Traefik + Let's Encrypt
├── .env.example
├── SETUP_KEYS.md          ← activation des clés tierces
├── CLAUDE.md              ← instructions IA + règles du repo
└── docs/                  ← doc technique pour contributeurs
    ├── STRUCTURE.md
    ├── ARCHITECTURE.md
    ├── DEVELOPMENT.md
    ├── DEPLOYMENT.md
    └── CONTRIBUTING.md
```

## Déploiement production

Voir [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). Résumé :

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Traefik gère HTTPS + Let's Encrypt automatique. DNS A record requis sur
`api.vizhome.fr → IP serveur`.

## Conventions

- **Style** : `ruff` (lint + format), `mypy` (types)
- **Tests** : `pytest` obligatoire pour tout nouvel endpoint
- **Migrations** : 1 migration = 1 PR
- **Commits** : Conventional Commits (`feat`, `fix`, `refactor`, `docs`, `chore`)
- **PRs** : description + checklist [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)

## Ressources

- 📖 Documentation publique : https://docs.vizhome.fr
- 🐛 Issues : GitHub Issues (privé)
- 📧 Contact : dev@vizhome.fr

## Licence

Propriétaire — © VizHome 2026. Tous droits réservés.
