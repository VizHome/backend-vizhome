"""Tests de listing et révocation de sessions."""

from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User, UserSession


@pytest.mark.django_db
class TestSessions:
    def test_list_sessions(self, api_client: APIClient, user: User):
        # Login deux fois → 2 sessions
        for ua in ["Mozilla/5.0 Chrome Windows", "Mozilla/5.0 Safari Mac"]:
            api_client.post(
                "/api/v1/auth/login",
                {
                    "email": user.email,
                    "password": "Test1234!",
                },
                format="json",
                HTTP_USER_AGENT=ua,
            )

        # Auth avec un des access tokens
        login = api_client.post(
            "/api/v1/auth/login",
            {
                "email": user.email,
                "password": "Test1234!",
            },
            format="json",
            HTTP_USER_AGENT="Mozilla/5.0 Firefox Linux",
        )
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        response = api_client.get("/api/v1/me/sessions")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 3

    def test_revoke_session(self, api_client: APIClient, user: User):
        # Crée une session "à révoquer"
        target = UserSession.objects.create(
            user=user, refresh_jti="fake-jti", device_name="Chrome — Windows"
        )
        # Auth en tant que ce user
        login = api_client.post(
            "/api/v1/auth/login",
            {
                "email": user.email,
                "password": "Test1234!",
            },
            format="json",
        )
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        response = api_client.delete(f"/api/v1/me/sessions/{target.pk}")
        assert response.status_code == status.HTTP_204_NO_CONTENT

        target.refresh_from_db()
        assert target.revoked_at is not None
