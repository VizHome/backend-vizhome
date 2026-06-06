"""Tests OAuth — providers Google + GitHub avec mocks réseau."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.oauth.base import OAuthError, OAuthProfile


@pytest.mark.django_db
class TestGoogleOAuth:
    def test_unknown_provider_returns_404(self, api_client: APIClient):
        response = api_client.post(
            "/api/v1/auth/oauth/badprovider/exchange", {"id_token": "x"}, format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_google_creates_new_user(self, api_client: APIClient):
        fake_profile = OAuthProfile(
            provider="google",
            provider_user_id="42",
            email="alice@gmail.com",
            email_verified=True,
            first_name="Alice",
            last_name="Martin",
            avatar_url="https://avatar.example/alice.png",
        )

        with patch(
            "apps.accounts.oauth.google.GoogleProvider.exchange",
            return_value=fake_profile,
        ):
            response = api_client.post(
                "/api/v1/auth/oauth/google/exchange",
                {"id_token": "fake"},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["created"] is True
        assert "access" in response.data
        assert response.data["user"]["email"] == "alice@gmail.com"
        assert User.objects.filter(email="alice@gmail.com").exists()

    def test_google_login_existing_user(self, api_client: APIClient, user: User):
        fake_profile = OAuthProfile(
            provider="google",
            provider_user_id="42",
            email=user.email,
            email_verified=True,
        )

        with patch(
            "apps.accounts.oauth.google.GoogleProvider.exchange",
            return_value=fake_profile,
        ):
            response = api_client.post(
                "/api/v1/auth/oauth/google/exchange",
                {"id_token": "fake"},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["created"] is False
        assert User.objects.filter(email=user.email).count() == 1

    def test_invalid_id_token_returns_400(self, api_client: APIClient):
        with patch(
            "apps.accounts.oauth.google.GoogleProvider.exchange",
            side_effect=OAuthError("id_token Google invalide"),
        ):
            response = api_client.post(
                "/api/v1/auth/oauth/google/exchange",
                {"id_token": "bad"},
                format="json",
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestGitHubOAuth:
    def test_github_creates_user(self, api_client: APIClient):
        fake_profile = OAuthProfile(
            provider="github",
            provider_user_id="1234",
            email="bob@example.com",
            email_verified=True,
            first_name="Bob",
            last_name="Builder",
        )

        with patch(
            "apps.accounts.oauth.github.GitHubProvider.exchange",
            return_value=fake_profile,
        ):
            response = api_client.post(
                "/api/v1/auth/oauth/github/exchange",
                {"code": "auth-code", "redirect_uri": "http://localhost:3000/cb"},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["user"]["email"] == "bob@example.com"
        assert response.data["created"] is True
