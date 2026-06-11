"""Interface abstraite pour les providers OAuth.

Chaque provider doit exposer une méthode `exchange(payload)` qui prend les
données envoyées par le frontend (id_token, code, redirect_uri…) et retourne
un OAuthProfile normalisé.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class OAuthError(Exception):
    """Levée quand l'échange OAuth échoue (token invalide, provider HS, etc.)."""


@dataclass(frozen=True)
class OAuthProfile:
    """Profil utilisateur normalisé renvoyé par chaque provider."""

    provider: str
    provider_user_id: str  # id unique côté provider
    email: str
    email_verified: bool
    first_name: str = ''
    last_name: str = ''
    avatar_url: str = ''


class OAuthProvider(ABC):
    name: str

    @abstractmethod
    def exchange(self, payload: dict[str, Any]) -> OAuthProfile:
        """Convertit le payload du frontend en profil normalisé."""
        ...
