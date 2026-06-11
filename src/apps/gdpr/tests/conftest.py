"""Fixtures pytest pour l'app gdpr."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(
        email='gdpr-user@example.fr',
        password='Test1234!',
        first_name='Gdpr',
        last_name='User',
    )


@pytest.fixture
def other_user(db) -> User:
    return User.objects.create_user(
        email='other@example.fr',
        password='Test1234!',
        first_name='Other',
        last_name='Person',
    )


def _build_auth_client(api_client: APIClient, user: User) -> APIClient:
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return api_client


@pytest.fixture
def auth_client(api_client: APIClient, user: User) -> APIClient:
    return _build_auth_client(api_client, user)


@pytest.fixture
def other_auth_client(user: User, other_user: User) -> APIClient:
    """Client authentifié comme `other_user` (pour les tests IDOR)."""
    return _build_auth_client(APIClient(), other_user)
