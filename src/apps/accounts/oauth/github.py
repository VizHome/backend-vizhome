"""Provider GitHub OAuth — authorization code flow."""

from __future__ import annotations

from typing import Any

import requests
from django.conf import settings

from .base import OAuthError, OAuthProfile, OAuthProvider


class GitHubProvider(OAuthProvider):
    """Le frontend redirige vers GitHub → reçoit un `code` en callback → l'envoie ici.

    On échange le code contre un access_token GitHub, puis on fetch /user et
    /user/emails.
    """

    name = "github"

    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USER_URL = "https://api.github.com/user"
    EMAILS_URL = "https://api.github.com/user/emails"

    def exchange(self, payload: dict[str, Any]) -> OAuthProfile:
        code = payload.get("code")
        redirect_uri = payload.get("redirect_uri")
        if not code:
            raise OAuthError("Le champ code est requis.")

        client_id = settings.GITHUB_OAUTH_CLIENT_ID
        client_secret = settings.GITHUB_OAUTH_CLIENT_SECRET
        if not (client_id and client_secret):
            raise OAuthError("GitHub OAuth non configuré côté serveur.")

        # 1. code → access_token
        try:
            resp = requests.post(
                self.TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                timeout=10,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise OAuthError(f"Échec contact GitHub : {e}") from e

        data = resp.json()
        access_token = data.get("access_token")
        if not access_token:
            raise OAuthError(
                f"GitHub a refusé le code : {data.get('error_description', '?')}"
            )

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        }

        # 2. /user
        try:
            user_resp = requests.get(self.USER_URL, headers=headers, timeout=10)
            user_resp.raise_for_status()
        except requests.RequestException as e:
            raise OAuthError(f"Impossible de récupérer le profil GitHub : {e}") from e
        user = user_resp.json()

        # 3. /user/emails (email principal peut être privé sur /user)
        email = user.get("email")
        email_verified = False
        if not email:
            try:
                emails_resp = requests.get(self.EMAILS_URL, headers=headers, timeout=10)
                emails_resp.raise_for_status()
                primary = next(
                    (
                        e
                        for e in emails_resp.json()
                        if e.get("primary") and e.get("verified")
                    ),
                    None,
                )
                if primary:
                    email = primary["email"]
                    email_verified = True
            except requests.RequestException as e:
                raise OAuthError(
                    f"Impossible de récupérer les emails GitHub : {e}"
                ) from e
        else:
            email_verified = True  # GitHub valide les emails à l'inscription

        if not email:
            raise OAuthError("Impossible de récupérer un email vérifié depuis GitHub.")

        # Split name → first/last
        full_name = (user.get("name") or "").strip()
        parts = full_name.split(" ", 1)
        first = parts[0] if parts else ""
        last = parts[1] if len(parts) > 1 else ""

        return OAuthProfile(
            provider=self.name,
            provider_user_id=str(user["id"]),
            email=email.lower(),
            email_verified=email_verified,
            first_name=first,
            last_name=last,
            avatar_url=user.get("avatar_url", ""),
        )
