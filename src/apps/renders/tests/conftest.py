"""Fixtures pytest pour l'app renders."""
from __future__ import annotations

import base64
import io

import pytest
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(
        email='render@example.fr',
        password='Test1234!',
        first_name='Render',
        last_name='User',
    )


@pytest.fixture
def auth_client(api_client: APIClient, user: User) -> APIClient:
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return api_client


@pytest.fixture
def sketch_b64() -> str:
    """Une image PNG 4x4 rouge, encodée en base64."""
    img = Image.new('RGB', (4, 4), color='red')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def fake_gemini_result():
    """Bytes PNG plausibles pour mocker un GenerationResult Gemini."""
    img = Image.new('RGB', (32, 32), color='blue')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()
