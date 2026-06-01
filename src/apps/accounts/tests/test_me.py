"""Tests des endpoints /me et /me/preferences."""
from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.mark.django_db
class TestMe:
    def test_get_me_requires_auth(self, api_client: APIClient):
        response = api_client.get('/api/v1/me/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_me_returns_profile_with_stats_and_prefs(
        self, auth_client: APIClient, user: User
    ):
        response = auth_client.get('/api/v1/me/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['email'] == user.email
        # `name` est désormais le pseudo public (immuable), pas first_name+last_name
        assert response.data['name'] == user.pseudo
        assert response.data['pseudo'] == user.pseudo
        assert response.data['first_name'] == 'Jean'
        assert response.data['last_name'] == 'Dupont'
        assert 'stats' in response.data
        assert 'preferences' in response.data
        assert response.data['stats']['renders_limit'] == 5  # plan free

    def test_patch_me_updates_profile(self, auth_client: APIClient, user: User):
        response = auth_client.patch('/api/v1/me/', {'first_name': 'Pierre'}, format='json')
        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.first_name == 'Pierre'

    def test_patch_me_cannot_change_email_or_plan(self, auth_client: APIClient, user: User):
        original_email = user.email
        original_plan = user.plan
        auth_client.patch(
            '/api/v1/me/',
            {'email': 'hack@hack.fr', 'plan': 'enterprise'},
            format='json',
        )
        user.refresh_from_db()
        assert user.email == original_email
        assert user.plan == original_plan


@pytest.mark.django_db
class TestPreferences:
    def test_patch_preferences(self, auth_client: APIClient, user: User):
        response = auth_client.patch(
            '/api/v1/me/preferences',
            {'theme': 'dark', 'language': 'en', 'reduced_motion': True},
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK
        user.preferences.refresh_from_db()
        assert user.preferences.theme == 'dark'
        assert user.preferences.language == 'en'
        assert user.preferences.reduced_motion is True

    def test_patch_invalid_choice_rejected(self, auth_client: APIClient):
        response = auth_client.patch(
            '/api/v1/me/preferences', {'theme': 'rainbow'}, format='json'
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestChangePassword:
    def test_change_password(self, auth_client: APIClient, user: User):
        response = auth_client.post('/api/v1/me/change-password', {
            'current_password': 'Test1234!',
            'new_password': 'NewPass1234!',
            'new_password_confirm': 'NewPass1234!',
        }, format='json')
        assert response.status_code == status.HTTP_204_NO_CONTENT
        user.refresh_from_db()
        assert user.check_password('NewPass1234!')

    def test_wrong_current_password_rejected(self, auth_client: APIClient):
        response = auth_client.post('/api/v1/me/change-password', {
            'current_password': 'wrong',
            'new_password': 'NewPass1234!',
            'new_password_confirm': 'NewPass1234!',
        }, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
