"""Lookup des providers OAuth par nom."""

from __future__ import annotations

from .base import OAuthProvider
from .github import GitHubProvider
from .google import GoogleProvider

_PROVIDERS: dict[str, type[OAuthProvider]] = {
    "google": GoogleProvider,
    "github": GitHubProvider,
}


def get_provider(name: str) -> OAuthProvider | None:
    cls = _PROVIDERS.get(name)
    return cls() if cls else None
