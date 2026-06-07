"""Tests des endpoints d'export RGPD (POST + GET status)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.gdpr.models import EXPORT_LINK_TTL_HOURS, ExportRequest

pytestmark = pytest.mark.django_db


class TestExportRequest:
    URL = '/api/v1/me/export-data'

    def test_requires_auth(self, api_client: APIClient):
        r = api_client.post(self.URL)
        assert r.status_code == 401

    def test_creates_export_request_and_triggers_task(
        self, auth_client: APIClient, user: User
    ):
        with patch('apps.gdpr.tasks.build_user_export_zip.delay') as mock_delay:
            r = auth_client.post(self.URL)
        assert r.status_code == 202
        assert ExportRequest.objects.filter(user=user).count() == 1
        export = ExportRequest.objects.get(user=user)
        assert export.status == ExportRequest.Status.QUEUED
        mock_delay.assert_called_once_with(export.pk)

    def test_idempotent_returns_pending_existing(
        self, auth_client: APIClient, user: User
    ):
        existing = ExportRequest.objects.create(
            user=user, status=ExportRequest.Status.PROCESSING
        )
        with patch('apps.gdpr.tasks.build_user_export_zip.delay') as mock_delay:
            r = auth_client.post(self.URL)
        assert r.status_code == 202
        assert r.data['id'] == existing.pk
        assert ExportRequest.objects.filter(user=user).count() == 1
        mock_delay.assert_not_called()


class TestExportStatus:
    URL = '/api/v1/me/export-data/status'

    def test_requires_auth(self, api_client: APIClient):
        r = api_client.get(self.URL)
        assert r.status_code == 401

    def test_404_when_no_export(self, auth_client: APIClient):
        r = auth_client.get(self.URL)
        assert r.status_code == 404
        assert r.data['code'] == 'no_export'

    def test_returns_status_for_latest_export(
        self, auth_client: APIClient, user: User
    ):
        ExportRequest.objects.create(user=user, status=ExportRequest.Status.QUEUED)
        latest = ExportRequest.objects.create(
            user=user, status=ExportRequest.Status.PROCESSING
        )
        r = auth_client.get(self.URL)
        assert r.status_code == 200
        assert r.data['id'] == latest.pk
        assert r.data['status'] == 'processing'

    def test_marks_ready_as_expired_after_deadline(
        self, auth_client: APIClient, user: User
    ):
        ExportRequest.objects.create(
            user=user,
            status=ExportRequest.Status.READY,
            file_key='gdpr/exports/1/export-1.zip',
            expires_at=timezone.now() - timedelta(hours=1),
        )
        r = auth_client.get(self.URL)
        assert r.status_code == 200
        assert r.data['status'] == 'expired'

    def test_does_not_leak_other_user_export(
        self, other_auth_client: APIClient, user: User
    ):
        ExportRequest.objects.create(
            user=user, status=ExportRequest.Status.READY,
            expires_at=timezone.now() + timedelta(hours=EXPORT_LINK_TTL_HOURS),
        )
        # `other_auth_client` is logged as `other_user` who has no exports
        r = other_auth_client.get(self.URL)
        assert r.status_code == 404
