"""Tests des endpoints de suppression de compte RGPD."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, UserSession
from apps.gdpr.models import DELETION_GRACE_PERIOD_DAYS, DeletionRequest

pytestmark = pytest.mark.django_db


class TestRequestDeleteAccount:
    URL = '/api/v1/me/delete-account'

    def test_requires_auth(self, api_client: APIClient):
        r = api_client.post(self.URL, {'confirm': 'DELETE'}, format='json')
        assert r.status_code == 401

    def test_requires_confirm_token(self, auth_client: APIClient, user: User):
        r = auth_client.post(self.URL, {'confirm': 'maybe'}, format='json')
        assert r.status_code == 400
        user.refresh_from_db()
        assert user.is_active is True

    def test_creates_request_and_deactivates_user(self, auth_client: APIClient, user: User):
        # Crée une session pour vérifier qu'elle est révoquée
        session = UserSession.objects.create(user=user, refresh_jti='jti1')
        r = auth_client.post(self.URL, {'confirm': 'DELETE', 'notes': 'au revoir'}, format='json')
        assert r.status_code == 202
        user.refresh_from_db()
        assert user.is_active is False
        deletion = DeletionRequest.objects.get(user=user)
        assert deletion.notes == 'au revoir'
        assert deletion.is_pending is True
        # Échéance proche de J+30
        delta = deletion.scheduled_for - timezone.now()
        assert timedelta(days=DELETION_GRACE_PERIOD_DAYS - 1) < delta
        assert delta < timedelta(days=DELETION_GRACE_PERIOD_DAYS + 1)
        # Sessions révoquées
        session.refresh_from_db()
        assert session.revoked_at is not None

    def test_conflict_if_already_scheduled(self, auth_client: APIClient, user: User):
        DeletionRequest.objects.create(user=user)
        r = auth_client.post(self.URL, {'confirm': 'DELETE'}, format='json')
        assert r.status_code == 409
        assert r.data['code'] == 'already_scheduled'

    def test_replaces_old_cancelled_request(self, auth_client: APIClient, user: User):
        DeletionRequest.objects.create(user=user, cancelled_at=timezone.now() - timedelta(days=1))
        r = auth_client.post(self.URL, {'confirm': 'DELETE'}, format='json')
        assert r.status_code == 202
        # Une seule existe désormais (OneToOne enforced)
        assert DeletionRequest.objects.filter(user=user).count() == 1
        deletion = DeletionRequest.objects.get(user=user)
        assert deletion.cancelled_at is None


class TestCancelDeleteAccount:
    URL = '/api/v1/me/delete-account/cancel'

    def test_requires_auth(self, api_client: APIClient):
        r = api_client.post(self.URL)
        assert r.status_code == 401

    def test_cancels_pending_request_and_reactivates_user(self, auth_client: APIClient, user: User):
        # Crée la demande + soft delete
        DeletionRequest.objects.create(user=user)
        user.is_active = False
        user.save(update_fields=['is_active'])

        r = auth_client.post(self.URL)
        assert r.status_code == 200
        user.refresh_from_db()
        assert user.is_active is True
        deletion = DeletionRequest.objects.get(user=user)
        assert deletion.cancelled_at is not None

    def test_404_when_no_request(self, auth_client: APIClient):
        r = auth_client.post(self.URL)
        assert r.status_code == 404
        assert r.data['code'] == 'no_deletion_request'

    def test_410_when_already_completed(self, auth_client: APIClient, user: User):
        DeletionRequest.objects.create(user=user, completed_at=timezone.now())
        r = auth_client.post(self.URL)
        assert r.status_code == 410
        assert r.data['code'] == 'already_completed'

    def test_idempotent_when_already_cancelled(self, auth_client: APIClient, user: User):
        DeletionRequest.objects.create(user=user, cancelled_at=timezone.now() - timedelta(hours=1))
        r = auth_client.post(self.URL)
        assert r.status_code == 200

    def test_does_not_cancel_other_user_request(self, other_auth_client: APIClient, user: User):
        # `user` a une demande, `other_user` (qui appelle) en a pas
        DeletionRequest.objects.create(user=user)
        r = other_auth_client.post(self.URL)
        assert r.status_code == 404
        # Demande de `user` toujours en cours
        assert DeletionRequest.objects.get(user=user).cancelled_at is None
