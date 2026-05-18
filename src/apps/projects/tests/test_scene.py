"""Tests Scene : GET + PUT avec versioning."""
from __future__ import annotations

import pytest
from rest_framework import status


@pytest.mark.django_db
class TestScene:
    def test_get_scene(self, auth_client, project):
        r = auth_client.get(f'/api/v1/projects/{project.pk}/scene')
        assert r.status_code == 200
        assert r.data['data'] == {}
        assert r.data['version'] == 1

    def test_put_scene_increments_version(self, auth_client, project):
        scene_data = {
            'camera': {'position': [10, 5, 10], 'target': [0, 0, 0]},
            'lights': {'preset': 'sunset'},
            'weather': 'cloudy',
            'navigation': 'first_person',
        }
        r = auth_client.put(
            f'/api/v1/projects/{project.pk}/scene',
            {'data': scene_data}, format='json',
        )
        assert r.status_code == 200
        assert r.data['data'] == scene_data
        assert r.data['version'] == 2

    def test_put_scene_persists(self, auth_client, project):
        auth_client.put(
            f'/api/v1/projects/{project.pk}/scene',
            {'data': {'foo': 'bar'}}, format='json',
        )
        project.scene.refresh_from_db()
        assert project.scene.data == {'foo': 'bar'}
