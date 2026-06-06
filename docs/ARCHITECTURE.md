# Architecture — backend-vizhome

Choix de design et patterns appliqués dans le backend Django.

## Vue d'ensemble

```
┌──────────────────────────────────────────────────────────────────┐
│                       Navigateur utilisateur                     │
│         (Nuxt 4 SPA — http://localhost:3000 ou app.*)            │
└────────────────┬─────────────────────────────────┬───────────────┘
                 │ JWT REST                        │ direct PUT
                 │ /api/v1/*                       │ MinIO presigned
                 ▼                                 ▼
┌────────────────────────────────┐   ┌─────────────────────────────┐
│   api (Django + Gunicorn)      │   │  minio (S3-compatible)      │
│   - DRF, JWT, axes, 2FA        │   │  bucket vizhome-media       │
│   - dj-stripe webhooks         │   │  (renders + modèles 3D)     │
│   - drf-spectacular (OpenAPI)  │   └─────────────────────────────┘
└─────┬──────────┬────────┬──────┘
      │          │        │
      ▼          ▼        ▼
┌──────────┐ ┌────────┐ ┌──────────────┐
│postgres  │ │redis   │ │ celery       │
│ Users,   │ │ broker │ │ - generate_  │
│ Projects,│ │ + cache│ │   render     │
│ Renders, │ │ + 2FA  │ │              │
│ Scenes…  │ │challen-│ │ celery-beat  │
└──────────┘ │ges     │ │ - reset      │
             └────────┘ │   monthly    │
                        └──────────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │ Gemini API · Stripe   │
                  │ SMTP · Sentry         │
                  └───────────────────────┘
```

## Principes

### 1. Apps modulaires sans dépendances cycliques

Chaque app a une responsabilité claire, et les dépendances entre apps
sont **toujours dans le même sens** :

```
billing  ─┐
renders  ─┤
projects ─┴─►  accounts  ─► (Django core)
```

Si tu ajoutes une nouvelle app, place-la au bon niveau de la hiérarchie.

### 2. Imports inter-apps via `settings.AUTH_USER_MODEL`

Jamais d'import direct de `User` depuis `apps.accounts.models` dans une
autre app. Toujours :

```python
from django.conf import settings

class Project(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, ...)
```

### 3. Source de vérité métier dans les serializers, pas dans les views

Les validations + les transformations sont dans `serializers.py`. Les
views sont minces — elles ne font que les autorisations et l'invocation.

```python
# ✅ Bon
class RenderCreateSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        # Vérif quota
        ...

# ❌ Mauvais
class RenderListCreateView(APIView):
    def post(self, request):
        if request.user.stats.renders_this_month >= ...:  # ne fais pas ça
            ...
```

### 4. Signaux pour la synchronisation automatique

Les compteurs (`UserStats.total_projects`, `storage_used_bytes`,
`renders_this_month`) sont mis à jour par `post_save` / `post_delete`
signaux, pas par les views.

```python
@receiver(post_save, sender=ImportedModel)
def increment_storage_on_model_save(sender, instance, created, **kwargs):
    if created:
        UserStats.objects.filter(user=instance.project.user).update(
            storage_used_bytes=F('storage_used_bytes') + instance.file_size_bytes
        )
```

### 5. Désactivation gracieuse des intégrations externes

Tous les providers (Gemini, Stripe, OAuth) ont un check `is_configured()`
qui renvoie `False` si la clé n'est pas définie. Les endpoints qui en
dépendent renvoient alors **503 Service Unavailable** au lieu de planter.

```python
if not stripe_client.is_configured():
    return Response(
        {'detail': "Stripe n'est pas configuré.", 'code': 'stripe_unavailable'},
        status=503,
    )
```

## Patterns récurrents

### Pipeline async via Celery

```
POST /renders/         ←  202 Accepted + render(pending)
  │
  └─► generate_render.delay(id)   [enqueue Redis]
                  │
                  ▼
        celery worker             ← pickup
                  │
                  ▼
        provider.generate(...)     ← appel Gemini
                  │
                  ▼
        upload MinIO + Render(done, result_url)
                  │
                  ▼
GET /renders/{id}      ←  polling 2s côté client
```

Bénéfices :
- Pas de blocage HTTP pendant 30s
- Retry automatique sur erreur transitoire
- Scaling horizontal trivial (ajouter des workers)
- Future-proof pour vidéo, 3D, etc.

### Authentification JWT avec rotation

- `access_token` 15 min
- `refresh_token` 7 jours, rotation activée
- Blacklist via `simplejwt.token_blacklist`
- Sessions trackées par JWT JTI (révocation par device)

### Storage S3-compatible

```python
# Lecture (Django → MinIO direct via réseau Docker)
storage.save('renders/outputs/xxx.png', file)

# Écriture par le client (presigned URL)
url = generate_upload_url(key, content_type)
# → URL signée avec host PUBLIC (cdn.vizhome.fr)
# → client PUT directement sur MinIO
```

**Deux clients boto3** dans `apps/projects/presigned.py` :
- `get_internal_client()` — `http://minio:9000` pour les ops server-side
- `get_public_client()` — `http://localhost:9000` pour signer les URLs
  utilisables depuis le browser

### Multi-provider IA

```python
# apps/renders/providers/base.py
class BaseProvider(ABC):
    @abstractmethod
    def generate(self, prompt, output_type, input_image_bytes, style_hint) -> GenerationResult:
        ...

# apps/renders/providers/registry.py
_PROVIDERS = {'gemini': GeminiProvider}

# Ajouter un provider = nouvelle classe + enregistrement registry
```

## Choix techniques

### Pourquoi Celery plutôt que Django async ?

La génération IA prend 5-30 secondes. Tenir une connexion HTTP ouverte :
- Bloque un worker Gunicorn pour rien
- Rate-limit l'utilisateur s'il rafraîchit
- Empêche les retries transparents

Celery permet un **202 immédiat** + polling côté client. Pattern
scalable, identique pour les futurs jobs (vidéo, 3D, batch).

### Pourquoi MinIO plutôt que cloud S3 ?

- Gratuit, open-source, API 100% S3-compatible
- Migration vers AWS S3 / Cloudflare R2 / Backblaze B2 sans changer le code
- Console web pour browser les fichiers en dev
- Pas de coûts egress
- Self-hostable sur ton serveur en prod

### Pourquoi dj-stripe plutôt qu'une intégration manuelle ?

dj-stripe synchronise automatiquement les objets Stripe (Customer,
Subscription, Invoice, PaymentMethod) en DB via webhooks. On évite :
- Réinventer le data model Stripe
- Implémenter la déduplication des webhooks
- Gérer manuellement les retries de sync

On consomme directement les models Django et on hook notre logique via
`@djstripe_receiver('customer.subscription.created')`.

### Pourquoi presigned URLs pour les uploads ?

Un modèle 3D peut peser plusieurs Go. Le faire transiter par Django :
- Bloquerait 4 Go en RAM pendant l'upload
- Bloquerait un worker Gunicorn pendant 30s
- Imposerait une limite max dans la config Nginx/Gunicorn

Avec presigned URL, le navigateur PUT directement vers MinIO. Django ne
voit que les métadonnées via `HEAD object`.

### Bootstrap idempotent + verrou Redis (zéro-commande au deploy)

L'entrypoint Docker du container `api` lance `python manage.py bootstrap`
avant de démarrer Gunicorn. Cette commande orchestre toutes les étapes de
boot du backend :

1. `migrate` (applique les migrations en attente)
2. `collectstatic` (si `STATIC_ROOT` défini)
3. `compilemessages` (si dossier `locale/` présent)
4. `seed_forum_categories` (idempotent)
5. `setup_stripe_products` (si Stripe configuré)
6. `setup_webhook_endpoint` (idem)

**Multi-replica safety** : un verrou Redis (`vizhome:bootstrap:lock`, TTL
5 min) garantit qu'**une seule instance** lance le bootstrap quand on scale
horizontalement. Les autres replicas attendent (max `--wait-for-lock` sec)
puis exec directement Gunicorn. Le verrou identifie son détenteur par
`pid:<pid>:host:<hostname>` pour éviter de relâcher un verrou expiré qui a
été repris par un autre process.

Pour les workers Celery, on passe `BOOTSTRAP_SKIP=1` : ils ne tournent
aucune étape (l'API s'en charge) et exec directement `celery worker`.

### Hardening API : défense en profondeur

Sécurité organisée en **3 couches concentriques** :

1. **Traefik** (gateway) : security-headers, compression, rate-limit global
   (100 req/s/IP), HSTS preload, TLS 1.3, redirect www→apex.
2. **Django** (app) : `SECURE_*` settings (HSTS 1 an, COOP same-origin,
   Referrer-Policy strict-origin-when-cross-origin), cookies Secure/HttpOnly/
   SameSite=Lax, CSRF_TRUSTED_ORIGINS env-driven, **CSP via django-csp**
   (allowlist explicite : self, Stripe, OAuth providers, jsdelivr pour Swagger).
3. **DRF throttling** par scope :
    - Auth : `register` 5/h, `forgot-password` 3/h, `login` 20/min
    - Contact form public : `contact` 5/h
    - **Renders IA** : `render-create` 20/h/user (coûteux)
    - **Forum écriture** : `forum-write` 30/min/user (anti-flood)
    - **Tickets support** : `support-create` 10/h/user

Les classes de throttle sont dans `apps/core/throttling.py` et appliquées
via `get_throttles()` qui ne s'active **que sur les méthodes POST** (les GET
des listings restent sous le throttle `user` global à 120/min).

Validation upload presigned MinIO renforcée
(`PresignedUploadRequestSerializer`) :
* Extension whitelist (`.glb .gltf .obj .fbx .stl`)
* Filename sanitisé (refuse path traversal `../`, `/`, `\`, control chars,
  fichiers cachés `.foo`)
* Taille max **100 MB** par fichier (au-delà → multipart upload)
* Cohérence content-type ↔ extension (refuse `text/html` ou
  `application/javascript` sur un `.glb`, normalise les types incohérents
  non malveillants en `application/octet-stream`)

CI : **bandit** scan SAST (résultats SARIF dans GitHub Code Scanning) +
**pip-audit** sur `requirements.txt` via le service OSV (en plus de Trivy
sur l'image Docker et Dependency Review sur les PRs).

### Reverse proxy Traefik (prod)

Traefik fait office de gateway HTTPS unique pour tout l'écosystème :
* TLS auto via Let's Encrypt (HTTP-01 + TLS-ALPN-01 challenges)
* HTTP/3 (QUIC) en plus de HTTP/2 et HTTP/1.1
* Redirection 80 → 443 automatique
* Middlewares globaux appliqués via labels Docker :
    * `security-headers` (HSTS preload, COOP, CORP, frame-deny)
    * `compress` (Brotli + gzip négociés)
    * `rate-limit-global` (100 req/s, burst 200)
* Métriques Prometheus exposées sur port interne `8082`
* Dashboard sécurisé par Basic Auth sur `traefik.vizhome.fr`

Deux networks Docker :
* `vizhome_proxy` (external) : Traefik + services exposés (api, minio,
  frontend Nuxt qui vit dans le repo séparé)
* `vizhome_internal` (bridge) : Postgres, Redis, Celery workers, MinIO
  côté communication interne

La config dynamique (`traefik/dynamic/*.yml`) est hot-reloadée — pas besoin
de restart Traefik pour ajuster les middlewares ou les options TLS.

## Tests : structure et conventions

- **pytest** avec `pytest-django`
- Fixtures partagées dans `apps/<nom>/tests/conftest.py`
- Authenticated client via `auth_client` fixture (JWT pré-injecté)
- Mocks systématiques pour les appels externes (Stripe, Gemini, OAuth)

```python
@pytest.fixture
def auth_client(api_client, user):
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return api_client
```

## Settings split

```
config/settings/
├── base.py    — commun à tous les environnements
├── dev.py     — DEBUG, CORS permissif, email console
├── prod.py    — HSTS, Sentry, email SMTP, cookies secure
└── test.py    — FileSystem storage (pas MinIO), cache LocMem
```

Sélection via `DJANGO_SETTINGS_MODULE` env var (défaut : `config.settings.dev`).
