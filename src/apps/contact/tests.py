"""Tests pour l'endpoint POST /api/v1/contact/."""

from __future__ import annotations

import pytest
from django.core import mail
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.contact.models import NewsletterSubscriber

pytestmark = pytest.mark.django_db


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def valid_payload() -> dict:
    return {
        'name': 'Jean Dupont',
        'email': 'jean@example.com',
        'subject': 'general',
        'message': "Bonjour, j'ai une question sur votre service VizHome.",
        'privacy_accepted': True,
        'newsletter_opt_in': False,
    }


# ─── Happy path ──────────────────────────────────────────────────────────────


def test_post_contact_sends_email(client: APIClient, valid_payload: dict) -> None:
    """Une payload valide envoie un email et répond 200."""
    url = reverse('api_v1:contact:contact')
    response = client.post(url, data=valid_payload, format='json')

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'ok': True}
    assert len(mail.outbox) == 1

    sent = mail.outbox[0]
    assert 'VizHome contact' in sent.subject
    assert 'Jean Dupont' in sent.subject
    assert valid_payload['email'] in sent.reply_to
    assert 'Bonjour' in sent.body


def test_post_contact_newsletter_optin_creates_subscriber(
    client: APIClient, valid_payload: dict
) -> None:
    """Si newsletter_opt_in=True, un NewsletterSubscriber est créé."""
    valid_payload['newsletter_opt_in'] = True
    url = reverse('api_v1:contact:contact')
    response = client.post(url, data=valid_payload, format='json')

    assert response.status_code == status.HTTP_200_OK
    assert NewsletterSubscriber.objects.filter(email=valid_payload['email']).exists()


def test_post_contact_newsletter_optin_is_idempotent(
    client: APIClient, valid_payload: dict
) -> None:
    """Deux envois avec opt-in pour le même mail ne créent qu'une entrée."""
    valid_payload['newsletter_opt_in'] = True
    url = reverse('api_v1:contact:contact')
    client.post(url, data=valid_payload, format='json')
    client.post(url, data=valid_payload, format='json')

    assert NewsletterSubscriber.objects.filter(email=valid_payload['email']).count() == 1


def test_post_contact_email_normalized_lowercase(client: APIClient, valid_payload: dict) -> None:
    """L'email du NewsletterSubscriber est stocké en lowercase."""
    valid_payload['newsletter_opt_in'] = True
    valid_payload['email'] = 'Jean.DUPONT@Example.com'
    url = reverse('api_v1:contact:contact')
    client.post(url, data=valid_payload, format='json')

    assert NewsletterSubscriber.objects.filter(email='jean.dupont@example.com').exists()


# ─── Validation ──────────────────────────────────────────────────────────────


def test_post_contact_rejects_short_message(client: APIClient, valid_payload: dict) -> None:
    """Message < 20 caractères → 400."""
    valid_payload['message'] = 'trop court'
    response = client.post(reverse('api_v1:contact:contact'), data=valid_payload, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'message' in response.json()


def test_post_contact_rejects_invalid_email(client: APIClient, valid_payload: dict) -> None:
    """Email mal formé → 400."""
    valid_payload['email'] = 'pas-un-email'
    response = client.post(reverse('api_v1:contact:contact'), data=valid_payload, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'email' in response.json()


def test_post_contact_rejects_invalid_subject(client: APIClient, valid_payload: dict) -> None:
    """Sujet hors liste autorisée → 400."""
    valid_payload['subject'] = 'spam'
    response = client.post(reverse('api_v1:contact:contact'), data=valid_payload, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_post_contact_requires_privacy_acceptance(client: APIClient, valid_payload: dict) -> None:
    """privacy_accepted=False → 400."""
    valid_payload['privacy_accepted'] = False
    response = client.post(reverse('api_v1:contact:contact'), data=valid_payload, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_post_contact_short_name_rejected(client: APIClient, valid_payload: dict) -> None:
    """Nom < 3 caractères → 400."""
    valid_payload['name'] = 'Al'
    response = client.post(reverse('api_v1:contact:contact'), data=valid_payload, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_post_contact_no_email_sent_on_invalid(client: APIClient, valid_payload: dict) -> None:
    """Une payload invalide n'envoie aucun email."""
    valid_payload['email'] = 'bad'
    client.post(reverse('api_v1:contact:contact'), data=valid_payload, format='json')
    assert len(mail.outbox) == 0
