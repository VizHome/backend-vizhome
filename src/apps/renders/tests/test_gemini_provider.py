"""Tests du provider Gemini avec mocks SDK."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.renders.providers.base import ProviderError
from apps.renders.providers.gemini import GeminiProvider


def _mock_gemini_response(image_bytes: bytes, mime: str = "image/png"):
    """Construit un objet réponse Gemini factice avec une image inline."""
    inline = MagicMock(data=image_bytes, mime_type=mime)
    part = MagicMock(inline_data=inline)
    content = MagicMock(parts=[part])
    candidate = MagicMock(content=content)
    response = MagicMock(candidates=[candidate])
    return response


@pytest.fixture
def gemini():
    with (
        patch("django.conf.settings.GEMINI_API_KEY", "fake-key"),
        patch("apps.renders.providers.gemini.genai.Client") as mock_client_cls,
    ):
        provider = GeminiProvider()
        # Patch directement l'instance client pour contrôler les appels
        provider._client = MagicMock()
        yield provider


class TestGeminiProvider:
    def test_requires_api_key(self):
        with patch("django.conf.settings.GEMINI_API_KEY", ""):
            with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
                GeminiProvider()

    def test_rejects_3d_output_type(self, gemini, fake_gemini_result):
        with pytest.raises(ProviderError, match="output_type='3d'"):
            gemini.generate(prompt="x", output_type="3d")

    def test_rejects_empty_prompt(self, gemini):
        with pytest.raises(ProviderError, match="prompt ne peut pas être vide"):
            gemini.generate(prompt="", output_type="2d")

    def test_generate_text_to_image(self, gemini, fake_gemini_result):
        gemini._client.models.generate_content.return_value = _mock_gemini_response(
            fake_gemini_result
        )

        result = gemini.generate(prompt="A modern house", output_type="2d")

        assert result.image_bytes == fake_gemini_result
        assert result.mime_type == "image/png"
        # Vérifie que l'appel Gemini a bien le bon model
        call = gemini._client.models.generate_content.call_args
        assert "gemini" in call.kwargs["model"]

    def test_generate_with_style_hint_enriches_prompt(self, gemini, fake_gemini_result):
        gemini._client.models.generate_content.return_value = _mock_gemini_response(
            fake_gemini_result
        )
        gemini.generate(prompt="un salon", style_hint="aquarelle")
        call = gemini._client.models.generate_content.call_args
        contents = call.kwargs["contents"]
        assert "aquarelle" in contents[0]
        assert "salon" in contents[0]

    def test_generate_image_to_image(self, gemini, fake_gemini_result):
        gemini._client.models.generate_content.return_value = _mock_gemini_response(
            fake_gemini_result
        )

        result = gemini.generate(
            prompt="Photoréaliste",
            output_type="2d",
            input_image_bytes=fake_gemini_result,
        )
        assert result.image_bytes == fake_gemini_result
        # L'image PIL doit être en 2e position dans contents
        contents = gemini._client.models.generate_content.call_args.kwargs["contents"]
        assert len(contents) == 2

    def test_invalid_input_image_raises(self, gemini):
        with pytest.raises(ProviderError, match="Image d'entrée invalide"):
            gemini.generate(prompt="x", input_image_bytes=b"not an image")

    def test_response_without_image_raises(self, gemini):
        empty = MagicMock(candidates=[MagicMock(content=MagicMock(parts=[]))])
        gemini._client.models.generate_content.return_value = empty
        with pytest.raises(ProviderError, match="Aucune image"):
            gemini.generate(prompt="x")
