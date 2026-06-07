"""Tests des endpoints renders : list, create, detail, history."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.accounts.models import User
from apps.renders.models import Render


@pytest.fixture(autouse=True)
def _force_gemini_key():
    with patch('django.conf.settings.GEMINI_API_KEY', 'fake-key'):
        yield


@pytest.mark.django_db
class TestCreate:
    URL = '/api/v1/renders/'

    def test_create_prompt_returns_202_and_triggers_celery(self, auth_client):
        with patch('apps.renders.views.generate_render.delay') as mock_task:
            response = auth_client.post(
                self.URL,
                {
                    'source': 'prompt',
                    'output_type': '2d',
                    'prompt': 'A modern living room with large windows',
                },
                format='json',
            )

        assert response.status_code == 202
        assert response.data['status'] == 'pending'
        assert response.data['source'] == 'prompt'
        assert response.data['result_url'] is None
        mock_task.assert_called_once()
        # L'argument est l'id du render créé
        assert mock_task.call_args.args[0] == response.data['id']

    def test_create_sketch_stores_input_image(self, auth_client, sketch_b64):
        with patch('apps.renders.views.generate_render.delay'):
            response = auth_client.post(
                self.URL,
                {
                    'source': 'sketch',
                    'output_type': '2d',
                    'prompt': 'Photoréaliste',
                    'sketch_base64': sketch_b64,
                },
                format='json',
            )

        assert response.status_code == 202
        render = Render.objects.get(pk=response.data['id'])
        assert render.input_image
        assert render.input_image.read().startswith(b'\x89PNG')

    def test_create_accepts_data_uri_prefix(self, auth_client, sketch_b64):
        with patch('apps.renders.views.generate_render.delay'):
            response = auth_client.post(
                self.URL,
                {
                    'source': 'sketch',
                    'output_type': '2d',
                    'style_hint': 'photoréaliste',
                    'sketch_base64': f'data:image/png;base64,{sketch_b64}',
                },
                format='json',
            )
        assert response.status_code == 202

    def test_create_requires_auth(self, api_client):
        response = api_client.post(
            self.URL,
            {
                'source': 'prompt',
                'output_type': '2d',
                'prompt': 'test',
            },
            format='json',
        )
        assert response.status_code == 401

    def test_quota_enforced(self, auth_client, user):
        user.stats.renders_this_month = user.stats.renders_limit
        user.stats.save()
        response = auth_client.post(
            self.URL,
            {
                'source': 'prompt',
                'output_type': '2d',
                'prompt': 'test',
            },
            format='json',
        )
        assert response.status_code == 400
        # Le message contient le détail + code
        assert 'Quota' in str(response.data)


@pytest.mark.django_db
class TestList:
    URL = '/api/v1/renders/'

    def test_list_only_own_renders(self, auth_client, user):
        Render.objects.create(user=user, source='prompt', prompt='mine')
        other = User.objects.create_user(email='other@x.fr', password='X')
        Render.objects.create(user=other, source='prompt', prompt='not mine')

        response = auth_client.get(self.URL)
        assert response.status_code == 200
        results = response.data['results']
        assert len(results) == 1
        assert results[0]['prompt'] == 'mine'

    def test_filter_by_source(self, auth_client, user):
        Render.objects.create(user=user, source='prompt', prompt='p1')
        Render.objects.create(user=user, source='sketch', prompt='s1')
        response = auth_client.get(self.URL + '?source=sketch')
        results = response.data['results']
        assert len(results) == 1
        assert results[0]['source'] == 'sketch'


@pytest.mark.django_db
class TestDetail:
    def test_get_render(self, auth_client, user):
        r = Render.objects.create(user=user, source='prompt', prompt='hello')
        response = auth_client.get(f'/api/v1/renders/{r.pk}')
        assert response.status_code == 200
        assert response.data['prompt'] == 'hello'

    def test_patch_only_title(self, auth_client, user):
        r = Render.objects.create(user=user, source='prompt', prompt='original')
        response = auth_client.patch(
            f'/api/v1/renders/{r.pk}',
            {'title': 'Salon moderne', 'prompt': 'tentative de modif'},
            format='json',
        )
        assert response.status_code == 200
        r.refresh_from_db()
        assert r.title == 'Salon moderne'
        assert r.prompt == 'original'  # non modifié

    def test_delete_render(self, auth_client, user):
        r = Render.objects.create(user=user, source='prompt', prompt='to delete')
        response = auth_client.delete(f'/api/v1/renders/{r.pk}')
        assert response.status_code == 204
        assert not Render.objects.filter(pk=r.pk).exists()

    def test_cannot_access_other_user_render(self, auth_client):
        other = User.objects.create_user(email='other@x.fr', password='X')
        r = Render.objects.create(user=other, source='prompt', prompt='secret')
        response = auth_client.get(f'/api/v1/renders/{r.pk}')
        assert response.status_code == 404


@pytest.mark.django_db
class TestHistory:
    def test_history_returns_only_done_prompts(self, auth_client, user):
        Render.objects.create(user=user, source='prompt', prompt='done1', status='done')
        Render.objects.create(user=user, source='prompt', prompt='pending', status='pending')
        Render.objects.create(user=user, source='sketch', prompt='sketch1', status='done')

        response = auth_client.get('/api/v1/renders/history')
        assert response.status_code == 200
        # Pas de pagination sur history
        assert len(response.data) == 1
        assert response.data[0]['prompt'] == 'done1'
