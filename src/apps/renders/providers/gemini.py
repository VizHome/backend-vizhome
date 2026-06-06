"""Provider Gemini — utilise gemini-2.5-flash-image-preview pour text-to-image et image-to-image."""

from __future__ import annotations

import io

from django.conf import settings
from google import genai
from google.genai import types
from PIL import Image

from .base import BaseProvider, GenerationResult, ProviderError


class GeminiProvider(BaseProvider):
    """Implémentation Gemini (Google).

    Le modèle gemini-2.5-flash-image-preview accepte du texte seul OU
    texte + image (image-to-image). Il retourne une image en inline_data.
    """

    name = "gemini"
    supported_output_types = {"2d"}

    def __init__(self) -> None:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            raise ProviderError(
                "GEMINI_API_KEY non configuré. "
                "Renseigne la variable dans .env pour activer le provider Gemini."
            )
        self._client = genai.Client(api_key=api_key)
        self._model = settings.GEMINI_IMAGE_MODEL

    def generate(
        self,
        prompt: str,
        output_type: str = "2d",
        input_image_bytes: bytes | None = None,
        style_hint: str = "",
    ) -> GenerationResult:
        if not self.supports(output_type):
            raise ProviderError(
                f"Gemini ne supporte pas output_type='{output_type}'. "
                f"Supportés : {sorted(self.supported_output_types)}"
            )

        # Construction du prompt enrichi
        full_prompt = prompt or ""
        if style_hint:
            full_prompt = (
                f"Style : {style_hint}. {full_prompt}".strip()
                if full_prompt
                else f"Restitue cette image avec ce style : {style_hint}."
            )
        if not full_prompt:
            raise ProviderError("Le prompt ne peut pas être vide.")

        contents: list = [full_prompt]
        if input_image_bytes:
            try:
                img = Image.open(io.BytesIO(input_image_bytes))
                img.load()  # force decode → erreur explicite si bytes invalides
                contents.append(img)
            except Exception as e:
                raise ProviderError(f"Image d'entrée invalide : {e}") from e

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )
        except Exception as e:
            raise ProviderError(f"Erreur appel Gemini : {e}") from e

        # Extraction de l'image inline depuis la réponse
        image_bytes, mime_type = self._extract_image(response)
        return GenerationResult(
            image_bytes=image_bytes,
            mime_type=mime_type,
            provider_response_id=getattr(response, "response_id", "") or "",
        )

    @staticmethod
    def _extract_image(response) -> tuple[bytes, str]:
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            if not content:
                continue
            for part in content.parts or []:
                inline = getattr(part, "inline_data", None)
                if inline and inline.data:
                    return inline.data, inline.mime_type or "image/png"
        raise ProviderError(
            "Aucune image dans la réponse Gemini (probablement bloquée par les safety filters)."
        )
