# Développement — backend-vizhome

Workflow quotidien pour développer sur le backend Django.

## Démarrer la stack

```bash
docker compose up -d              # postgres + redis + minio + api + celery
docker compose logs -f api        # logs Django en live
docker compose logs -f celery     # logs worker en live
docker compose ps                 # statut des services
```

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
```

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
