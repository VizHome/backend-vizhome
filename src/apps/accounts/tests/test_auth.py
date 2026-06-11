"""Tests des endpoints d'authentification."""

from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User, UserPreferences, UserStats


@pytest.mark.django_db
class TestRegister:
    url = '/api/v1/auth/register'

    def test_register_creates_user_with_prefs_and_stats(self, api_client: APIClient):
        payload = {
            'email': 'new@example.fr',
            'pseudo': 'newuser',
            'first_name': 'New',
            'last_name': 'User',
            'password': 'Test1234!',
            'password_confirm': 'Test1234!',
        }
        response = api_client.post(self.url, payload, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert 'access' in response.data
        assert 'refresh' in response.data
        assert response.data['user']['email'] == 'new@example.fr'
        assert response.data['user']['pseudo'] == 'newuser'

        user = User.objects.get(email='new@example.fr')
        assert user.pseudo == 'newuser'
        assert UserPreferences.objects.filter(user=user).exists()
        assert UserStats.objects.filter(user=user).exists()

    def test_register_rejects_missing_pseudo(self, api_client: APIClient):
        response = api_client.post(
            self.url,
            {
                'email': 'np@example.fr',
                'first_name': 'A',
                'last_name': 'B',
                'password': 'Test1234!',
                'password_confirm': 'Test1234!',
            },
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'pseudo' in response.data

    def test_register_rejects_duplicate_pseudo(self, api_client: APIClient, user: User):
        response = api_client.post(
            self.url,
            {
                'email': 'unique@example.fr',
                'pseudo': user.pseudo,  # déjà pris
                'password': 'Test1234!',
                'password_confirm': 'Test1234!',
            },
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'pseudo' in response.data

    def test_register_rejects_invalid_pseudo_format(self, api_client: APIClient):
        # Pseudo qui ne commence pas par une lettre → rejet
        response = api_client.post(
            self.url,
            {
                'email': 'xx@example.fr',
                'pseudo': '123abc',
                'password': 'Test1234!',
                'password_confirm': 'Test1234!',
            },
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_rejects_password_mismatch(self, api_client: APIClient):
        response = api_client.post(
            self.url,
            {
                'email': 'x@x.fr',
                'password': 'Test1234!',
                'password_confirm': 'OTHER1234!',
            },
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_rejects_duplicate_email(self, api_client: APIClient, user: User):
        response = api_client.post(
            self.url,
            {
                'email': user.email,
                'password': 'Test1234!',
                'password_confirm': 'Test1234!',
            },
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestLogin:
    url = '/api/v1/auth/login'

    def test_login_returns_tokens(self, api_client: APIClient, user: User):
        response = api_client.post(
            self.url,
            {
                'email': user.email,
                'password': 'Test1234!',
            },
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data

    def test_login_wrong_password_rejected(self, api_client: APIClient, user: User):
        response = api_client.post(
            self.url,
            {
                'email': user.email,
                'password': 'wrong',
            },
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_creates_session(self, api_client: APIClient, user: User):
        api_client.post(
            self.url,
            {
                'email': user.email,
                'password': 'Test1234!',
            },
            format='json',
            HTTP_USER_AGENT='Mozilla/5.0 (Windows) Chrome/120',
        )
        assert user.sessions.filter(revoked_at__isnull=True).count() == 1
        session = user.sessions.first()
        assert 'Chrome' in session.device_name
        assert 'Windows' in session.device_name


@pytest.mark.django_db
class TestLogout:
    def test_logout_blacklists_refresh_and_revokes_session(self, api_client: APIClient, user: User):
        login = api_client.post(
            '/api/v1/auth/login',
            {
                'email': user.email,
                'password': 'Test1234!',
            },
            format='json',
        )
        access = login.data['access']
        refresh = login.data['refresh']

        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        response = api_client.post('/api/v1/auth/logout', {'refresh': refresh}, format='json')

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert user.sessions.filter(revoked_at__isnull=True).count() == 0


@pytest.mark.django_db
class TestPasswordReset:
    def test_forgot_password_does_not_leak_existence(self, api_client: APIClient):
        # Email inexistant : doit quand même renvoyer 204
        response = api_client.post(
            '/api/v1/auth/forgot-password', {'email': 'nope@nope.fr'}, format='json'
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_forgot_then_reset_password(self, api_client: APIClient, user: User, mailoutbox):
        # 1. Demande de reset
        r1 = api_client.post('/api/v1/auth/forgot-password', {'email': user.email}, format='json')
        assert r1.status_code == status.HTTP_204_NO_CONTENT
        assert len(mailoutbox) == 1

        # 2. Extrait uid + token de l'email
        body = mailoutbox[0].body
        import re

        m = re.search(r'uid=([^&]+)&token=([^\s]+)', body)
        assert m, f'Lien introuvable dans : {body}'
        uid, token = m.group(1), m.group(2)

        # 3. Reset
        r2 = api_client.post(
            '/api/v1/auth/reset-password',
            {
                'uid': uid,
                'token': token,
                'password': 'NewPass1234!',
                'password_confirm': 'NewPass1234!',
            },
            format='json',
        )
        assert r2.status_code == status.HTTP_204_NO_CONTENT

        # 4. Le nouveau mdp marche
        user.refresh_from_db()
        assert user.check_password('NewPass1234!')
