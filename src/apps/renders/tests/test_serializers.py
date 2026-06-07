"""Tests des validations du serializer de création."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _force_gemini_key():
    with patch('django.conf.settings.GEMINI_API_KEY', 'fake-key'):
        yield


@pytest.mark.django_db
class TestRenderCreateValidation:
    URL = '/api/v1/renders/'

    def test_prompt_required_for_prompt_source(self, auth_client):
        response = auth_client.post(
            self.URL,
            {
                'source': 'prompt',
                'output_type': '2d',
            },
            format='json',
        )
        assert response.status_code == 400
        assert 'prompt' in response.data

    def test_sketch_required_for_sketch_source(self, auth_client):
        response = auth_client.post(
            self.URL,
            {
                'source': 'sketch',
                'output_type': '2d',
                'prompt': 'A house',
            },
            format='json',
        )
        assert response.status_code == 400
        assert 'sketch_base64' in response.data

    def test_3d_output_rejected_with_gemini(self, auth_client):
        response = auth_client.post(
            self.URL,
            {
                'source': 'prompt',
                'output_type': '3d',
                'prompt': 'A house',
            },
            format='json',
        )
        assert response.status_code == 400
        assert 'output_type' in response.data
