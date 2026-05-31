# Structure du projet — backend-vizhome

Vue arborescente complète du repository Django, avec rôle de chaque
fichier et dossier.

## Arborescence racine

```
backend-vizhome/
├── src/                          ← code Django (séparé pour Docker mount)
│   ├── manage.py                 commande CLI Django
│   ├── requirements.txt          deps runtime
│   ├── requirements-dev.txt      deps dev (pytest, ruff, mypy…)
│   ├── config/                   module de configuration Django
│   │   ├── settings/
│   │   │   ├── base.py           settings communs
│   │   │   ├── dev.py            DEBUG, CORS permissif
│   │   │   ├── prod.py           HSTS, Sentry, email SMTP
│   │   │   └── test.py           Storage FileSystem (pas MinIO en tests)
│   │   ├── urls.py               routing racine + API v1
│   │   ├── wsgi.py / asgi.py
│   │   └── celery.py             instance Celery + autodiscover
│   └── apps/                     7 apps métier
│       ├── core/                 healthcheck, middleware partagé
│       ├── accounts/             User custom + 2FA + OAuth + sessions
│       ├── projects/             Project + Scene + ImportedModel + Annotation
│       ├── renders/              Render + providers IA (Gemini)
│       ├── gallery/              endpoints galerie (réutilise renders)
│       ├── billing/              dj-stripe + plans + webhook handlers
│       └── forum/                Category + Topic + Reply (forum communautaire)
│
├── docker/
│   ├── Dockerfile                multi-stage prod (~629 MB)
│   ├── Dockerfile.dev            dev avec deps de compilation
│   └── entrypoint.sh             attend Postgres + run migrations
│
├── scripts/
│   ├── backup_postgres.sh        cron dump compressé + rétention
│   └── backup_minio.sh           mirror MinIO (snapshot)
│
├── .github/workflows/
│   └── ci.yml                    lint (ruff) + tests (pytest) + build
│
├── docker-compose.yml            stack dev (postgres + redis + minio + mailpit + api + celery)
├── docker-compose.prod.yml       stack prod (+ traefik + celery-beat)
├── .env / .env.example
├── .env.prod.example
├── pyproject.toml                config ruff + mypy + pytest
├── SETUP_KEYS.md                 guide d'activation Gemini/Stripe/OAuth
├── README.md
├── LICENSE
└── bruno/                        collection Bruno (test API end-to-end)
    ├── bruno.json                config collection
    ├── README.md                 workflow conseillé + variables d'env
    ├── openapi.yml               schéma OpenAPI 3 export (régénéré depuis Django)
    ├── environments/             Local.bru, Production.bru
    ├── 01-Health/                liveness + readiness
    ├── 02-Auth/                  register, login, refresh, logout, 2FA, OAuth (8 req)
    ├── 03-Me/                    profil, prefs, sessions, 2FA setup (10 req)
    ├── 04-Projects/              CRUD + Scene
    │   ├── Models/               upload (multipart + presigned)
    │   ├── Annotations/          CRUD annotations 3D
    │   └── Sharing/              liens publics
    ├── 05-Renders/               création (prompt + sketch) + polling + history
    ├── 06-Billing/               plans, subscription, invoices, payment-methods
    └── 07-Forum/                 categories, topics, replies (11 req)
```

## Détail des apps

### `apps/core/`

```
core/
├── apps.py
├── views.py                      liveness + readiness
├── urls.py                       /health/live, /health/ready
└── (pas de models — utilitaires uniquement)
```

Endpoints `/health/*` pour Docker healthcheck + load balancer prod.

### `apps/accounts/`

```
accounts/
├── apps.py                       ready() → load signals
├── managers.py                   UserManager (email-based, pas username)
├── models.py                     User, UserPreferences, UserStats, UserSession
├── signals.py                    post_save User → create Prefs + Stats
├── serializers.py                Register, Login, Me, Preferences, Sessions
├── views.py                      Auth + Me + Sessions + ChangePassword
├── urls.py                       auth_patterns + me_patterns
├── permissions.py                custom DRF permissions
├── throttling.py                 RegisterThrottle, LoginThrottle, ForgotPasswordThrottle
├── lockout.py                    Réponse 429 axes (DRF + JsonResponse)
├── utils.py                      get_client_ip, parse_device_name
├── two_factor.py                 TOTP setup / verify / disable
├── admin.py
├── oauth/                        sous-package
│   ├── base.py                   OAuthProvider abstract + OAuthProfile
│   ├── google.py                 Google id_token verify
│   ├── github.py                 GitHub code exchange
│   ├── registry.py               get_provider('google'|'github')
│   └── views.py                  POST /auth/oauth/{provider}/exchange
├── management/commands/
│   └── reset_monthly_counters.py reset UserStats.renders_this_month
├── migrations/
└── tests/                        19 tests (auth/me/sessions/2fa/oauth/security)
```

### `apps/projects/`

```
projects/
├── apps.py
├── models.py                     Project, Scene, ImportedModel, Annotation, ShareLink
├── signals.py                    auto-Scene à la création + sync UserStats storage
├── serializers.py                ProjectListSerializer, ProjectDetailSerializer, etc.
├── views.py                      CRUD + Scene + Models + Annotations + Share + Shared
├── urls.py
├── permissions.py                IsProjectOwner
├── presigned.py                  helpers boto3 (upload_url + head_object + copy_object)
├── admin.py
├── migrations/
└── tests/                        30 tests
```

### `apps/renders/`

```
renders/
├── apps.py
├── models.py                     Render (1 modèle pour 3 sources)
├── tasks.py                      @shared_task generate_render (Celery)
├── serializers.py                RenderCreateSerializer + RenderSerializer
├── views.py                      List/Create + Detail + History
├── urls.py
├── admin.py
├── providers/                    abstraction multi-IA
│   ├── base.py                   BaseProvider + GenerationResult + ProviderError
│   ├── gemini.py                 GeminiProvider (gemini-2.5-flash-image-preview)
│   └── registry.py               get_provider('gemini') → ouvert OpenAI/Replicate
├── migrations/
└── tests/                        26 tests
```

### `apps/billing/`

```
billing/
├── apps.py                       ready() → load handlers
├── plans.py                      PLAN_CONFIG (source de vérité)
├── stripe_client.py              wrapper Stripe SDK (is_configured)
├── serializers.py                PlanSerializer, CheckoutRequestSerializer, etc.
├── views.py                      Plans + Subscription + Invoices + PaymentMethods
├── urls.py                       public_patterns + me_patterns
├── handlers.py                   djstripe_receiver → User.plan + quotas
├── apps.py
├── management/commands/
│   └── setup_stripe_products.py  crée Products + Prices côté Stripe
└── tests/                        19 tests (mocks Stripe)
```

### `apps/gallery/`

Reposting les endpoints galerie (filtrage des renders `status=done`).
Pas de modèles propres — réutilise `Render` de `apps.renders`.

### `apps/forum/`

```
forum/
├── apps.py                       ready() → load signals
├── models.py                     Category, Topic, Reply
├── signals.py                    update topics_count + replies_count + last_reply_at
├── serializers.py                Category, Topic (List + Detail + Create), Reply
├── views.py                      CRUD complet + GET public + permissions custom
├── urls.py
├── permissions.py                IsAuthorOrReadOnly, IsAuthorOrStaff
├── admin.py
├── management/commands/
│   └── seed_forum_categories.py  seed des 5 cats par défaut
├── migrations/
└── tests/                        18 tests (categories + topics + replies + cascade)
```

**Endpoints** (sous `/api/v1/forum/`) :
- `GET    /categories` — liste publique (pas paginé)
- `GET    /categories/{slug}` — détail
- `GET    /topics` — liste paginée (filtres `?category=`, `?search=`, `?ordering=`)
- `POST   /topics` — créer (auth)
- `GET    /topics/{id}` — détail + auto-incrémente views_count
- `PATCH  /topics/{id}` — édit (auteur ou staff)
- `DELETE /topics/{id}` — supprime (auteur ou staff)
- `GET    /topics/{id}/replies` — liste paginée
- `POST   /topics/{id}/replies` — créer (auth, refusé si topic locked)
- `PATCH  /replies/{id}` — édit (auteur ou staff)
- `DELETE /replies/{id}` — supprime (auteur ou staff)

## Migration vers production

```
docker/Dockerfile          ←  build prod multi-stage
docker-compose.prod.yml    ←  stack prod avec Traefik
.env.prod.example          ←  variables prod
```

Voir [DEPLOYMENT.md](./DEPLOYMENT.md) pour le déploiement complet.

## Tests

```bash
docker compose exec api pytest                     # tous (114 tests)
docker compose exec api pytest apps/accounts       # par app
docker compose exec api pytest -k oauth            # par mot-clé
docker compose exec api pytest --cov=apps          # avec coverage
```

Structure des tests :

```
apps/<nom>/tests/
├── __init__.py
├── conftest.py          fixtures pytest (auth_client, user, etc.)
├── test_models.py       (parfois implicite)
├── test_views.py
├── test_serializers.py
└── ...
```
