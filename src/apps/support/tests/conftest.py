"""Fixtures partagées pour les tests support."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.support.models import SupportTicket


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(
        email='alice@example.com', password='S3cure!pass', first_name='Alice',
    )


@pytest.fixture
def other_user(db) -> User:
    return User.objects.create_user(
        email='bob@example.com', password='S3cure!pass', first_name='Bob',
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
def other_client(api_client: APIClient, other_user: User) -> APIClient:
    api_client.force_authenticate(user=other_user)
    return api_client


@pytest.fixture
def staff_client(api_client: APIClient, staff_user: User) -> APIClient:
    api_client.force_authenticate(user=staff_user)
    return api_client


@pytest.fixture
def ticket(db, user: User) -> SupportTicket:
    """Ticket de base avec 1 message initial."""
    from apps.support.models import SupportMessage
    t = SupportTicket.objects.create(
        user=user,
        subject='Mon rendu reste bloqué',
        category=SupportTicket.Category.TECHNICAL,
        priority=SupportTicket.Priority.HIGH,
    )
    SupportMessage.objects.create(
        ticket=t, author=user, from_staff=False,
        body='Le rendu #42 est toujours en pending depuis 1h.',
    )
    return t
