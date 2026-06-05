"""Fixtures pytest pour l'app projects."""

from __future__ import annotations


import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.projects.models import Project


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(
        email="projects@example.fr",
        password="Test1234!",
        first_name="Project",
        last_name="User",
    )


@pytest.fixture
def auth_client(api_client: APIClient, user: User) -> APIClient:
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client


@pytest.fixture
def project(user) -> Project:
    return Project.objects.create(user=user, title="Mon projet test")


@pytest.fixture
def fake_glb() -> SimpleUploadedFile:
    """Fichier GLB factice (4 octets, suffit pour les validations)."""
    return SimpleUploadedFile("cube.glb", b"glTF", content_type="model/gltf-binary")


@pytest.fixture
def fake_obj() -> SimpleUploadedFile:
    content = b"# OBJ test\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
    return SimpleUploadedFile("cube.obj", content, content_type="text/plain")
