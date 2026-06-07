"""Endpoint Server-Sent Events (SSE) pour le suivi temps réel d'un Render.

Remplace le polling frontend 2s/3min : le client ouvre une connexion HTTP
persistante et reçoit un événement à chaque changement de statut du Render.

Pourquoi pas Django Channels / Redis pub-sub ?
------------------------------------------------
Le pipeline Celery écrit déjà l'état dans Postgres ; un poll DB côté serveur
(toutes les 1.5s) est :
  * suffisant pour un job IA qui dure typiquement 30s à 3min,
  * trivial à wiring (aucune dépendance, pas d'event bus),
  * compatible WSGI gunicorn sync.

Limite à connaître (cf. docstring `RenderSSEView`) : chaque connexion SSE
occupe un worker gunicorn sync pendant toute sa durée. En production, basculer
sur ``gunicorn -k gthread --threads 4 --workers 4`` permet d'absorber ~16
connexions concurrentes par instance avant saturation.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator

from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.views import View
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .models import Render

logger = logging.getLogger(__name__)

# ─── Constantes ──────────────────────────────────────────────────────────────
SSE_POLL_INTERVAL_S = 1.5
SSE_MAX_DURATION_S = 300  # 5 min
SSE_HEARTBEAT_EVERY_S = 15  # commentaire SSE pour garder la connexion en vie


def _sse_event(data: dict) -> bytes:
    """Encode un dict en frame SSE ``data: <json>\\n\\n``."""
    return f'data: {json.dumps(data, separators=(",", ":"))}\n\n'.encode()


def _sse_comment(text: str) -> bytes:
    """Encode un commentaire SSE (ligne ``: ...``) servant de heartbeat."""
    return f': {text}\n\n'.encode()


class RenderSSEView(View):
    """GET ``/api/v1/renders/<pk>/events`` : flux SSE du statut d'un Render.

    Auth
    ----
    Bearer JWT lu dans l'en-tête ``Authorization`` (le polyfill côté frontend
    le passe en header HTTP standard). L'IDOR est bloqué : le render doit
    appartenir au user authentifié.

    Cycle
    -----
    * Émet un événement immédiat avec le statut courant.
    * Re-poll la DB toutes ``SSE_POLL_INTERVAL_S`` secondes, émet un nouvel
      événement si le statut change.
    * Termine dès que ``render.is_terminal`` (done | failed).
    * Garde-fou : ferme proprement après ``SSE_MAX_DURATION_S``.

    Limitation gunicorn
    -------------------
    Une connexion SSE = un worker WSGI bloqué pendant toute la durée. Avec
    le déploiement par défaut (``gunicorn --workers 4`` sync), 4 connexions
    simultanées suffisent à saturer l'instance. Recommandé en prod :
    ``gunicorn -k gthread --threads 4 --workers 4`` → ~16 connexions
    concurrentes par instance.
    """

    http_method_names = ['get']

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        # ─── Auth Bearer manuelle (View, pas DRF) ───────────────────────────
        user = self._authenticate(request)
        if user is None:
            return HttpResponse(
                status=401,
                content=json.dumps({'detail': 'Authentification requise.'}),
                content_type='application/json',
            )

        # ─── IDOR : on filtre sur user dans le queryset ─────────────────────
        try:
            render = Render.objects.only('pk', 'user_id').get(pk=pk, user=user)
        except Render.DoesNotExist:
            return HttpResponse(
                status=404,
                content=json.dumps({'detail': 'Render introuvable.'}),
                content_type='application/json',
            )

        response = StreamingHttpResponse(
            self._event_stream(render.pk),
            content_type='text/event-stream',
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'  # Nginx : ne pas bufferiser
        response['Connection'] = 'keep-alive'
        return response

    # ─── Helpers ────────────────────────────────────────────────────────────
    @staticmethod
    def _authenticate(request: HttpRequest):
        """Valide le Bearer JWT et renvoie l'utilisateur, ou ``None`` si KO."""
        header = request.META.get('HTTP_AUTHORIZATION', '')
        if not header.startswith('Bearer '):
            return None
        token_str = header.split(' ', 1)[1].strip()
        if not token_str:
            return None

        authenticator = JWTAuthentication()
        try:
            validated = authenticator.get_validated_token(token_str)
            return authenticator.get_user(validated)
        except (InvalidToken, TokenError):
            return None
        except Exception:  # pragma: no cover - filet de sécurité
            logger.exception("Erreur d'authentification SSE inattendue")
            return None

    @staticmethod
    def _event_stream(render_id: int) -> Iterator[bytes]:
        """Generator branché à ``StreamingHttpResponse``.

        Refresh le Render depuis la DB toutes ``SSE_POLL_INTERVAL_S`` et
        ne pousse un événement qu'au changement de statut, pour éviter de
        spammer le client. Ajoute un commentaire de heartbeat tous les
        ``SSE_HEARTBEAT_EVERY_S`` pour éviter que les proxies coupent
        la connexion en idle.
        """
        deadline = time.monotonic() + SSE_MAX_DURATION_S
        last_status: str | None = None
        last_heartbeat = time.monotonic()

        while time.monotonic() < deadline:
            try:
                render = Render.objects.only('pk', 'status', 'error_message', 'result_image').get(
                    pk=render_id
                )
            except Render.DoesNotExist:
                # Supprimé en cours de route, on coupe.
                yield _sse_event({'status': 'failed', 'error': 'Render supprimé.'})
                return

            if render.status != last_status:
                payload = {
                    'id': render.pk,
                    'status': render.status,
                    'is_terminal': render.is_terminal,
                }
                if render.status == Render.Status.FAILED and render.error_message:
                    payload['error'] = render.error_message
                if render.status == Render.Status.DONE and render.result_image:
                    payload['result_url'] = render.result_image.url
                yield _sse_event(payload)
                last_status = render.status

                if render.is_terminal:
                    return

            # Heartbeat (commentaire SSE) pour garder la connexion vivante
            now = time.monotonic()
            if now - last_heartbeat >= SSE_HEARTBEAT_EVERY_S:
                yield _sse_comment('keep-alive')
                last_heartbeat = now

            time.sleep(SSE_POLL_INTERVAL_S)

        # Timeout : on prévient le client qu'on coupe sans verdict.
        yield _sse_event(
            {
                'status': last_status or 'pending',
                'is_terminal': False,
                'timeout': True,
            }
        )
