"""Lookup des providers IA par nom (configurable via RENDERS_DEFAULT_PROVIDER)."""

from __future__ import annotations

from .base import BaseProvider, ProviderError
from .gemini import GeminiProvider

_PROVIDERS: dict[str, type[BaseProvider]] = {
    'gemini': GeminiProvider,
    # 'openai': OpenAIProvider,       # à ajouter plus tard
    # 'replicate': ReplicateProvider, # à ajouter plus tard
}


def get_provider(name: str) -> BaseProvider:
    """Instancie un provider par son nom.

    Raises ProviderError si le nom est inconnu.
    """
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ProviderError(
            f"Provider IA inconnu : '{name}'. Disponibles : {sorted(_PROVIDERS.keys())}"
        )
    return cls()


def available_providers() -> list[str]:
    return sorted(_PROVIDERS.keys())
