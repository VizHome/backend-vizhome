"""Endpoint d'échange OAuth : POST /auth/oauth/{provider}/exchange."""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import User
from ..serializers import UserSerializer
from ..views import _issue_tokens_for_user
from .base import OAuthError
from .registry import get_provider


class OAuthExchangeView(APIView):
    """Échange un payload OAuth (id_token ou code) contre nos JWT.

    POST /auth/oauth/google/exchange   { "id_token": "..." }
    POST /auth/oauth/github/exchange   { "code": "...", "redirect_uri": "..." }
    """

    permission_classes = [AllowAny]

    def post(self, request: Request, provider: str) -> Response:
        oauth_provider = get_provider(provider)
        if not oauth_provider:
            return Response(
                {"detail": f"Provider OAuth inconnu : {provider}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            profile = oauth_provider.exchange(request.data)
        except OAuthError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if not profile.email_verified:
            return Response(
                {"detail": "Email non vérifié auprès du provider."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Find or create
        user, created = User.objects.get_or_create(
            email=profile.email,
            defaults={
                "first_name": profile.first_name,
                "last_name": profile.last_name,
                "avatar_url": profile.avatar_url,
                "is_active": True,
            },
        )

        # Si user créé, on définit un mot de passe random (forçant la connexion OAuth)
        if created:
            user.set_unusable_password()
            user.save()

        tokens = _issue_tokens_for_user(user, request)
        return Response(
            {
                "user": UserSerializer(user).data,
                "created": created,
                **tokens,
            },
            status=status.HTTP_200_OK,
        )
