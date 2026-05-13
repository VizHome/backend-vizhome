"""Tests des limites de sécurité : throttling + axes + is_current session."""
from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.mark.django_db
class TestAxesLockout:
    def test_lockout_after_5_failed_logins(self, api_client: APIClient, user: User):
        for _ in range(5):
            api_client.post('/api/v1/auth/login', {
                'email': user.email, 'password': 'wrong',
            }, format='json')

        # 6e tentative → verrouillé même si le bon mdp est fourni
        response = api_client.post('/api/v1/auth/login', {
            'email': user.email, 'password': 'Test1234!',
        }, format='json')
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.data['code'] == 'account_locked'

    def test_successful_login_resets_counter(self, api_client: APIClient, user: User):
        for _ in range(3):
            api_client.post('/api/v1/auth/login', {
                'email': user.email, 'password': 'wrong',
            }, format='json')

        # Login réussi
        ok = api_client.post('/api/v1/auth/login', {
            'email': user.email, 'password': 'Test1234!',
        }, format='json')
        assert ok.status_code == 200

        # Compteur reset : on doit pouvoir refaire 5 tentatives échouées sans lockout
        for _ in range(4):
            api_client.post('/api/v1/auth/login', {
                'email': user.email, 'password': 'wrong',
            }, format='json')
        last = api_client.post('/api/v1/auth/login', {
            'email': user.email, 'password': 'Test1234!',
        }, format='json')
        assert last.status_code == 200


@pytest.mark.django_db
class TestIsCurrentSession:
    def test_current_session_marked_true(self, api_client: APIClient, user: User):
        login = api_client.post('/api/v1/auth/login', {
            'email': user.email, 'password': 'Test1234!',
        }, format='json', HTTP_USER_AGENT='Chrome Windows')

        access = login.data['access']
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        response = api_client.get('/api/v1/me/sessions')
        sessions = response.data['results']
        # 1 seule session, c'est la courante
        assert len(sessions) == 1
        assert sessions[0]['is_current'] is True

    def test_other_sessions_marked_false(self, api_client: APIClient, user: User):
        # Login depuis device A
        login_a = api_client.post('/api/v1/auth/login', {
            'email': user.email, 'password': 'Test1234!',
        }, format='json', HTTP_USER_AGENT='Chrome Windows')

        # Login depuis device B (token séparé)
        api_client.post('/api/v1/auth/login', {
            'email': user.email, 'password': 'Test1234!',
        }, format='json', HTTP_USER_AGENT='Safari Mac')

        # On consulte depuis A
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {login_a.data["access"]}')
        response = api_client.get('/api/v1/me/sessions')
        sessions = response.data['results']

        assert len(sessions) == 2
        current_sessions = [s for s in sessions if s['is_current']]
        assert len(current_sessions) == 1
        assert 'Windows' in current_sessions[0]['device_name']
