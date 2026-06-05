"""2FA TOTP via django-otp.

Flow :
1. POST /me/2fa/setup → crée un TOTPDevice non confirmé, renvoie secret + QR code
2. POST /me/2fa/verify-setup avec un code → confirme et active le device
3. POST /me/2fa/disable → supprime le device

Login avec 2FA actif :
- POST /auth/login → renvoie {require_2fa: true, challenge_token} (pas d'access/refresh)
- POST /auth/2fa/verify avec challenge_token + code → renvoie les tokens
"""

from __future__ import annotations

import base64
import io
import secrets
import time
from typing import Any

import qrcode
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .serializers import UserSerializer, build_token_pair
from .throttling import LoginThrottle


# ─── Helpers ──────────────────────────────────────────────────────────────────
def user_has_active_2fa(user: User) -> bool:
    return TOTPDevice.objects.filter(user=user, confirmed=True).exists()


def get_user_totp_device(
    user: User, confirmed: bool | None = True
) -> TOTPDevice | None:
    qs = TOTPDevice.objects.filter(user=user)
    if confirmed is not None:
        qs = qs.filter(confirmed=confirmed)
    return qs.first()


def generate_challenge_token(user_id: int) -> str:
    """Token éphémère (5 min) qui prouve qu'on a passé l'étape 1 du login 2FA."""
    token = secrets.token_urlsafe(32)
    cache.set(f"2fa_challenge:{token}", user_id, timeout=300)
    return token


def consume_challenge_token(token: str) -> int | None:
    user_id = cache.get(f"2fa_challenge:{token}")
    if user_id is not None:
        cache.delete(f"2fa_challenge:{token}")
    return user_id


def build_qr_code_data_uri(uri: str) -> str:
    """Génère un QR code en data URI (base64 PNG) depuis l'otpauth:// URI."""
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


# ─── Serializers ──────────────────────────────────────────────────────────────
class TwoFactorVerifySerializer(serializers.Serializer):
    code = serializers.CharField(min_length=6, max_length=6)


class TwoFactorLoginSerializer(serializers.Serializer):
    challenge_token = serializers.CharField()
    code = serializers.CharField(min_length=6, max_length=6)


# ─── Setup / activation ───────────────────────────────────────────────────────
class Setup2FAView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        user = request.user

        if user_has_active_2fa(user):
            return Response(
                {"detail": "2FA déjà activé. Désactivez-le avant de re-configurer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Supprime tout device non confirmé précédent
        TOTPDevice.objects.filter(user=user, confirmed=False).delete()

        # Crée un nouveau device (non confirmé)
        device = TOTPDevice.objects.create(
            user=user,
            name=f"TOTP {user.email}",
            confirmed=False,
        )

        return Response(
            {
                "secret": base64.b32encode(bytes.fromhex(device.key)).decode(),
                "qr_code": build_qr_code_data_uri(device.config_url),
                "otpauth_uri": device.config_url,
            }
        )


class VerifySetup2FAView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = TwoFactorVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        device = get_user_totp_device(request.user, confirmed=False)
        if not device:
            return Response(
                {
                    "detail": "Aucune configuration 2FA en attente. Appelez /me/2fa/setup d'abord."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not device.verify_token(serializer.validated_data["code"]):
            return Response(
                {"detail": "Code invalide."}, status=status.HTTP_400_BAD_REQUEST
            )

        device.confirmed = True
        device.save()

        # Met à jour la préférence du user
        prefs = request.user.preferences
        prefs.two_factor_enabled = True
        prefs.save(update_fields=["two_factor_enabled"])

        return Response({"detail": "2FA activé avec succès."})


class Disable2FAView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = TwoFactorVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        device = get_user_totp_device(request.user, confirmed=True)
        if not device:
            return Response(
                {"detail": "2FA non activé."}, status=status.HTTP_400_BAD_REQUEST
            )

        # Exige un code valide pour désactiver (sécurité)
        if not device.verify_token(serializer.validated_data["code"]):
            return Response(
                {"detail": "Code invalide."}, status=status.HTTP_400_BAD_REQUEST
            )

        device.delete()

        prefs = request.user.preferences
        prefs.two_factor_enabled = False
        prefs.save(update_fields=["two_factor_enabled"])

        return Response({"detail": "2FA désactivé."})


# ─── Login 2FA ────────────────────────────────────────────────────────────────
class Verify2FALoginView(APIView):
    """Étape 2 du login : échange challenge_token + code TOTP contre des JWT."""

    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request: Request) -> Response:
        serializer = TwoFactorLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = consume_challenge_token(serializer.validated_data["challenge_token"])
        if user_id is None:
            return Response(
                {"detail": "Challenge invalide ou expiré."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return Response(
                {"detail": "Utilisateur introuvable."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        device = get_user_totp_device(user, confirmed=True)
        if not device or not device.verify_token(serializer.validated_data["code"]):
            return Response(
                {"detail": "Code 2FA invalide."}, status=status.HTTP_400_BAD_REQUEST
            )

        # Import local pour éviter le cycle avec views.py
        from .views import _issue_tokens_for_user

        tokens = _issue_tokens_for_user(user, request)
        return Response({"user": UserSerializer(user).data, **tokens})
