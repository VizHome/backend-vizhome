"""Provider Google OAuth — vérifie un id_token côté SPA (Google Sign-In)."""
from __future__ import annotations

from typing import Any

from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from .base import OAuthError, OAuthProfile, OAuthProvider


class GoogleProvider(OAuthProvider):
    """Le frontend appelle Google Sign-In, récupère un id_token JWT, et nous l'envoie.

    On le vérifie en cryptographie via la lib google-auth, qui valide :
    - signature
    - issuer (accounts.google.com)
    - audience (notre client_id)
    - expiration
    """

    name = 'google'

    def exchange(self, payload: dict[str, Any]) -> OAuthProfile:
        token = payload.get('id_token')
        if not token:
            raise OAuthError('Le champ id_token est requis.')

        client_id = settings.GOOGLE_OAUTH_CLIENT_ID
        if not client_id:
            raise OAuthError('GOOGLE_OAUTH_CLIENT_ID non configuré côté serveur.')

        try:
            info = google_id_token.verify_oauth2_token(
                token, google_requests.Request(), client_id
            )
        except ValueError as e:
            raise OAuthError(f'id_token Google invalide : {e}') from e

        if not info.get('email_verified'):
            raise OAuthError("L'email Google n'est pas vérifié.")

        return OAuthProfile(
            provider=self.name,
            provider_user_id=str(info['sub']),
            email=info['email'].lower(),
            email_verified=True,
            first_name=info.get('given_name', ''),
            last_name=info.get('family_name', ''),
            avatar_url=info.get('picture', ''),
        )
