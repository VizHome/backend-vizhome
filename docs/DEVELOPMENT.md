# Développement — backend-vizhome

Workflow quotidien pour développer sur le backend Django.

## Démarrer la stack

```bash
docker compose up -d              # postgres + redis + minio + pgweb + api + celery
docker compose logs -f api        # logs Django en live
docker compose logs -f celery     # logs worker en live
docker compose ps                 # statut des services
```

**Services exposés en dev** :
- `http://localhost:8000` — API Django
- `http://localhost:8000/admin/` — Django admin (back-office classique)
- `http://localhost:8081` — **pgweb** : UI moderne pour browse/query Postgres
  (auto-connecté via `PGWEB_DATABASE_URL`, aucune auth — local-only).
  Si pull en échec (`EOF` sur cloudfront), retry plus tard ou switche vers
  `adminer` (bloc commenté dans `docker-compose.yml`, port 8082).
- `http://localhost:9000` / `9001` — MinIO API / Console
- `http://localhost:8025` — Mailpit (mails sortants en dev)

## Commandes Django via Docker

Comme Django tourne dans le container `api`, on préfixe toutes les
commandes par `docker compose exec api` :

```bash
# Migrations
docker compose exec api python manage.py makemigrations
docker compose exec api python manage.py migrate

# Shell Django (avec autoload des models)
docker compose exec api python manage.py shell

# Créer un superuser (pour /admin/)
docker compose exec api python manage.py createsuperuser

# Lancer un script management custom
docker compose exec api python manage.py setup_stripe_products
docker compose exec api python manage.py reset_monthly_counters

# Bootstrap idempotent — orchestre TOUS les setups en une commande
# (migrate + collectstatic + Stripe + seed forum + i18n)
docker compose exec api python manage.py bootstrap
docker compose exec api python manage.py bootstrap --skip-stripe   # sans Stripe
docker compose exec api python manage.py bootstrap --only migrate  # juste migrate
```

> En prod, l'entrypoint Docker lance automatiquement `bootstrap` au
> démarrage du container `api`. **Tu n'as donc rien à exécuter à la main**
> après un `docker compose up -d`. En dev, c'est aussi pratique de lancer
> `bootstrap` après un `git pull` plutôt que de te rappeler de chaque
> commande individuelle.

## Tests

```bash
# Tous (~114 tests, ~30s)
docker compose exec api pytest

# Par app
docker compose exec api pytest apps/accounts
docker compose exec api pytest apps/renders/tests/test_views.py

# Par mot-clé
docker compose exec api pytest -k oauth
docker compose exec api pytest -k "not test_slow"

# Avec verbose + couleur
docker compose exec api pytest -v --color=yes

# Avec coverage
docker compose exec api pytest --cov=apps --cov-report=term-missing

# Arrêt au 1er fail (debug rapide)
docker compose exec api pytest -x

# Re-lance uniquement les fails du run précédent
docker compose exec api pytest --lf
```

## Lint & format

```bash
# Vérifier (ne modifie rien)
docker compose exec api ruff check src/
docker compose exec api ruff format --check src/

# Corriger automatiquement
docker compose exec api ruff check --fix src/
docker compose exec api ruff format src/

# Type checking (optionnel, lent)
docker compose exec api mypy src/
```

Configuration : voir [pyproject.toml](../pyproject.toml).

## Workflow type : ajouter un endpoint

::: details Étapes recommandées

1. **Modèle** dans `apps/<app>/models.py` si nouveau
2. **Migration** : `makemigrations` + `migrate`
3. **Serializer** dans `apps/<app>/serializers.py`
4. **View** dans `apps/<app>/views.py` (préférer les `generics.*` ou `APIView`)
5. **URL** dans `apps/<app>/urls.py` puis include dans `config/urls.py`
6. **Permissions** : ajouter au serializer ou via `permission_classes`
7. **Tests** dans `apps/<app>/tests/test_views.py`
8. **OpenAPI** : automatique via `drf-spectacular`, vérifier sur `/api/docs/`
:::

## Debug avec ipdb

```python
# Dans n'importe quel fichier Python
import ipdb; ipdb.set_trace()
```

Puis lancer le serveur en mode interactif :

```bash
# Ne pas utiliser docker compose up -d — il faut un TTY attaché
docker compose run --service-ports --rm api python manage.py runserver 0.0.0.0:8000
```

## Recharger l'env après un changement de `.env`

```bash
# `docker compose restart` NE relit PAS .env !
docker compose up -d --force-recreate api celery
```

## Inspecter Postgres

```bash
# Shell Postgres
docker compose exec postgres psql -U vizhome -d vizhome

# Backup local
docker compose exec postgres pg_dump -U vizhome vizhome > backup.sql

# Restore
cat backup.sql | docker compose exec -T postgres psql -U vizhome -d vizhome
```

## Inspecter MinIO

- Console web : http://localhost:9001 (`vizhome` / `vizhome_minio_dev_password`)
- CLI (depuis un container) :
  ```bash
  docker compose exec minio mc alias set local http://localhost:9000 vizhome vizhome_minio_dev_password
  docker compose exec minio mc ls local/vizhome-media
  ```

## Inspecter les emails (MailPit)

Tous les emails envoyés par Django en dev (reset password, notifications,
etc.) sont catchés par [MailPit](https://mailpit.axllent.org/) — aucun
vrai envoi sur internet.

- **UI web** : http://localhost:8025
- **SMTP host** : `mailpit:1025` (depuis le réseau Docker)

Tu peux tester un envoi rapide depuis le shell Django :

```bash
docker compose exec api python manage.py shell -c "
from django.core.mail import send_mail
send_mail('Test MailPit', 'Hello', 'dev@vizhome.local', ['user@example.com'])
"
# → l'email apparaît immédiatement dans http://localhost:8025
```

Pour revenir aux logs console (sans MailPit), set dans `.env` :
```bash
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

## Inspecter Redis

```bash
docker compose exec redis redis-cli

# Lister les clés
redis> KEYS *
redis> KEYS celery-task-*
redis> KEYS 2fa_challenge:*

# Voir le contenu d'une clé
redis> GET <key>
```

## Forum : nettoyage des images orphelines

Chaque image uploadée via le bouton 🖼️ ou paste dans l'éditeur forum
crée un `ForumUpload(used=False)`. Quand un Topic ou Reply est sauvegardé,
le signal `post_save` parse le HTML et passe à `used=True` les uploads
dont la `key` apparaît en `<img src>`.

**Si l'user ferme l'onglet sans publier**, les `ForumUpload(used=False)`
restent + leurs fichiers MinIO. La commande de cleanup les supprime
après une période de grâce :

```bash
# Manuel (dry-run pour voir sans rien supprimer)
docker compose exec api python manage.py cleanup_forum_orphan_uploads --dry-run

# Vraiment supprimer (orphelins > 24h)
docker compose exec api python manage.py cleanup_forum_orphan_uploads

# Période de grâce custom
docker compose exec api python manage.py cleanup_forum_orphan_uploads --hours 12
```

**Activer en tâche planifiée (recommandé prod)** :

1. Django admin → `Periodic Tasks` (django-celery-beat) → **Add**
2. Name : `Forum cleanup orphan uploads`
3. Task (registered) : `forum.cleanup_orphan_uploads`
4. Crontab schedule : `0 3 * * *` (3h du matin tous les jours)
5. Enabled ✓ → Save

À ce moment Celery beat lance la task chaque nuit. Vérifier dans
`docker compose logs celery` qu'elle tourne bien.

⚠️ Une fois `used=True`, un upload n'est JAMAIS supprimé par ce
cleanup, même si le post qui le référence est ensuite supprimé.
Pour un vrai garbage collector avec ref-counting, ajouter un compteur
sur `ForumUpload` + signal `post_save (update)` + `post_delete`.

## Stripe : webhook en local (dj-stripe sync)

Sans webhook, **Stripe ne notifie pas ton backend** des paiements/abonnements
réussis → `User.plan` reste sur l'ancienne valeur, et aucune `Invoice`
n'apparaît dans la DB. Les pages `/account/billing` et `/admin/billing`
montrent un état figé.

Le pipeline est déjà câblé côté backend (`apps/billing/handlers.py` écoute
`customer.subscription.created/updated/deleted`). Il suffit que **Stripe CLI
tourne** pour forwarder les events vers ton localhost.

### Setup en 4 étapes

```bash
# 1. Installer Stripe CLI une fois :
# Windows (winget) :
winget install stripe.stripe-cli
# Mac :
brew install stripe/stripe-cli/stripe
# Linux : voir https://docs.stripe.com/stripe-cli

# 2. Login (ouvre un navigateur pour autoriser le CLI)
stripe login

# 3. Démarrer le forward (garde ce terminal ouvert pendant tes tests)
stripe listen --forward-to localhost:8000/webhooks/stripe/  # ⚠️ slash FINAL obligatoire
```

Le CLI affiche au démarrage :

```
> Ready! Your webhook signing secret is whsec_xxxxxxxxxxxxxxxxx (^C to quit)
```

```bash
# 4. Copier ce whsec_xxx dans .env :
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxx

# Puis recréer le container pour que Django reload .env
docker compose up -d --force-recreate api
```

### Vérifier que ça marche

Dans le terminal `stripe listen`, chaque paiement / changement d'abonnement
affichera une ligne `--> customer.subscription.updated [evt_xxx]` puis
`<- [200 OK] /webhooks/stripe/`. Côté `docker compose logs api`, tu verras
`INFO User foo@bar.com → plan pro`.

Pour forcer un event de test sans passer par Stripe Checkout :

```bash
stripe trigger customer.subscription.created
```

### Pièges

- **Ne réutilise pas le même `whsec_` entre deux sessions** : à chaque
  `stripe login` puis `stripe listen`, le CLI peut régénérer le secret
  → updater `.env` à chaque session devient pénible. Astuce : crée un
  **webhook endpoint permanent** dans le dashboard Stripe test
  (`https://dashboard.stripe.com/test/webhooks`) pointant vers ton ngrok/tunnel,
  son `whsec_` ne change jamais.

- **Le webhook secret du `.env.example` (`whsec_placeholder`) est invalide**
  → Django acceptera l'event mais dj-stripe le rejettera silencieusement.
  Si tes events `200 OK` arrivent mais `User.plan` ne change pas, vérifie
  d'abord le secret.

## Snapshot quotidien des métriques admin (Phase 3)

Le panel admin garde un historique long-terme via la table
`AdminDailySnapshot` (1 ligne par jour, payload = overview consolidé).

```bash
# Manuel (à lancer une première fois pour valider)
docker compose exec api python manage.py snapshot_admin_metrics

# Pour une date spécifique (ex: rattraper hier)
docker compose exec api python manage.py snapshot_admin_metrics --date 2026-05-31
```

**Activer en tâche planifiée (recommandé prod)** :

1. Django admin → `Periodic Tasks` (django-celery-beat) → **Add**
2. Name : `Admin daily snapshot`
3. Task (registered) : `admin_panel.snapshot_metrics`
4. Crontab schedule : `5 0 * * *` (00h05 UTC tous les jours — laisse
   passer minuit pour capturer la veille complète)
5. Enabled ✓ → Save

Vérifier dans `docker compose logs celery` qu'elle tourne. Les snapshots
sont consultables dans `Django admin → AdminDailySnapshot` ou via une
query Postgres directe (`SELECT date, payload->'users' FROM ...`).

## Reset complet de la DB

```bash
# Détruit toutes les données ! À utiliser uniquement en dev.
docker compose down -v
docker compose up -d
```

## Mise à jour des dépendances

```bash
# Éditer requirements.txt → ajouter / modifier une ligne
# Puis rebuild :
docker compose build api celery
docker compose up -d --force-recreate api celery
```

## OpenAPI auto-doc

À chaque changement de view / serializer, le schéma OpenAPI se
régénère automatiquement. Visualiser :

- Swagger UI : http://localhost:8000/api/docs/
- ReDoc : http://localhost:8000/api/redoc/
- YAML brut : http://localhost:8000/api/schema/

## Tester l'API avec Bruno

Une collection [Bruno](https://www.usebruno.com/) prête à l'emploi est
dans [`../bruno/`](../bruno/) — 57 requêtes couvrant les 48 endpoints,
groupées en 6 dossiers (`01-Health`, `02-Auth`, `03-Me`, `04-Projects`,
`05-Renders`, `06-Billing`).

### Démarrage

1. **Installer Bruno** : https://www.usebruno.com/downloads (desktop)
2. **Open Collection** → sélectionner `backend-vizhome/bruno/`
3. Choisir l'environnement **Local** (en haut à droite)
4. Lancer `01-Health > Readiness` pour vérifier que le backend répond

### Workflow conseillé

Les requêtes sont ordonnées (`seq:`) pour pouvoir être exécutées dans
l'ordre. Le chaînage des tokens et IDs est automatique via des scripts
`post-response` :

```
Register      → stocke accessToken, refreshToken, userId
Create Project → stocke projectId
Get Presigned URL → stocke presignedKey + presignedUploadUrl
Confirm Upload   → stocke modelId
Create Render    → stocke renderId (poll Get Render jusqu'à status=done)
```

Tu peux aussi lancer toute la collection en une fois (Run → Run All)
pour un smoke test complet — chaque requête a un bloc `tests {}` qui
vérifie le status code et la shape de la réponse.

### Quand utiliser Bruno vs Swagger UI

| Cas d'usage | Outil |
|---|---|
| Explorer un endpoint inconnu | **Swagger UI** (`/api/docs/`) |
| Tester un flow complet (register → projet → render) | **Bruno** |
| Reproduire un bug avec un payload précis | **Bruno** (sauvegardable + versionable) |
| Vérifier qu'une PR n'a rien cassé | **Bruno** (Run All) |
| Partager une requête avec un collègue | **Bruno** (commit dans git) |

Détail complet : [`bruno/README.md`](../bruno/README.md).

Pour customiser un endpoint :

```python
from drf_spectacular.utils import extend_schema

@extend_schema(
    summary="Crée un projet",
    tags=["Projets"],
    examples=[...]
)
class ProjectListCreateView(generics.ListCreateAPIView):
    ...
```

## Conseils

- **Petits commits atomiques** — 1 feature ou 1 fix par commit
- **Pas de migration manuelle** — toujours `makemigrations` qui détecte
  le diff entre les models et le state migrations
- **Tests pour chaque nouvelle feature** — viser couverture > 80% sur
  `apps/`
- **Variables d'env dans `.env`, pas hardcoded** — utiliser
  `env('NOM', default=...)` dans `base.py`
- **Avant un PR** :
  ```bash
  docker compose exec api ruff check src/
  docker compose exec api ruff format src/
  docker compose exec api pytest
  ```
