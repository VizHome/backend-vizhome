"""Tests du flow 2FA TOTP."""

from __future__ import annotations

import pyotp
import pytest
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User


def _setup_2fa(auth_client: APIClient) -> tuple[str, str]:
    """Helper : setup 2FA et retourne (secret_b32, otpauth_uri)."""
    response = auth_client.post('/api/v1/me/2fa/setup')
    assert response.status_code == 200
    return response.data['secret'], response.data['otpauth_uri']


def _totp_code(secret_b32: str) -> str:
    return pyotp.TOTP(secret_b32).now()


def _reset_totp_replay(user: User) -> None:
    """Reset le last_t pour autoriser la réutilisation du même code TOTP en tests.

    django-otp empêche normalement le replay du même code dans la fenêtre 30s.
    Pour les tests qui chainent setup → verify → use, on contourne.
    """
    TOTPDevice.objects.filter(user=user).update(last_t=-1)


@pytest.mark.django_db
class TestSetup2FA:
    def test_setup_creates_unconfirmed_device(self, auth_client: APIClient, user: User):
        response = auth_client.post('/api/v1/me/2fa/setup')
        assert response.status_code == 200
        assert 'secret' in response.data
        assert response.data['qr_code'].startswith('data:image/png;base64,')

        assert TOTPDevice.objects.filter(user=user, confirmed=False).count() == 1

    def test_verify_setup_activates_device(self, auth_client: APIClient, user: User):
        secret, _ = _setup_2fa(auth_client)
        code = _totp_code(secret)

        response = auth_client.post('/api/v1/me/2fa/verify-setup', {'code': code}, format='json')
        assert response.status_code == 200

        device = TOTPDevice.objects.get(user=user)
        assert device.confirmed is True

        user.preferences.refresh_from_db()
        assert user.preferences.two_factor_enabled is True

    def test_verify_setup_rejects_invalid_code(self, auth_client: APIClient):
        _setup_2fa(auth_client)
        response = auth_client.post(
            '/api/v1/me/2fa/verify-setup', {'code': '000000'}, format='json'
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_setup_rejected_if_already_active(self, auth_client: APIClient, user: User):
        TOTPDevice.objects.create(user=user, name='existing', confirmed=True)
        response = auth_client.post('/api/v1/me/2fa/setup')
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestLoginWith2FA:
    def test_login_returns_challenge_when_2fa_active(
        self, api_client: APIClient, auth_client: APIClient, user: User
    ):
        # Active le 2FA
        secret, _ = _setup_2fa(auth_client)
        auth_client.post('/api/v1/me/2fa/verify-setup', {'code': _totp_code(secret)}, format='json')

        # Login → renvoie un challenge, pas de tokens
        response = api_client.post(
            '/api/v1/auth/login',
            {
                'email': user.email,
                'password': 'Test1234!',
            },
            format='json',
        )
        assert response.status_code == 200
        assert response.data['require_2fa'] is True
        assert 'challenge_token' in response.data
        assert 'access' not in response.data

    def test_2fa_verify_returns_tokens(
        self, api_client: APIClient, auth_client: APIClient, user: User
    ):
        secret, _ = _setup_2fa(auth_client)
        auth_client.post('/api/v1/me/2fa/verify-setup', {'code': _totp_code(secret)}, format='json')
        _reset_totp_replay(user)  # autorise la réutilisation du code en test

        # Étape 1
        login = api_client.post(
            '/api/v1/auth/login',
            {
                'email': user.email,
                'password': 'Test1234!',
            },
            format='json',
        )
        challenge = login.data['challenge_token']

        # Étape 2
        response = api_client.post(
            '/api/v1/auth/2fa/verify',
            {
                'challenge_token': challenge,
                'code': _totp_code(secret),
            },
            format='json',
        )
        assert response.status_code == 200
        assert 'access' in response.data
        assert 'refresh' in response.data


@pytest.mark.django_db
class TestDisable2FA:
    def test_disable_with_valid_code(self, auth_client: APIClient, user: User):
        secret, _ = _setup_2fa(auth_client)
        auth_client.post('/api/v1/me/2fa/verify-setup', {'code': _totp_code(secret)}, format='json')
        _reset_totp_replay(user)

        response = auth_client.post(
            '/api/v1/me/2fa/disable', {'code': _totp_code(secret)}, format='json'
        )
        assert response.status_code == 200
        assert not TOTPDevice.objects.filter(user=user).exists()

    def test_disable_requires_code(self, auth_client: APIClient, user: User):
        secret, _ = _setup_2fa(auth_client)
        auth_client.post('/api/v1/me/2fa/verify-setup', {'code': _totp_code(secret)}, format='json')

        response = auth_client.post('/api/v1/me/2fa/disable', {'code': '000000'}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
