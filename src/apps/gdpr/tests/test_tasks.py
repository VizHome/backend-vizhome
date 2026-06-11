"""Tests des tâches Celery RGPD (export builder + cron cleanup)."""

from __future__ import annotations

import io
import zipfile
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.gdpr.models import DeletionRequest, ExportRequest
from apps.gdpr.tasks import (
    build_user_export_zip,
    cleanup_expired_exports,
    cleanup_pending_deletions,
)

pytestmark = pytest.mark.django_db


class TestBuildUserExportZip:
    def test_marks_ready_and_writes_archive(self, user: User):
        export = ExportRequest.objects.create(user=user)
        build_user_export_zip(export.pk)
        export.refresh_from_db()
        assert export.status == ExportRequest.Status.READY
        assert export.file_key
        assert export.file_size_bytes > 0
        assert export.expires_at is not None

        # L'archive doit contenir data.json + README.md
        from django.core.files.storage import default_storage

        with default_storage.open(export.file_key, 'rb') as fp:
            content = fp.read()
        zf = zipfile.ZipFile(io.BytesIO(content))
        names = set(zf.namelist())
        assert 'data.json' in names
        assert 'README.md' in names

    def test_no_op_on_unknown_id(self):
        # Pas d'exception même si l'export n'existe pas
        build_user_export_zip(99999)


class TestCleanupExpiredExports:
    def test_marks_expired_and_deletes_archive(self, user: User):
        # READY mais expiré
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        key = 'gdpr/exports/test/exp-1.zip'
        default_storage.save(key, ContentFile(b'fake'))

        ExportRequest.objects.create(
            user=user,
            status=ExportRequest.Status.READY,
            file_key=key,
            file_size_bytes=4,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        n = cleanup_expired_exports()
        assert n == 1
        export = ExportRequest.objects.get(user=user)
        assert export.status == ExportRequest.Status.EXPIRED
        assert export.file_key == ''
        assert not default_storage.exists(key)

    def test_ignores_still_valid(self, user: User):
        ExportRequest.objects.create(
            user=user,
            status=ExportRequest.Status.READY,
            file_key='gdpr/exports/test/still-good.zip',
            expires_at=timezone.now() + timedelta(hours=1),
        )
        n = cleanup_expired_exports()
        assert n == 0


class TestCleanupPendingDeletions:
    def test_hard_deletes_due_users(self, user: User, other_user: User):
        # `user` : échéance passée → doit être supprimé
        DeletionRequest.objects.create(
            user=user,
            scheduled_for=timezone.now() - timedelta(hours=1),
        )
        user.is_active = False
        user.save(update_fields=['is_active'])

        # `other_user` : échéance future → doit rester
        DeletionRequest.objects.create(
            user=other_user,
            scheduled_for=timezone.now() + timedelta(days=15),
        )
        other_user.is_active = False
        other_user.save(update_fields=['is_active'])

        n = cleanup_pending_deletions()
        assert n == 1
        assert not User.objects.filter(pk=user.pk).exists()
        assert User.objects.filter(pk=other_user.pk).exists()

    def test_ignores_cancelled_requests(self, user: User):
        DeletionRequest.objects.create(
            user=user,
            scheduled_for=timezone.now() - timedelta(days=1),
            cancelled_at=timezone.now(),
        )
        n = cleanup_pending_deletions()
        assert n == 0
        assert User.objects.filter(pk=user.pk).exists()

    def test_ignores_already_completed_requests(self, user: User):
        DeletionRequest.objects.create(
            user=user,
            scheduled_for=timezone.now() - timedelta(days=1),
            completed_at=timezone.now() - timedelta(hours=2),
        )
        n = cleanup_pending_deletions()
        assert n == 0
        assert User.objects.filter(pk=user.pk).exists()
