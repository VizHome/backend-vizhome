"""Classe d'authentification JWT qui accepte les comptes désactivés.

Utilisée uniquement par l'endpoint d'annulation de suppression de compte
(`/me/delete-account/cancel`). En effet, dès qu'une demande de suppression
est posée, `is_active=False` ; sans cette classe, le user ne pourrait
plus annuler car la `JWTAuthentication` standard refuse les comptes
inactifs.

Sécurité : on impose toujours la validité du token JWT (signature +
expiration). On garde aussi le filet `user.gdpr_deletion_request` côté
view : si pas de DeletionRequest pour ce user, la cancel renverra 404.
"""

from __future__ import annotations

from rest_framework_simplejwt.authentication import JWTAuthentication


class JWTAuthenticationAllowInactive(JWTAuthentication):
    """JWTAuthentication sans le check `is_active=True`.

    On override `get_user` au lieu de patcher le user en place pour ne
    pas altérer l'état attendu ailleurs.
    """

    def get_user(self, validated_token):
        from django.contrib.auth import get_user_model
        from rest_framework_simplejwt.exceptions import (
            AuthenticationFailed,
            InvalidToken,
        )
        from rest_framework_simplejwt.settings import api_settings

        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError as exc:
            raise InvalidToken(
                'Token contained no recognizable user identification'
            ) from exc

        user_model = get_user_model()
        try:
            user = user_model.objects.get(**{api_settings.USER_ID_FIELD: user_id})
        except user_model.DoesNotExist as exc:
            raise AuthenticationFailed('User not found') from exc

        # ⚠️ Pas de check `is_active` : c'est le but de cette classe.
        return user
