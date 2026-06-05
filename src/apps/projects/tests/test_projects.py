"""Tests CRUD Project + duplication."""

from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.projects.models import Annotation, Project, Scene


@pytest.mark.django_db
class TestProjectCRUD:
    URL = "/api/v1/projects/"

    def test_list_only_own_projects(self, auth_client, user):
        Project.objects.create(user=user, title="mine")
        other = User.objects.create_user(email="o@x.fr", password="x")
        Project.objects.create(user=other, title="not mine")

        r = auth_client.get(self.URL)
        assert r.status_code == 200
        results = r.data["results"]
        assert len(results) == 1
        assert results[0]["title"] == "mine"

    def test_create_project_creates_scene_auto(self, auth_client, user):
        r = auth_client.post(self.URL, {"title": "Salon"}, format="json")
        assert r.status_code == 201
        assert r.data["title"] == "Salon"
        project = Project.objects.get(pk=r.data["id"])
        assert Scene.objects.filter(project=project).exists()
        # Stats user incrémentées
        user.stats.refresh_from_db()
        assert user.stats.total_projects == 1

    def test_get_detail_includes_scene_and_lists(self, auth_client, project):
        Annotation.objects.create(
            project=project,
            type="note",
            position={"x": 0, "y": 0, "z": 0},
            content="hello",
        )
        r = auth_client.get(f"/api/v1/projects/{project.pk}")
        assert r.status_code == 200
        assert "scene" in r.data
        assert "imported_models" in r.data
        assert "annotations" in r.data
        assert len(r.data["annotations"]) == 1

    def test_patch_updates_fields(self, auth_client, project):
        r = auth_client.patch(
            f"/api/v1/projects/{project.pk}", {"title": "Renommé"}, format="json"
        )
        assert r.status_code == 200
        project.refresh_from_db()
        assert project.title == "Renommé"

    def test_delete_decrements_stats(self, auth_client, user, project):
        user.stats.total_projects = 1
        user.stats.save()
        r = auth_client.delete(f"/api/v1/projects/{project.pk}")
        assert r.status_code == 204
        user.stats.refresh_from_db()
        assert user.stats.total_projects == 0

    def test_cannot_access_other_user_project(self, auth_client):
        other = User.objects.create_user(email="o@x.fr", password="x")
        other_project = Project.objects.create(user=other, title="secret")
        r = auth_client.get(f"/api/v1/projects/{other_project.pk}")
        assert r.status_code == 404


@pytest.mark.django_db
class TestDuplicate:
    def test_duplicate_copies_scene_and_annotations(self, auth_client, user, project):
        project.scene.data = {"camera": {"position": [1, 2, 3]}}
        project.scene.save()
        Annotation.objects.create(
            project=project,
            type="note",
            position={"x": 0, "y": 0, "z": 0},
            content="note1",
        )

        r = auth_client.post(f"/api/v1/projects/{project.pk}/duplicate")
        assert r.status_code == 201
        assert r.data["title"].endswith("(copie)")
        new_pk = r.data["id"]
        new_project = Project.objects.get(pk=new_pk)
        assert new_project.scene.data == {"camera": {"position": [1, 2, 3]}}
        assert new_project.annotations.count() == 1

    def test_duplicate_skips_assets_by_default(
        self, auth_client, project, fake_glb, user
    ):
        # Ajoute un modèle 3D au projet source
        from apps.projects.models import ImportedModel

        ImportedModel.objects.create(
            project=project,
            name="Cube",
            format="glb",
            file=fake_glb,
            file_size_bytes=4,
        )

        r = auth_client.post(f"/api/v1/projects/{project.pk}/duplicate")
        assert r.status_code == 201
        new_project = Project.objects.get(pk=r.data["id"])
        # Pas d'assets copiés par défaut
        assert new_project.imported_models.count() == 0

    def test_duplicate_with_copy_assets_copies_models(self, auth_client, project, user):
        from unittest.mock import patch
        from apps.projects.models import ImportedModel

        m1 = ImportedModel.objects.create(
            project=project,
            name="Cube",
            format="glb",
            file="projects/models/2026/05/orig_abc.glb",
            file_size_bytes=1024,
            position={"x": 1, "y": 2, "z": 3},
        )
        m2 = ImportedModel.objects.create(
            project=project,
            name="Sphere",
            format="obj",
            file="projects/models/2026/05/orig_xyz.obj",
            file_size_bytes=2048,
        )

        with patch("apps.projects.presigned.copy_object") as mock_copy:
            r = auth_client.post(
                f"/api/v1/projects/{project.pk}/duplicate?copy_assets=true"
            )
            assert r.status_code == 201
            assert mock_copy.call_count == 2

        new_project = Project.objects.get(pk=r.data["id"])
        assert new_project.imported_models.count() == 2
        # Transform conservé
        new_m1 = new_project.imported_models.get(name="Cube")
        assert new_m1.position == {"x": 1, "y": 2, "z": 3}
        # Stats : 2× les tailles (originaux + copies, chacun incrémenté par le signal)
        user.stats.refresh_from_db()
        assert user.stats.storage_used_bytes == 2 * (1024 + 2048)

    def test_duplicate_with_copy_assets_enforces_quota(
        self, auth_client, project, user
    ):
        from apps.projects.models import ImportedModel

        ImportedModel.objects.create(
            project=project,
            name="Big",
            format="glb",
            file="projects/models/2026/05/big.glb",
            file_size_bytes=user.stats.storage_limit_bytes,
        )

        r = auth_client.post(
            f"/api/v1/projects/{project.pk}/duplicate?copy_assets=true"
        )
        assert r.status_code == 400
        assert "storage" in str(r.data).lower()
        # Aucun projet créé en cas de quota refusé
        assert Project.objects.filter(title__icontains="(copie)").count() == 0
