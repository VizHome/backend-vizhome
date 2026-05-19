# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Critical rule — keep `docs/` in sync

Every structural or behavioral change **must** be reflected in `docs/` in the
**same commit** as the code change. Doc updates are part of "done", not a
follow-up task.

| Type de changement | Fichier(s) à éditer |
|---|---|
| Nouvelle app Django, dossier, fichier de config | `docs/STRUCTURE.md` |
| Nouveau pattern, choix techno, refacto archi | `docs/ARCHITECTURE.md` |
| Nouvelle commande, script, workflow de dev | `docs/DEVELOPMENT.md` |
| Nouvelle variable d'env, étape de deploy, service externe | `docs/DEPLOYMENT.md` + `.env.example` |
| Nouvelle convention de code, règle de PR | `docs/CONTRIBUTING.md` |
| Nouvelle clé d'API tierce à activer | `SETUP_KEYS.md` |
| Nouvelle dépendance Python | `src/requirements.txt` (+ `ARCHITECTURE.md` si majeure) |

## Commands

All commands run inside the Docker stack (the dev environment is fully
containerized). Service name for the Django container is **`api`** (not
`backend`).

```bash
# Stack lifecycle
docker compose up -d                                  # start postgres + redis + minio + api + celery
docker compose logs -f api                            # live logs (replace api with celery, postgres…)
docker compose down                                   # stop everything
docker compose build api celery                       # rebuild after requirements change

# Tests (pytest, ~114 tests)
docker compose exec api pytest                        # all tests
docker compose exec api pytest apps/accounts          # single app
docker compose exec api pytest apps/accounts/tests/test_auth.py::test_login  # single test
docker compose exec api pytest --cov=apps             # with coverage

# Linting / formatting / typing
docker compose exec api ruff check src/               # lint
docker compose exec api ruff format src/              # auto-format
docker compose exec api mypy src/                     # type check

# Django
docker compose exec api python manage.py makemigrations
docker compose exec api python manage.py migrate
docker compose exec api python manage.py shell
docker compose exec api python manage.py createsuperuser

# Stripe / OpenAPI
docker compose exec api python manage.py setup_stripe_products
docker compose exec api python manage.py spectacular --file schema.yml
```

Settings module is selected via `DJANGO_SETTINGS_MODULE` env var. Default for
docker-compose is `config.settings.dev`; tests use `config.settings.test`;
prod uses `config.settings.prod`.

## Architecture

### App layout (`src/apps/`)

6 Django apps, each self-contained (models, serializers, views, urls, tests):

- **`accounts`** — Custom email-based User (`USERNAME_FIELD = 'email'`, no
  username column), 2FA TOTP via `django-otp`, OAuth (Google id_token verify,
  GitHub code exchange), `UserPreferences`, `UserStats`, `UserSession`
  tracking. JWT auth via `djangorestframework-simplejwt` with rotation +
  blacklist. Login lockout via `django-axes`.
- **`projects`** — `Project` (3D scene container), `Scene` (Three.js state in
  PostgreSQL `JSONField`), `ImportedModel` (GLB/OBJ/FBX/STL), `Annotation`,
  `ShareLink`. Presigned MinIO upload flow in `presigned.py`.
- **`renders`** — `Render` (single model serving prompt/sketch/screenshot →
  2D/3D via Gemini). **Async pipeline**: POST returns 202 + `pending` →
  Celery worker calls provider → uploads to MinIO → client polls until
  `status=done`. Pluggable IA via **provider registry** (`providers/registry.py`).
- **`billing`** — dj-stripe integration. Plans defined in `plans.py`
  (`PLAN_CONFIG`). Webhook handlers in `handlers.py`. Setup command:
  `setup_stripe_products`.
- **`gallery`** — Endpoints reusing `Render` filtering for `status=done`
  renders. No models of its own.
- **`core`** — Healthchecks (`/health/live`, `/health/ready`). No models.

### Non-obvious patterns to preserve

1. **Settings split** (`config/settings/{base,dev,prod,test}.py`) — don't
   collapse into one file. Each has a clear role (dev = DEBUG + console
   email; prod = HSTS + Sentry + SMTP + secure cookies; test = FileSystem
   storage + LocMem cache).

2. **Dual boto3 clients for MinIO** (`apps/projects/presigned.py`) — internal
   client points at `http://minio:9000` (Docker network), public client at
   `http://localhost:9000` (or public domain). **Required** because SigV4
   signatures include the host. Presigned PUT URLs let the browser upload
   directly to MinIO, bypassing Django.

3. **Provider registry pattern** (`apps/renders/providers/`) — `BaseProvider`
   ABC + `registry.py` mapping names to classes. Current implementation:
   `GeminiProvider` (`gemini-2.5-flash-image-preview`). To add OpenAI /
   Replicate / etc., implement `BaseProvider` and register; no view changes
   needed.

4. **Celery async render** (`apps/renders/tasks.py`, `config/celery.py`) —
   `max_retries=2`, `retry_delay=10s`, `task_time_limit=30min`. Status
   transitions: `pending → processing → done | failed`. Atomic `F()` queries
   for `UserStats` updates.

5. **AUTH_USER_MODEL discipline** — ForeignKeys to the user must use
   `settings.AUTH_USER_MODEL` (string), never `from apps.accounts.models
   import User`. Breaks migrations otherwise.

6. **Graceful provider fallback** — Stripe, Gemini, OAuth clients all have
   `is_configured()` checks. Endpoints return **503** if the integration is
   not configured rather than crashing with 500. Keep this pattern when
   adding new third-party integrations.

7. **Signal-driven stats sync** — `UserStats` counters
   (`total_projects`, `storage_used_bytes`, `renders_this_month`) are updated
   via `post_save` / `post_delete` signals. Don't compute these in views.

### Stack (versions confirmed in `src/requirements.txt`)

Django 5.2 · DRF 3.16 · `djangorestframework-simplejwt` 5.5+ · `django-otp` 1.5+ ·
dj-stripe 2.9 · Celery 5.4 + `django-celery-beat` 2.7 · boto3 1.35 ·
google-genai 1.0 · drf-spectacular 0.28 · django-axes 7.0 · psycopg 3.2+ ·
Redis (cache + Celery broker) · Sentry SDK 2.20

### Reference docs

- `docs/STRUCTURE.md` — full file tree, app breakdown
- `docs/ARCHITECTURE.md` — design rationale, diagrams
- `docs/DEVELOPMENT.md` — full dev workflow
- `docs/DEPLOYMENT.md` — `docker-compose.prod.yml`, Traefik, Stripe webhook
- `docs/CONTRIBUTING.md` — conventions, PR checklist
- `SETUP_KEYS.md` — Gemini, Stripe, Google OAuth, GitHub OAuth activation
- `README.md` — onboarding public (stack, démarrage Docker, scripts)

## Conventions

- **Lint/format**: `ruff` only (no black/flake8/isort)
- **Type check**: `mypy` (run before PR)
- **Tests**: `pytest` mandatory for any new endpoint
- **Commits**: Conventional Commits (`feat`, `fix`, `refactor`, `docs`, `chore`)
- **Branches**: `feat/`, `fix/`, `chore/`
