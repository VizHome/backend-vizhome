"""Tests upload de modèles 3D — multipart + presigned URL."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework import status

from apps.projects.models import ImportedModel


@pytest.mark.django_db
class TestMultipartUpload:
    def test_upload_glb_creates_model(self, auth_client, project, fake_glb, user):
        r = auth_client.post(
            f"/api/v1/projects/{project.pk}/models",
            {"name": "Cube", "file": fake_glb},
            format="multipart",
        )
        assert r.status_code == 201
        assert r.data["name"] == "Cube"
        assert r.data["format"] == "glb"
        assert r.data["file_size_bytes"] == 4

        # Stats storage incrémentées
        user.stats.refresh_from_db()
        assert user.stats.storage_used_bytes == 4

    def test_upload_unsupported_format_rejected(self, auth_client, project):
        from django.core.files.uploadedfile import SimpleUploadedFile

        bad = SimpleUploadedFile("cube.exe", b"xxxx")
        r = auth_client.post(
            f"/api/v1/projects/{project.pk}/models",
            {"name": "Cube", "file": bad},
            format="multipart",
        )
        assert r.status_code == 400
        assert "file" in r.data

    def test_storage_quota_enforced(self, auth_client, project, fake_glb, user):
        user.stats.storage_used_bytes = user.stats.storage_limit_bytes
        user.stats.save()
        r = auth_client.post(
            f"/api/v1/projects/{project.pk}/models",
            {"name": "Cube", "file": fake_glb},
            format="multipart",
        )
        assert r.status_code == 400
        assert "storage" in str(r.data).lower()

    def test_delete_model_decrements_stats_and_removes_file(
        self, auth_client, project, fake_glb, user
    ):
        r = auth_client.post(
            f"/api/v1/projects/{project.pk}/models",
            {"name": "Cube", "file": fake_glb},
            format="multipart",
        )
        model_id = r.data["id"]
        user.stats.refresh_from_db()
        size_before = user.stats.storage_used_bytes
        assert size_before > 0

        r2 = auth_client.delete(f"/api/v1/projects/{project.pk}/models/{model_id}")
        assert r2.status_code == 204

        user.stats.refresh_from_db()
        assert user.stats.storage_used_bytes == 0


@pytest.mark.django_db
class TestPresignedUpload:
    URL_REQUEST = "/api/v1/projects/{}/models/upload-url"
    URL_CONFIRM = "/api/v1/projects/{}/models/confirm"

    @patch("apps.projects.views.generate_upload_url")
    def test_request_upload_url(self, mock_gen, auth_client, project):
        mock_gen.return_value = (
            "http://localhost:9000/vizhome-media/projects/models/...?sig"
        )
        r = auth_client.post(
            self.URL_REQUEST.format(project.pk),
            {
                "name": "BigModel",
                "file_name": "house.glb",
                "file_size_bytes": 50_000_000,
                "content_type": "model/gltf-binary",
            },
            format="json",
        )
        assert r.status_code == 200
        assert "upload_url" in r.data
        assert r.data["method"] == "PUT"
        assert r.data["key"].endswith(".glb")
        mock_gen.assert_called_once()

    def test_request_upload_url_rejects_bad_extension(self, auth_client, project):
        r = auth_client.post(
            self.URL_REQUEST.format(project.pk),
            {"name": "Bad", "file_name": "malware.exe", "file_size_bytes": 100},
            format="json",
        )
        assert r.status_code == 400

    def test_request_upload_url_enforces_quota(self, auth_client, project, user):
        user.stats.storage_used_bytes = user.stats.storage_limit_bytes
        user.stats.save()
        r = auth_client.post(
            self.URL_REQUEST.format(project.pk),
            {"name": "X", "file_name": "x.glb", "file_size_bytes": 100},
            format="json",
        )
        assert r.status_code == 400

    @patch("apps.projects.views.head_object")
    def test_confirm_creates_model(self, mock_head, auth_client, project, user):
        mock_head.return_value = {"ContentLength": 123_456}
        key = "projects/models/2026/05/abc.glb"
        r = auth_client.post(
            self.URL_CONFIRM.format(project.pk),
            {"name": "House", "key": key},
            format="json",
        )
        assert r.status_code == 201
        assert r.data["name"] == "House"
        assert r.data["format"] == "glb"
        assert r.data["file_size_bytes"] == 123_456

        user.stats.refresh_from_db()
        assert user.stats.storage_used_bytes == 123_456

    @patch("apps.projects.views.head_object")
    def test_confirm_fails_if_file_missing(self, mock_head, auth_client, project):
        mock_head.return_value = None
        r = auth_client.post(
            self.URL_CONFIRM.format(project.pk),
            {"name": "House", "key": "missing.glb"},
            format="json",
        )
        assert r.status_code == 400
