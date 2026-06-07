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
│   └── apps/                     apps métier
│       ├── core/                 healthcheck, middleware partagé
│       ├── accounts/             User custom + 2FA + OAuth + sessions
│       ├── projects/             Project + Scene + ImportedModel + Annotation
│       ├── renders/              Render + providers IA (Gemini)
│       ├── gallery/              endpoints galerie (réutilise renders)
│       ├── billing/              dj-stripe + plans + webhook handlers
│       ├── forum/                Category + Topic + Reply (forum communautaire)
│       ├── support/              SupportTicket + SupportMessage (ticketing helpdesk)
│       └── gdpr/                 ExportRequest + DeletionRequest (RGPD art. 15/17/20)
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
│   ├── ci.yml                    lint (ruff) + tests (pytest) + build
│   └── benchmarks.yml            microbench pytest-benchmark (main only)
│
├── benchmarks/                   bench performance (hors src/, indep de Django)
│   ├── README.md                 mode d'emploi local + CI
│   ├── locustfile.py             5 scenarios load test HTTP (Locust)
│   ├── test_perf.py              microbench Python (pytest-benchmark)
│   └── conftest.py               injecte src/ dans sys.path
│
├── Makefile                      targets bench-local / bench-headless / bench-micro / bench-compare
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
    ├── 07-Forum/                 categories, topics, replies, upload image, moderation (15 req)
    ├── 08-Admin/                 overview, users, renders, timeline, audit-log,
    │                             subscriptions, invoices, forum/topics, support/tickets,
    │                             CSV exports (12 req)
    └── 09-Support/               tickets CRUD + messages threading (4 req)
```

## Détail des apps

### `apps/core/`

```
core/
├── apps.py
├── views.py                      liveness + readiness
├── urls.py                       /health/live, /health/ready
├── tests.py                      tests healthcheck + bootstrap command
└── management/commands/
    └── bootstrap.py              orchestrateur "zéro-commande" pour le deploy
```

Endpoints `/health/*` pour Docker healthcheck + load balancer prod.

**`manage.py bootstrap`** : exécuté par l'entrypoint Docker au démarrage de
l'API. Idempotent. Étapes : `migrate` → `collectstatic` → `compilemessages`
→ `seed_forum_categories` → `setup_stripe_products` → `setup_webhook_endpoint`.
Sûr en multi-replica grâce à un verrou Redis (`vizhome:bootstrap:lock`, TTL
5 min). Flags : `--skip-stripe`, `--skip-lock`, `--only <step>`,
`--wait-for-lock <sec>`.

### `apps/contact/`

```
contact/
├── apps.py
├── models.py                     NewsletterSubscriber (email opt-in)
├── serializers.py                ContactMessageSerializer
├── views.py                      POST /api/v1/contact/ (public, rate-limited 5/h)
├── admin.py                      gestion staff des subscribers
├── urls.py
├── tests.py
├── templates/contact/            email HTML + text (Reply-To direct user)
└── migrations/0001_initial.py
```

Form de contact public marketing site. Envoie un email à
`CONTACT_RECIPIENT_EMAIL` (défaut `contact@vizhome.fr`) via `send_mail`.
Si `newsletter_opt_in=True`, crée/réactive un `NewsletterSubscriber`
idempotent par email (lowercase normalisé).

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

### `apps/forum/`

```
forum/
├── apps.py                        ready() → load signals
├── models.py                      Category, Topic, Reply, ForumUpload
├── signals.py                     compteurs cache + mark uploads `used`
├── serializers.py                 Category, Topic, Reply
├── views.py                       CRUD forum + ForumImageUploadView (multipart)
├── urls.py                        12 endpoints (incl. upload-image)
├── permissions.py                 IsAuthorOrReadOnly, IsAuthorOrStaff
├── uploads.py                     extract_used_keys() — parse `<img src>` HTML
├── tasks.py                       cleanup_forum_orphan_uploads_task (Celery)
├── admin.py
├── management/commands/
│   ├── seed_forum_categories.py   bootstrap des 5 catégories par défaut
│   └── cleanup_forum_orphan_uploads.py  GC images uploadées sans post
├── migrations/
│   ├── 0001_initial.py
│   └── 0002_forumupload.py
└── tests/                         41 tests (views + uploads/cleanup)
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

### `apps/admin_panel/`

Endpoints staff-only pour le dashboard interne (cf
`frontend-vizhome/pages/admin/*.vue`).

```
admin_panel/
├── apps.py
├── models.py                      ★ AdminAuditLog + AdminDailySnapshot (Phase 3)
├── audit.py                       ★ log_admin_action() helper (actor + IP + UA + payload)
├── renderers.py                   ★ CSVRenderer (flatten {results} → text/csv + filename)
├── views.py                       9 views (overview, users CRUD, renders, timeline,
│                                  audit-log, subscriptions, invoices, forum/topics)
├── serializers.py                 AdminUser + AdminUserUpdate + AdminRender + AdminAuditLog
├── urls.py                        9 endpoints
├── tasks.py                       ★ snapshot_metrics_task (Celery, name='admin_panel.snapshot_metrics')
├── management/commands/
│   └── snapshot_admin_metrics.py  ★ snapshot daily metrics → AdminDailySnapshot
└── tests/                         28+ tests (overview + drill-down + permissions + garde-fous)
```

Endpoints (9, tous staff-only — `IsAuthenticated + IsAdminUser`) :
- `GET /api/v1/admin/overview` — toutes les métriques en 1 réponse
- `GET /api/v1/admin/users` — liste paginée + filtres ; aussi `?format=csv` (CSVRenderer)
- `GET/PATCH /api/v1/admin/users/{id}` — modération (ban/unban, promote/demote staff)
  avec garde-fous anti self-demotion / self-deactivation + **audit log avant/après**
- `GET /api/v1/admin/renders` — liste paginée + filtres ; aussi `?format=csv`
- `GET /api/v1/admin/timeline?days=N` — séries temporelles pour graphiques
- `GET /api/v1/admin/audit-log` — journal d'audit paginé + filtres (action, actor, target_type)
- `GET /api/v1/admin/subscriptions` — subscriptions Stripe actives (mode `no_djstripe` détecté)
- `GET /api/v1/admin/invoices` — 100 dernières factures Stripe
- `GET /api/v1/admin/forum/topics` — liste paginée pour modération (réutilise `TopicListSerializer`).
  Les actions pin/lock/delete passent par `/forum/topics/{id}/...` qui auditent via `log_admin_action`.

**Patterns Phase 3** :
- `AdminAuditLog` n'utilise pas de FK vers la cible → utilise `target_type` + `target_id` + `target_repr`
  pour survivre aux suppressions.
- `AdminDailySnapshot` capture l'overview chaque jour. Sérialisation : payload passé à
  `json.loads(json.dumps(..., cls=DjangoJSONEncoder))` pour gérer les datetimes imbriqués.
- `CSVRenderer` détecte la structure paginée DRF `{count, results}` et set
  `Content-Disposition: attachment; filename=<csv_filename>-<date>.csv`.

### `apps/forum/`

```
forum/
├── apps.py                       ready() → load signals
├── models.py                     Category, Topic, Reply
├── signals.py                    update topics_count + replies_count + last_reply_at
├── serializers.py                Category, Topic (List + Detail + Create), Reply
├── views.py                      CRUD complet + GET public + permissions custom
├── urls.py
├── permissions.py                IsAuthorOrReadOnly, IsAuthorOrStaff,
│                                 IsAuthorWithinTimeWindowOrStaff (édition 15 min),
│                                 ★ IsNotForumBanned (bloque write si user.is_banned_from_forum)
├── admin.py
├── management/commands/
│   └── seed_forum_categories.py  seed des 5 cats par défaut
├── migrations/
└── tests/                        18 tests (categories + topics + replies + cascade)
```

★ **Modération user-level** (Phase 4) : la flag `User.is_banned_from_forum`
empêche la création de topics/réponses (lecture reste libre). Géré depuis
`/admin/users` (action "Bannir du forum") avec audit log dédié.

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

### `apps/support/`

Système de tickets utilisateur ↔ staff (mini-helpdesk).

```
support/
├── apps.py
├── models.py                     SupportTicket (status/priority/category) + SupportMessage
├── serializers.py                Ticket (List/Detail/Create) + Message (read/create) + UpdateStatus
├── views.py                      TicketListCreateView, TicketDetailView,
│                                 TicketMessageCreateView, AdminTicketListView
├── urls.py                       3 endpoints user (+ 1 endpoint admin monté sur /admin/support/tickets)
├── admin.py                      Inline messages dans Django admin
├── notifications.py              notify_staff_new_ticket / notify_user_staff_replied /
│                                 notify_staff_user_replied (send_mail + fail_silently)
├── migrations/
└── tests/                        26 tests (CRUD + perms + transitions + emails + pseudo)
```

**Endpoints user** (sous `/api/v1/support/`) :
- `GET    /tickets` — liste paginée de mes tickets (annotés `messages_count`, `last_message_at`, `last_message_from_staff`)
- `POST   /tickets` — créer (subject + category + priority + body 1er message)
- `GET    /tickets/{id}` — détail + messages threadés
- `POST   /tickets/{id}/messages` — répondre

**Endpoint admin** (sous `/api/v1/admin/`) :
- `GET    /admin/support/tickets` — liste paginée tous tickets (filtres status/priority/category/assignee/search)
- `PATCH  /support/tickets/{id}` — staff change status/priority/assignee

**Transitions automatiques de status** :
- 1ère réponse staff → ticket passe en `pending` + assignee staff
- Reply user sur ticket `resolved` → repasse en `pending` (insatisfait)
- Reply impossible si ticket `closed`

**Notifications email** (envoyées via Mailpit en dev, SMTP réel en prod,
`fail_silently=True` pour ne jamais bloquer l'UX) :
- Création ticket → mail à TOUS les staffs actifs (file d'attente partagée)
- Reply staff → mail à l'auteur du ticket
- Reply user sur ticket assigné → mail à l'assignee uniquement (pas à tous
  les staffs pour éviter le spam)

### `apps/gdpr/`

Conformité RGPD : export des données personnelles (art. 15 + 20) et
suppression de compte avec délai de rétractation (art. 17).

```
gdpr/
├── apps.py
├── models.py                    ExportRequest + DeletionRequest
├── serializers.py               ExportRequestSerializer + DeletionRequestSerializer
│                                + DeleteAccountInputSerializer (confirm == "DELETE")
├── views.py                     ExportDataView + ExportDataStatusView
│                                + RequestDeleteAccountView + CancelDeleteAccountView
├── tasks.py                     ★ build_user_export_zip (Celery)
│                                + cleanup_expired_exports (cron horaire)
│                                + cleanup_pending_deletions (cron quotidien)
├── storage.py                   wrappers default_storage / presigned MinIO
├── authentication.py            JWTAuthenticationAllowInactive (cancel post soft delete)
├── urls.py                      me_patterns ajoutés à `/api/v1/me/`
├── admin.py                     ExportRequest + DeletionRequest en lecture seule
├── tests/                       conftest + test_export + test_delete_account + test_tasks
└── migrations/0001_initial.py
```

Endpoints (montés sous `/api/v1/me/` via `config/urls.py`) :
- `POST   /me/export-data` — déclenche un job Celery (idempotent : renvoie
  la demande QUEUED/PROCESSING existante au lieu de doubler le job)
- `GET    /me/export-data/status` — statut de la dernière demande
  + URL de téléchargement signée 24h si `status=ready`
- `POST   /me/delete-account` — exige `{"confirm": "DELETE"}`,
  soft delete immédiat (`is_active=False`, sessions JWT révoquées),
  `DeletionRequest(scheduled_for = now + 30j)` créé
- `POST   /me/delete-account/cancel` — réactive le compte tant que la
  tâche cron n'a pas hard-delete. Accepte les tokens même pour
  `is_active=False` (custom `JWTAuthenticationAllowInactive`).

Tâches Celery (à planifier via `django-celery-beat`) :
- `gdpr.build_user_export_zip(export_id)` — déclenchée à la demande
  utilisateur ; produit un ZIP `{README.md, data.json}` uploadé via
  `default_storage` (MinIO en prod, FileSystem en tests), TTL 24h
- `gdpr.cleanup_expired_exports` — horaire, supprime les archives dont
  `expires_at <= now`
- `gdpr.cleanup_pending_deletions` — quotidien à 03:00, hard-delete les
  comptes dont `scheduled_for <= now` ET ni annulés ni complétés.
  `user.delete()` cascade sur tous les FK (projets, renders, forum,
  support, sessions, etc.).

Limites connues (à documenter côté UX privacy) :
- Les emails déjà envoyés (Mailpit en dev, SMTP en prod) ne sont pas
  effacés — ils restent côté serveur SMTP / destinataires.
- Les facteurs Stripe (Customer, Invoices) ne sont pas effacés
  automatiquement côté Stripe ; à supprimer manuellement ou via un
  cron dédié (obligations légales facturation FR : 10 ans).
- Les logs applicatifs (Sentry, fichiers) ne sont pas purgés — TTL
  géré côté Sentry (90j) et logrotate.

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
