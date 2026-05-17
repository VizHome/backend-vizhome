"""Tests CRUD annotations."""
from __future__ import annotations

import pytest

from apps.projects.models import Annotation


@pytest.mark.django_db
class TestAnnotations:
    def test_create_annotation(self, auth_client, project):
        r = auth_client.post(
            f'/api/v1/projects/{project.pk}/annotations',
            {'type': 'note', 'position': {'x': 1, 'y': 2, 'z': 3}, 'content': 'Hello'},
            format='json',
        )
        assert r.status_code == 201
        assert r.data['content'] == 'Hello'
        assert Annotation.objects.filter(project=project).count() == 1

    def test_list_annotations(self, auth_client, project):
        Annotation.objects.create(project=project, type='note', position={'x':0,'y':0,'z':0})
        Annotation.objects.create(project=project, type='measure', position={'x':1,'y':1,'z':1})
        r = auth_client.get(f'/api/v1/projects/{project.pk}/annotations')
        assert r.status_code == 200
        assert len(r.data['results']) == 2

    def test_patch_annotation(self, auth_client, project):
        a = Annotation.objects.create(project=project, type='note', position={'x':0,'y':0,'z':0}, content='old')
        r = auth_client.patch(
            f'/api/v1/projects/{project.pk}/annotations/{a.pk}',
            {'content': 'new'}, format='json',
        )
        assert r.status_code == 200
        a.refresh_from_db()
        assert a.content == 'new'

    def test_delete_annotation(self, auth_client, project):
        a = Annotation.objects.create(project=project, type='note', position={'x':0,'y':0,'z':0})
        r = auth_client.delete(f'/api/v1/projects/{project.pk}/annotations/{a.pk}')
        assert r.status_code == 204
        assert not Annotation.objects.filter(pk=a.pk).exists()
