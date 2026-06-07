"""Scenarios de load test Locust pour le backend VizHome.

Cinq UserBehaviors :
- `HealthCheckUser`   : ping /health/live (sanity check Locust + reverse proxy)
- `AnonymousUser`     : visite landing public (categories forum, contact info)
- `AuthenticatedUser` : flow utilisateur connecte (login + listing API)
- `RenderingUser`     : flow rendu IA (login + POST /renders, le provider Gemini
                        est protege par le throttle backend, donc on ne tape
                        pas reellement Google)
- `ForumReader`       : lecteur public du forum (categories + topics pagines)

Lancer en local : `make bench-local` (UI Locust sur http://localhost:8089).
Lancer en headless : `make bench-headless` (50 users, 2 min, sortie texte).

Les fixtures users sont volontairement minimales : pour un test de charge
realiste, prevoir un seed de N comptes en CI (`manage.py seed_bench_users`)
et override `USER_EMAIL`/`USER_PASSWORD` via variables d'env.
"""

from __future__ import annotations

import os
import random
from typing import ClassVar

from locust import HttpUser, between, task

# Constantes : ne pas dupliquer dans chaque User
DEFAULT_HOST = os.environ.get('LOCUST_HOST', 'http://localhost:8000')
USER_EMAIL = os.environ.get('BENCH_USER_EMAIL', 'bench@vizhome.test')
USER_PASSWORD = os.environ.get('BENCH_USER_PASSWORD', 'BenchPassw0rd!')

# Pondering : weight relatif des taches dans une meme classe User
WEIGHT_LIST = 5
WEIGHT_DETAIL = 3
WEIGHT_CREATE = 1


def _login(client, email: str, password: str) -> str | None:
    """Authentifie un user via /api/v1/auth/login et retourne l'access token.

    Retourne None si le login echoue (compte de bench non seeded). On log
    une erreur Locust sans faire planter le scenario : ca permet de tourner
    en mode "dry run" meme sans seeds.
    """
    resp = client.post(
        '/api/v1/auth/login',
        json={'email': email, 'password': password},
        name='POST /auth/login',
        catch_response=True,
    )
    if resp.status_code != 200:
        resp.failure(f'Login KO ({resp.status_code})')
        return None
    data = resp.json()
    return data.get('access') or data.get('access_token')


class HealthCheckUser(HttpUser):
    """User minimal qui ne tape que /health/live.

    Sert de sanity check : si Locust ne voit meme pas l'endpoint healthcheck,
    inutile d'aller plus loin (probleme de host, de port, de reverse proxy).
    """

    host: ClassVar[str] = DEFAULT_HOST
    wait_time = between(1, 3)

    @task
    def liveness(self) -> None:
        """GET /health/live : doit repondre en < 50 ms p95."""
        self.client.get('/health/live', name='GET /health/live')


class AnonymousUser(HttpUser):
    """Visiteur curieux non authentifie qui parcourt les pages publiques.

    Endpoints touches : catalogue forum, schema OpenAPI (parfois inspecte
    par les scrappers), readiness probe. Pas de /api/v1/auth/login ici, on
    reste en non-authentifie.
    """

    host: ClassVar[str] = DEFAULT_HOST
    wait_time = between(2, 5)

    @task(weight=WEIGHT_LIST)
    def browse_forum_categories(self) -> None:
        """GET /api/v1/forum/categories : liste publique des cats."""
        self.client.get('/api/v1/forum/categories', name='GET /forum/categories (anon)')

    @task(weight=WEIGHT_DETAIL)
    def view_openapi_schema(self) -> None:
        """GET /api/schema/ : pas critique mais souvent crawle par bots."""
        self.client.get('/api/schema/', name='GET /api/schema')

    @task(weight=1)
    def readiness_probe(self) -> None:
        """GET /health/ready : check DB + Redis. Peut etre plus lourd."""
        self.client.get('/health/ready', name='GET /health/ready')


class AuthenticatedUser(HttpUser):
    """User connecte qui parcourt son dashboard.

    Scenario realiste : login, fetch /me/, list projects, list renders.
    C'est la session typique apres ouverture de l'app frontend.
    """

    host: ClassVar[str] = DEFAULT_HOST
    wait_time = between(1, 4)
    access_token: str | None = None

    def on_start(self) -> None:
        """Authentifie ce user simule au demarrage de la session Locust."""
        self.access_token = _login(self.client, USER_EMAIL, USER_PASSWORD)
        if self.access_token:
            self.client.headers.update({'Authorization': f'Bearer {self.access_token}'})

    @task(weight=WEIGHT_LIST)
    def list_projects(self) -> None:
        """GET /api/v1/projects : listing paginated des projets du user."""
        self.client.get('/api/v1/projects', name='GET /projects')

    @task(weight=WEIGHT_LIST)
    def list_renders(self) -> None:
        """GET /api/v1/renders : galerie des rendus du user."""
        self.client.get('/api/v1/renders', name='GET /renders')

    @task(weight=WEIGHT_DETAIL)
    def fetch_me(self) -> None:
        """GET /api/v1/me/ : profile + stats + preferences (nested)."""
        self.client.get('/api/v1/me/', name='GET /me')

    @task(weight=1)
    def fetch_preferences(self) -> None:
        """GET /api/v1/me/preferences : juste les preferences."""
        self.client.get('/api/v1/me/preferences', name='GET /me/preferences')


class RenderingUser(HttpUser):
    """User qui lance des rendus IA (les plus couteux cote backend).

    Le provider Gemini est protege par un throttle `RenderCreateThrottle`
    (20/h en defaut). Au-dela, le backend retourne 429 avant meme d'appeler
    Google : c'est ce qu'on veut mesurer ici, le cout du pipeline DRF +
    validation + signal Celery.

    En CI, le worker Celery doit etre mocke (mode `CELERY_TASK_ALWAYS_EAGER`)
    ou le provider doit retourner 503 (compatible avec le pattern graceful
    fallback decrit dans CLAUDE.md).
    """

    host: ClassVar[str] = DEFAULT_HOST
    wait_time = between(3, 5)
    access_token: str | None = None

    def on_start(self) -> None:
        """Login et stocke le token sur l'instance."""
        self.access_token = _login(self.client, USER_EMAIL, USER_PASSWORD)
        if self.access_token:
            self.client.headers.update({'Authorization': f'Bearer {self.access_token}'})

    @task(weight=WEIGHT_CREATE)
    def create_prompt_render(self) -> None:
        """POST /api/v1/renders : declenche un rendu IA en mode prompt.

        On accepte 202 (ok, mis en queue Celery), 429 (throttle hit) ou
        503 (provider non configure). Tout autre code = anomalie.
        """
        prompts = [
            'Une maison moderne au bord de la mer',
            'Salon scandinave avec cheminee',
            'Cuisine industrielle vue de jour',
        ]
        payload = {
            'source': 'prompt',
            'output_type': 'image_2d',
            'prompt': random.choice(prompts),
        }
        with self.client.post(
            '/api/v1/renders',
            json=payload,
            name='POST /renders (prompt)',
            catch_response=True,
        ) as resp:
            if resp.status_code in (202, 429, 503):
                resp.success()
            else:
                resp.failure(f'Status inattendu {resp.status_code}')

    @task(weight=WEIGHT_LIST)
    def list_render_history(self) -> None:
        """GET /api/v1/renders/history : 10 derniers prompts (autocomplete)."""
        self.client.get('/api/v1/renders/history', name='GET /renders/history')


class ForumReader(HttpUser):
    """Lecteur du forum public.

    Le forum est en lecture publique (cf. urls.py forum app). On simule un
    visiteur qui scrolle la liste, ouvre 1-2 topics, regarde les replies.
    """

    host: ClassVar[str] = DEFAULT_HOST
    wait_time = between(1, 4)

    @task(weight=WEIGHT_LIST)
    def list_categories(self) -> None:
        """GET /api/v1/forum/categories : peu de cats, doit etre rapide."""
        self.client.get('/api/v1/forum/categories', name='GET /forum/categories (reader)')

    @task(weight=WEIGHT_LIST)
    def list_topics_page1(self) -> None:
        """GET /api/v1/forum/topics : 1ere page paginated."""
        self.client.get('/api/v1/forum/topics', name='GET /forum/topics')

    @task(weight=WEIGHT_DETAIL)
    def list_topics_page2(self) -> None:
        """GET /api/v1/forum/topics?page=2 : test la pagination DRF."""
        self.client.get('/api/v1/forum/topics?page=2', name='GET /forum/topics?page=2')

    @task(weight=1)
    def list_topics_by_category(self) -> None:
        """GET /api/v1/forum/topics?category=support : filtre indexed."""
        self.client.get(
            '/api/v1/forum/topics?category=support',
            name='GET /forum/topics?category=...',
        )
