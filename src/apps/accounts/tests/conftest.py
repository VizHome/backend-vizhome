"""Fixtures pytest partagées pour les tests d'accounts."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture(autouse=True)
def _clear_cache_and_axes(db):
    """Nettoie le cache (throttles, 2FA challenges) et les access attempts axes entre tests."""
    cache.clear()
    from axes.models import AccessAttempt, AccessLog

    AccessAttempt.objects.all().delete()
    AccessLog.objects.all().delete()
    yield
    cache.clear()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(
        email="jean@example.fr",
        password="Test1234!",
        first_name="Jean",
        last_name="Dupont",
    )


@pytest.fixture
def auth_client(api_client: APIClient, user: User) -> APIClient:
    """Client DRF authentifié avec un access token JWT valide."""
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client
