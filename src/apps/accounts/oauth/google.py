"""Provider Google OAuth — supporte deux flows :

- **id_token** (legacy, Google One Tap / Sign-In JS SDK) : le frontend
  envoie directement le JWT id_token reçu côté browser. On vérifie sa
  signature + audience.
- **code** (recommandé, authorization code flow) : le frontend redirige
  vers Google `/o/oauth2/v2/auth`, Google rappelle sur notre page de
  callback avec un `code`, qu'on échange ici contre un id_token via
  Google Token endpoint. Symétrique au flow GitHub.

Le flow `code` est plus robuste : pas de cookies tiers, pas de FedCM,
marche dans tous les browsers, identique au flow GitHub.
"""

from __future__ import annotations

from typing import Any

import requests
from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from .base import OAuthError, OAuthProfile, OAuthProvider


class GoogleProvider(OAuthProvider):
    name = "google"

    TOKEN_URL = "https://oauth2.googleapis.com/token"

    def exchange(self, payload: dict[str, Any]) -> OAuthProfile:
        # Branche 1 : id_token déjà reçu côté browser (One Tap / SDK SPA)
        token = payload.get("id_token")

        # Branche 2 : on a un `code` à échanger (authorization code flow)
        code = payload.get("code")
        redirect_uri = payload.get("redirect_uri")

        if not token and not code:
            raise OAuthError("Champs requis : `id_token` OU `code` + `redirect_uri`.")

        client_id = settings.GOOGLE_OAUTH_CLIENT_ID
        if not client_id:
            raise OAuthError("GOOGLE_OAUTH_CLIENT_ID non configuré côté serveur.")

        # Flow `code` → on échange contre un id_token via Google Token endpoint.
        # Nécessite le client_secret côté serveur (jamais exposé au frontend).
        if not token:
            client_secret = settings.GOOGLE_OAUTH_CLIENT_SECRET
            if not client_secret:
                raise OAuthError(
                    "GOOGLE_OAUTH_CLIENT_SECRET non configuré côté serveur "
                    "(requis pour le flow authorization code).",
                )
            if not redirect_uri:
                raise OAuthError("Le champ redirect_uri est requis avec un code.")
            try:
                resp = requests.post(
                    self.TOKEN_URL,
                    data={
                        "code": code,
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    },
                    timeout=10,
                )
            except requests.RequestException as e:
                raise OAuthError(f"Échec contact Google : {e}") from e

            # Même sur 4xx Google renvoie un JSON {error, error_description}
            # — on l'extrait au lieu d'avaler l'erreur dans raise_for_status().
            try:
                data = resp.json()
            except ValueError:
                data = {}

            if not resp.ok:
                err_code = data.get("error", f"http_{resp.status_code}")
                err_desc = data.get("error_description", resp.text[:200])
                raise OAuthError(
                    f"Google a refusé le code ({err_code}) : {err_desc}",
                )

            token = data.get("id_token")
            if not token:
                raise OAuthError(
                    f"Réponse Google sans id_token : {data}",
                )

        # Validation cryptographique : signature + issuer + audience + exp
        try:
            info = google_id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                client_id,
            )
        except ValueError as e:
            raise OAuthError(f"id_token Google invalide : {e}") from e

        if not info.get("email_verified"):
            raise OAuthError("L'email Google n'est pas vérifié.")

        return OAuthProfile(
            provider=self.name,
            provider_user_id=str(info["sub"]),
            email=info["email"].lower(),
            email_verified=True,
            first_name=info.get("given_name", ""),
            last_name=info.get("family_name", ""),
            avatar_url=info.get("picture", ""),
        )
