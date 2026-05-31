"""Fixtures partagées pour les tests forum."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.forum.models import Category, Topic


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(
        email='alice@example.com', password='S3cure!pass', first_name='Alice'
    )


@pytest.fixture
def other_user(db) -> User:
    return User.objects.create_user(
        email='bob@example.com', password='S3cure!pass', first_name='Bob'
    )


@pytest.fixture
def staff_user(db) -> User:
    return User.objects.create_user(
        email='admin@example.com', password='S3cure!pass',
        first_name='Admin', is_staff=True,
    )


@pytest.fixture
def auth_client(api_client: APIClient, user: User) -> APIClient:
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def staff_client(api_client: APIClient, staff_user: User) -> APIClient:
    api_client.force_authenticate(user=staff_user)
    return api_client


@pytest.fixture
def cat_support(db) -> Category:
    return Category.objects.create(
        slug='support', name='Support', icon='help-circle', order=1,
    )


@pytest.fixture
def cat_annonces(db) -> Category:
    return Category.objects.create(
        slug='annonces', name='Annonces', icon='megaphone', order=2,
        is_admin_only=True,
    )


@pytest.fixture
def topic(db, user: User, cat_support: Category) -> Topic:
    return Topic.objects.create(
        category=cat_support, author=user,
        title='Comment importer un GLB ?',
        content='J\'ai un fichier glb mais je ne sais pas où le déposer.',
    )
