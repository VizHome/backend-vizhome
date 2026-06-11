"""Tests de l'endpoint SSE ``/api/v1/renders/<pk>/events``.

Le flux est un generator : on l'épuise manuellement pour vérifier la
séquence d'événements émis, sans laisser tourner la boucle réelle (qui
contient des ``time.sleep``).
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.renders.models import Render


def _bearer(user: User) -> str:
    """Génère un Authorization header Bearer pour ``user``."""
    refresh = RefreshToken.for_user(user)
    return f'Bearer {refresh.access_token}'


def _consume_stream(response, max_frames: int = 10) -> list[dict]:
    """Lit jusqu'à ``max_frames`` événements ``data:`` du flux SSE."""
    events: list[dict] = []
    for chunk in response.streaming_content:
        text = chunk.decode('utf-8')
        for line in text.splitlines():
            if line.startswith('data:'):
                events.append(json.loads(line[len('data:') :].strip()))
        if len(events) >= max_frames:
            break
    return events


@pytest.mark.django_db
class TestRenderSSEAuth:
    """Auth + IDOR."""

    def test_returns_401_without_bearer(self, api_client, user):
        render = Render.objects.create(user=user, source='prompt', prompt='x')
        response = api_client.get(f'/api/v1/renders/{render.pk}/events')
        assert response.status_code == 401

    def test_returns_401_with_invalid_bearer(self, api_client, user):
        render = Render.objects.create(user=user, source='prompt', prompt='x')
        response = api_client.get(
            f'/api/v1/renders/{render.pk}/events',
            HTTP_AUTHORIZATION='Bearer not-a-real-jwt',
        )
        assert response.status_code == 401

    def test_returns_404_for_other_user_render(self, api_client, user):
        """IDOR : un user ne doit pas pouvoir lire les events d'un autre."""
        other = User.objects.create_user(email='other@x.fr', password='X')
        render = Render.objects.create(user=other, source='prompt', prompt='secret')
        response = api_client.get(
            f'/api/v1/renders/{render.pk}/events',
            HTTP_AUTHORIZATION=_bearer(user),
        )
        assert response.status_code == 404

    def test_returns_404_for_unknown_render(self, api_client, user):
        response = api_client.get(
            '/api/v1/renders/99999/events',
            HTTP_AUTHORIZATION=_bearer(user),
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestRenderSSEStream:
    """Comportement du generator (mocké pour éviter ``time.sleep`` réels)."""

    def test_200_and_correct_headers_for_owner(self, api_client, user):
        render = Render.objects.create(user=user, source='prompt', prompt='x', status='done')
        # Patch sleep pour ne pas bloquer.
        with patch('apps.renders.sse.time.sleep', return_value=None):
            response = api_client.get(
                f'/api/v1/renders/{render.pk}/events',
                HTTP_AUTHORIZATION=_bearer(user),
            )
            # On force la lecture du flux pour terminer la requête
            list(response.streaming_content)

        assert response.status_code == 200
        assert response['Content-Type'].startswith('text/event-stream')
        assert response['Cache-Control'] == 'no-cache'
        assert response['X-Accel-Buffering'] == 'no'

    def test_terminates_when_status_done(self, api_client, user):
        """Si le render est déjà terminé, le flux ne doit émettre qu'un évènement."""
        render = Render.objects.create(user=user, source='prompt', prompt='x', status='done')
        with patch('apps.renders.sse.time.sleep', return_value=None):
            response = api_client.get(
                f'/api/v1/renders/{render.pk}/events',
                HTTP_AUTHORIZATION=_bearer(user),
            )
            events = _consume_stream(response)

        assert len(events) == 1
        assert events[0]['status'] == 'done'
        assert events[0]['is_terminal'] is True

    def test_emits_event_on_status_change(self, user):
        """Le générateur émet une frame à chaque transition de statut.

        On teste directement ``_event_stream`` (la logique métier), sans
        passer par le client HTTP : on remplace la chaîne
        ``Render.objects.only(...).get(pk=...)`` par un stub qui pousse
        une séquence de statuts contrôlée.
        """
        from apps.renders import sse as sse_mod

        render = Render.objects.create(user=user, source='prompt', prompt='x', status='pending')

        statuses = iter(['processing', 'done'])

        class _StubQS:
            def get(self, **kwargs):
                obj = Render.objects.get(**kwargs)
                try:
                    obj.status = next(statuses)
                except StopIteration:
                    obj.status = 'done'
                return obj

        with (
            patch('apps.renders.sse.time.sleep', return_value=None),
            patch.object(
                sse_mod.Render.objects,
                'only',
                lambda *a, **k: _StubQS(),
            ),
        ):
            frames = list(sse_mod.RenderSSEView._event_stream(render.pk))

        # Décode tous les events `data:`
        events: list[dict] = []
        for frame in frames:
            text = frame.decode('utf-8')
            for line in text.splitlines():
                if line.startswith('data:'):
                    events.append(json.loads(line[len('data:') :].strip()))

        seen = [e['status'] for e in events]
        assert 'processing' in seen
        assert 'done' in seen
        # La dernière frame est terminale
        assert events[-1]['is_terminal'] is True

    def test_includes_error_message_on_failed(self, api_client, user):
        render = Render.objects.create(
            user=user,
            source='prompt',
            prompt='x',
            status='failed',
            error_message='Quota provider dépassé',
        )
        with patch('apps.renders.sse.time.sleep', return_value=None):
            response = api_client.get(
                f'/api/v1/renders/{render.pk}/events',
                HTTP_AUTHORIZATION=_bearer(user),
            )
            events = _consume_stream(response)

        assert events[0]['status'] == 'failed'
        assert events[0]['error'] == 'Quota provider dépassé'
