"""Fixtures pytest pour billing."""
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
        email='billing@example.fr', password='Test1234!',
        first_name='Bill', last_name='Ing',
    )


@pytest.fixture
def auth_client(api_client, user) -> APIClient:
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return api_client
