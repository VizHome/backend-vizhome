"""Vues DRF pour accounts : auth + me + sessions."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .lockout import drf_lockout_response
from .models import User, UserSession
from .serializers import (
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UserPreferencesSerializer,
    UserSerializer,
    UserSessionSerializer,
    build_token_pair,
    encode_uid,
)
from .throttling import ForgotPasswordThrottle, LoginThrottle, RegisterThrottle
from .utils import get_client_ip, parse_device_name


# ─── Helper : crée une session + tokens ──────────────────────────────────────
def _issue_tokens_for_user(user: User, request: Request) -> dict[str, Any]:
    """Crée une UserSession + un couple access/refresh."""
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    session = UserSession.objects.create(
        user=user,
        refresh_jti="pending",  # placeholder, mis à jour ci-dessous
        device_name=parse_device_name(user_agent),
        user_agent=user_agent,
        ip_address=get_client_ip(request),
    )
    tokens = build_token_pair(user, session)

    # Récupère le jti depuis le refresh token et persiste-le
    from rest_framework_simplejwt.tokens import RefreshToken as RT

    refresh_obj = RT(tokens["refresh"])
    session.refresh_jti = refresh_obj["jti"]
    session.save(update_fields=["refresh_jti"])

    return tokens


# ─── Auth ─────────────────────────────────────────────────────────────────────
class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [RegisterThrottle]

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        tokens = _issue_tokens_for_user(user, request)
        return Response(
            {"user": UserSerializer(user).data, **tokens},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request: Request) -> Response:
        # Vérif lockout axes AVANT d'appeler authenticate() — Django capture
        # PermissionDenied en interne et le convertit en None, donc on ne peut
        # pas distinguer "verrouillé" de "mauvais mdp" après authenticate.
        from axes.handlers.proxy import AxesProxyHandler
        from django.contrib.auth.signals import user_logged_in

        email = (request.data.get("email") or "").lower()
        credentials = {"username": email}
        if not AxesProxyHandler.is_allowed(request, credentials):
            return drf_lockout_response()

        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        # Émet user_logged_in pour que axes reset son compteur (AXES_RESET_ON_SUCCESS).
        # DRF + JWT n'appellent jamais auth.login() qui émet ce signal nativement.
        user_logged_in.send(sender=User, request=request, user=user)

        # Si 2FA activé, renvoie un challenge au lieu des tokens
        from .two_factor import generate_challenge_token, user_has_active_2fa

        if user_has_active_2fa(user):
            challenge = generate_challenge_token(user.pk)
            return Response(
                {
                    "require_2fa": True,
                    "challenge_token": challenge,
                    "expires_in": 300,
                }
            )

        # Met à jour last_login
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        tokens = _issue_tokens_for_user(user, request)
        return Response({"user": UserSerializer(user).data, **tokens})


class LogoutView(APIView):
    """Blacklist le refresh token et marque la session comme révoquée."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "Refresh token requis."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            token = RefreshToken(refresh_token)
            jti = token["jti"]
            token.blacklist()
        except TokenError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        UserSession.objects.filter(refresh_jti=jti, user=request.user).update(
            revoked_at=timezone.now()
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ForgotPasswordThrottle]

    def post(self, request: Request) -> Response:
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()

        # Ne pas leaker l'existence du compte : toujours répondre 204
        user = User.objects.filter(email=email).first()
        if user and user.is_active:
            uid = encode_uid(user)
            token = default_token_generator.make_token(user)
            reset_url = (
                f"{settings.FRONTEND_URL}/auth/reset-password?uid={uid}&token={token}"
            )

            send_mail(
                subject="Réinitialisation de votre mot de passe VizHome",
                message=(
                    f"Bonjour,\n\n"
                    f"Vous avez demandé une réinitialisation de votre mot de passe.\n"
                    f"Cliquez sur ce lien pour en choisir un nouveau :\n\n{reset_url}\n\n"
                    f"Si vous n'êtes pas à l'origine de cette demande, ignorez cet email."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["password"])
        user.save()

        # Révoque toutes les sessions existantes pour ce user
        UserSession.objects.filter(user=user, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Me ───────────────────────────────────────────────────────────────────────
class MeView(generics.RetrieveUpdateAPIView):
    """GET = profil complet (user + stats + preferences), PATCH = update profil."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self) -> User:
        return self.request.user

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return UpdateMeSerializer
        return UserSerializer


class UpdateMeSerializer(UserSerializer):
    """Subset des champs modifiables via PATCH /me."""

    class Meta(UserSerializer.Meta):
        fields = ("first_name", "last_name", "avatar_url")


class PreferencesView(generics.RetrieveUpdateAPIView):
    """GET/PATCH des préférences."""

    serializer_class = UserPreferencesSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user.preferences


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Sessions ─────────────────────────────────────────────────────────────────
class SessionListView(generics.ListAPIView):
    serializer_class = UserSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserSession.objects.filter(
            user=self.request.user, revoked_at__isnull=True
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        # Extrait session_id depuis l'access token validé par SimpleJWT
        auth = self.request.auth
        ctx["current_session_id"] = auth.payload.get("session_id") if auth else None
        return ctx


class SessionDetailView(APIView):
    """Révoque une session par son id (blacklist le refresh token associé)."""

    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, pk: int) -> Response:
        try:
            session = UserSession.objects.get(
                pk=pk, user=request.user, revoked_at__isnull=True
            )
        except UserSession.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # Blacklist tous les outstanding tokens avec ce jti
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )

        outstanding = OutstandingToken.objects.filter(jti=session.refresh_jti)
        for token in outstanding:
            BlacklistedToken.objects.get_or_create(token=token)

        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
