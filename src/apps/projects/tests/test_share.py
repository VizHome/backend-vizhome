"""Tests ShareLink + accès public."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.projects.models import ShareLink


@pytest.mark.django_db
class TestShareLink:
    def test_create_share_link(self, auth_client, project):
        r = auth_client.post(
            f'/api/v1/projects/{project.pk}/share', {'permission': 'view'}, format='json',
        )
        assert r.status_code == 201
        assert 'token' in r.data
        assert r.data['share_url'].endswith(r.data['token'])
        assert len(r.data['token']) > 20

    def test_revoke_share_link(self, auth_client, project, user):
        link = ShareLink.objects.create(project=project, created_by=user)
        r = auth_client.delete(f'/api/v1/projects/{project.pk}/share/{link.pk}')
        assert r.status_code == 204
        assert not ShareLink.objects.filter(pk=link.pk).exists()


@pytest.mark.django_db
class TestPublicShared:
    URL = '/api/v1/shared/{}'

    def test_public_access_with_valid_token(self, api_client, project, user):
        link = ShareLink.objects.create(project=project, created_by=user)
        r = api_client.get(self.URL.format(link.token))
        assert r.status_code == 200
        assert r.data['id'] == project.pk

    def test_unknown_token_404(self, api_client):
        r = api_client.get(self.URL.format('invalid-token-xyz'))
        assert r.status_code == 404

    def test_expired_token_410(self, api_client, project, user):
        link = ShareLink.objects.create(
            project=project, created_by=user,
            expires_at=timezone.now() - timedelta(days=1),
        )
        r = api_client.get(self.URL.format(link.token))
        assert r.status_code == 410

    def test_public_endpoint_no_auth_required(self, api_client, project, user):
        link = ShareLink.objects.create(project=project, created_by=user)
        # Pas de Authorization header → ne doit pas renvoyer 401
        r = api_client.get(self.URL.format(link.token))
        assert r.status_code != 401

    def test_last_used_updated(self, api_client, project, user):
        link = ShareLink.objects.create(project=project, created_by=user)
        assert link.last_used_at is None
        api_client.get(self.URL.format(link.token))
        link.refresh_from_db()
        assert link.last_used_at is not None
