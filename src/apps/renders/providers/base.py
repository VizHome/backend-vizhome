"""Interface abstraite pour les providers IA de génération de rendus.

Chaque provider doit déclarer :
- son nom (utilisé par RENDERS_DEFAULT_PROVIDER et le registry)
- les output_types qu'il supporte
- une méthode `generate()` qui retourne un GenerationResult ou raise ProviderError
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class ProviderError(Exception):
    """Erreur côté provider (config manquante, API down, contenu refusé, etc.)."""


@dataclass(frozen=True)
class GenerationResult:
    """Résultat normalisé d'une génération IA."""

    image_bytes: bytes
    mime_type: str  # ex: 'image/png', 'image/jpeg'
    provider_response_id: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseProvider(ABC):
    name: str
    supported_output_types: set[str]

    @abstractmethod
    def generate(
        self,
        prompt: str,
        output_type: str = '2d',
        input_image_bytes: bytes | None = None,
        style_hint: str = '',
    ) -> GenerationResult:
        """Génère un rendu à partir d'un prompt (+ image optionnelle pour img2img)."""
        ...

    def supports(self, output_type: str) -> bool:
        return output_type in self.supported_output_types
