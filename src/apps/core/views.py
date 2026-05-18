"""Endpoints de healthcheck — pour Docker, load balancers, monitoring."""
from __future__ import annotations

import logging

from django.db import connection
from django.http import JsonResponse
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.request import Request

logger = logging.getLogger(__name__)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def liveness(request: Request) -> JsonResponse:
    """GET /health/live — le process Django répond."""
    return JsonResponse({'status': 'ok'})


@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def readiness(request: Request) -> JsonResponse:
    """GET /health/ready — Django + dépendances critiques (Postgres, Redis) OK.

    Utilisé par les load balancers pour décider de router le trafic vers ce
    container. Retourne 503 si l'une des deps est down.
    """
    checks: dict[str, str] = {}
    ok = True

    # Postgres
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        checks['postgres'] = 'ok'
    except Exception as e:
        logger.exception('Readiness: postgres KO')
        checks['postgres'] = f'error: {e}'
        ok = False

    # Redis (via cache)
    try:
        from django.core.cache import cache
        cache.set('_healthcheck', 'ok', timeout=5)
        if cache.get('_healthcheck') != 'ok':
            raise RuntimeError('cache write/read mismatch')
        checks['redis'] = 'ok'
    except Exception as e:
        logger.exception('Readiness: redis KO')
        checks['redis'] = f'error: {e}'
        ok = False

    status_code = 200 if ok else 503
    return JsonResponse({'status': 'ok' if ok else 'degraded', 'checks': checks}, status=status_code)
