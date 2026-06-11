"""Réponses personnalisées pour le verrouillage django-axes."""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from rest_framework.response import Response

_LOCKOUT_PAYLOAD = {
    'detail': (
        'Trop de tentatives échouées. Compte temporairement verrouillé. '
        'Réessayez dans quelques minutes.'
    ),
    'code': 'account_locked',
}


def api_lockout_response(request: HttpRequest, credentials: dict | None = None) -> JsonResponse:
    """Callable utilisé par django-axes (AXES_LOCKOUT_CALLABLE).

    Retourne un JsonResponse car axes appelle ce hook depuis son middleware,
    en dehors du contexte DRF — un Response DRF non rendu causerait une erreur.
    """
    return JsonResponse(_LOCKOUT_PAYLOAD, status=429)


def drf_lockout_response() -> Response:
    """Variante DRF — utilisée quand on détecte le lockout depuis une vue DRF.

    DRF se charge de la sérialisation via le renderer, donc `.data` est
    correctement exposé côté tests.
    """
    return Response(_LOCKOUT_PAYLOAD, status=429)
