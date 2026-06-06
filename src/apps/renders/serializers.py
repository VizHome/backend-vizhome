"""Serializers DRF pour l'app renders."""

from __future__ import annotations

import base64
import binascii
from typing import Any

from django.core.files.base import ContentFile
from rest_framework import serializers

from .models import Render
from .providers.registry import get_provider


class RenderSerializer(serializers.ModelSerializer):
    """Serializer en lecture — utilisé pour list, retrieve et response create."""

    result_url = serializers.SerializerMethodField()
    input_image_url = serializers.SerializerMethodField()
    is_terminal = serializers.BooleanField(read_only=True)

    class Meta:
        model = Render
        fields = (
            "id",
            "source",
            "output_type",
            "prompt",
            "style_hint",
            "title",
            "status",
            "is_terminal",
            "result_url",
            "input_image_url",
            "error_message",
            "provider",
            "created_at",
            "updated_at",
            "completed_at",
        )
        read_only_fields = fields

    def _absolute(self, url: str | None) -> str | None:
        if not url:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url

    def get_result_url(self, obj: Render) -> str | None:
        return self._absolute(obj.result_image.url) if obj.result_image else None

    def get_input_image_url(self, obj: Render) -> str | None:
        return self._absolute(obj.input_image.url) if obj.input_image else None


class RenderUpdateSerializer(serializers.ModelSerializer):
    """PATCH limité : seul le titre est modifiable post-création."""

    class Meta:
        model = Render
        fields = ("title",)


class RenderCreateSerializer(serializers.ModelSerializer):
    """Input pour POST /renders. Accepte sketch_base64 pour les modes sketch/screenshot."""

    sketch_base64 = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )

    class Meta:
        model = Render
        fields = (
            "source",
            "output_type",
            "prompt",
            "style_hint",
            "title",
            "sketch_base64",
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        source = attrs["source"]
        prompt = (attrs.get("prompt") or "").strip()
        sketch = attrs.get("sketch_base64")
        style_hint = (attrs.get("style_hint") or "").strip()

        if source == Render.Source.PROMPT and not prompt:
            raise serializers.ValidationError(
                {"prompt": "Prompt requis pour source=prompt."}
            )
        if source in (Render.Source.SKETCH, Render.Source.SCREENSHOT) and not sketch:
            raise serializers.ValidationError(
                {"sketch_base64": f"sketch_base64 requis pour source={source}."}
            )
        if source in (Render.Source.SKETCH, Render.Source.SCREENSHOT) and not (
            prompt or style_hint
        ):
            raise serializers.ValidationError(
                "Au moins un prompt ou un style_hint est requis pour interpréter le croquis."
            )

        # Validation provider : output_type doit être supporté
        #
        # Note : on NE capture PAS ProviderError ici — on le laisse remonter
        # jusqu'à la view qui le traduit en 503 + code structuré (pattern
        # cohérent avec _stripe_unavailable_response côté billing). Capturer
        # ici produirait un 400 + non_field_errors, qui est sémantiquement
        # faux (l'input client est correct, c'est le serveur qui n'a pas la
        # clé d'API).
        from django.conf import settings

        provider = get_provider(settings.RENDERS_DEFAULT_PROVIDER)

        if not provider.supports(attrs.get("output_type", Render.OutputType.IMAGE_2D)):
            raise serializers.ValidationError(
                {
                    "output_type": (
                        f"Le provider '{provider.name}' ne supporte pas encore "
                        f"output_type='{attrs.get('output_type')}'."
                    )
                }
            )

        return attrs

    def create(self, validated_data: dict[str, Any]) -> Render:
        sketch_b64 = validated_data.pop("sketch_base64", None)
        user = self.context["request"].user

        # Enforce quota
        stats = user.stats
        if stats.renders_this_month >= stats.renders_limit:
            raise serializers.ValidationError(
                {"detail": "Quota mensuel de rendus atteint.", "code": "quota_exceeded"}
            )

        render = Render.objects.create(user=user, **validated_data)

        if sketch_b64:
            image_bytes = _decode_base64_image(sketch_b64)
            render.input_image.save(f"sketch_{render.pk}.png", ContentFile(image_bytes))

        return render


def _decode_base64_image(b64: str) -> bytes:
    """Décode une data URI ou un base64 brut en bytes."""
    # Strip "data:image/png;base64," si présent
    if "," in b64 and b64.lstrip().startswith("data:"):
        b64 = b64.split(",", 1)[1]
    try:
        return base64.b64decode(b64, validate=True)
    except binascii.Error as e:
        raise serializers.ValidationError(
            {"sketch_base64": f"Base64 invalide : {e}"}
        ) from e
