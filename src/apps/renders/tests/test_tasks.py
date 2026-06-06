"""Tests de la tâche Celery generate_render avec provider mocké."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.renders.models import Render
from apps.renders.providers.base import GenerationResult, ProviderError
from apps.renders.tasks import generate_render


@pytest.mark.django_db
class TestGenerateRenderTask:
    def test_success_pipeline(self, user, fake_gemini_result):
        render = Render.objects.create(
            user=user, source="prompt", output_type="2d", prompt="a house"
        )

        fake_result = GenerationResult(
            image_bytes=fake_gemini_result, mime_type="image/png"
        )
        with patch("apps.renders.tasks.get_provider") as mock_get:
            mock_provider = MagicMock(name="gemini")
            mock_provider.name = "gemini"
            mock_provider.generate.return_value = fake_result
            mock_get.return_value = mock_provider

            generate_render(render.pk)

        render.refresh_from_db()
        assert render.status == Render.Status.DONE
        assert render.provider == "gemini"
        assert render.result_image
        assert render.completed_at is not None
        # Quota incrémenté
        user.stats.refresh_from_db()
        assert user.stats.renders_this_month == 1

    def test_provider_error_marks_failed(self, user):
        render = Render.objects.create(
            user=user, source="prompt", output_type="2d", prompt="x"
        )
        with patch("apps.renders.tasks.get_provider") as mock_get:
            mock_get.return_value.generate.side_effect = ProviderError("Safety filter")
            mock_get.return_value.name = "gemini"

            generate_render(render.pk)

        render.refresh_from_db()
        assert render.status == Render.Status.FAILED
        assert "Safety filter" in render.error_message
        # Quota NON incrémenté en cas d'échec
        user.stats.refresh_from_db()
        assert user.stats.renders_this_month == 0

    def test_skip_if_already_terminal(self, user):
        render = Render.objects.create(
            user=user,
            source="prompt",
            prompt="x",
            status="done",
        )
        with patch("apps.renders.tasks.get_provider") as mock_get:
            generate_render(render.pk)
            mock_get.assert_not_called()
