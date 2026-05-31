"""Serializers DRF pour accounts."""
from __future__ import annotations

from typing import Any

from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, UserPreferences, UserSession, UserStats


# ─── User ─────────────────────────────────────────────────────────────────────
class UserStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserStats
        fields = (
            'renders_this_month',
            'renders_limit',
            'total_projects',
            'storage_used_bytes',
            'storage_limit_bytes',
            'period_started_at',
        )
        read_only_fields = fields


class UserPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreferences
        exclude = ('id', 'user', 'updated_at')


class UserSerializer(serializers.ModelSerializer):
    """Serializer principal pour /me — inclut stats + preferences en nested."""

    name = serializers.CharField(read_only=True)
    stats = UserStatsSerializer(read_only=True)
    preferences = UserPreferencesSerializer(read_only=True)

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'first_name',
            'last_name',
            'name',
            'avatar_url',
            'plan',
            'is_staff',
            'date_joined',
            'stats',
            'preferences',
        )
        read_only_fields = ('id', 'email', 'plan', 'is_staff', 'date_joined')


# ─── Register / Login ─────────────────────────────────────────────────────────
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'password', 'password_confirm')

    def validate_email(self, value: str) -> str:
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Un compte avec cet email existe déjà.')
        return value.lower()

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Les mots de passe ne correspondent pas.'})
        password_validation.validate_password(attrs['password'])
        return attrs

    def create(self, validated_data: dict[str, Any]) -> User:
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        return User.objects.create_user(password=password, **validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        user = authenticate(
            request=self.context.get('request'),
            username=attrs['email'].lower(),
            password=attrs['password'],
        )
        if not user:
            raise serializers.ValidationError('Email ou mot de passe incorrect.')
        if not user.is_active:
            raise serializers.ValidationError('Ce compte est désactivé.')
        attrs['user'] = user
        return attrs


# ─── Password reset ───────────────────────────────────────────────────────────
class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Les mots de passe ne correspondent pas.'})

        try:
            uid = force_str(urlsafe_base64_decode(attrs['uid']))
            user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError, TypeError):
            raise serializers.ValidationError({'uid': 'Lien invalide.'})

        if not default_token_generator.check_token(user, attrs['token']):
            raise serializers.ValidationError({'token': 'Token invalide ou expiré.'})

        password_validation.validate_password(attrs['password'], user=user)
        attrs['user'] = user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(min_length=8, write_only=True)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_current_password(self, value: str) -> str:
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Mot de passe actuel incorrect.')
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({'new_password_confirm': 'Les mots de passe ne correspondent pas.'})
        password_validation.validate_password(
            attrs['new_password'], user=self.context['request'].user
        )
        return attrs


# ─── Sessions ─────────────────────────────────────────────────────────────────
class UserSessionSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(read_only=True)
    is_current = serializers.SerializerMethodField()

    class Meta:
        model = UserSession
        fields = (
            'id',
            'device_name',
            'user_agent',
            'ip_address',
            'location',
            'created_at',
            'last_active',
            'is_active',
            'is_current',
        )
        read_only_fields = fields

    def get_is_current(self, obj: UserSession) -> bool:
        current_id = self.context.get('current_session_id')
        return current_id is not None and obj.pk == current_id


# ─── Helpers JWT ──────────────────────────────────────────────────────────────
def build_token_pair(user: User, session: UserSession) -> dict[str, str]:
    """Crée un couple access+refresh JWT en injectant session_id dans les claims.

    Le session_id est ajouté avant la dérivation de l'access_token pour qu'il
    soit aussi présent dans les claims de l'access token (utilisé par le
    middleware pour identifier la session courante lors des requêtes).
    """
    refresh = RefreshToken.for_user(user)
    refresh['session_id'] = session.pk
    access = refresh.access_token
    access['session_id'] = session.pk
    return {
        'access': str(access),
        'refresh': str(refresh),
    }


def encode_uid(user: User) -> str:
    return urlsafe_base64_encode(force_bytes(user.pk))
