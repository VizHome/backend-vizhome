"""Serializers DRF du panel admin (read-only, version riche pour le staff)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import AdminAuditLog, AdminDailySnapshot

User = get_user_model()


class AdminAuditLogSerializer(serializers.ModelSerializer):
    """Sérialise un log d'action admin pour la page d'audit."""

    action_label = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AdminAuditLog
        fields = (
            "id",
            "actor",
            "actor_email",
            "action",
            "action_label",
            "target_type",
            "target_id",
            "target_repr",
            "payload",
            "ip_address",
            "created_at",
        )
        read_only_fields = fields


class AdminDailySnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminDailySnapshot
        fields = ("id", "date", "payload", "created_at")
        read_only_fields = fields


class AdminUserSerializer(serializers.ModelSerializer):
    """User avec champs supplémentaires utiles à la modération."""

    storage_used_bytes = serializers.IntegerField(
        source="stats.storage_used_bytes",
        read_only=True,
        default=0,
    )
    renders_this_month = serializers.IntegerField(
        source="stats.renders_this_month",
        read_only=True,
        default=0,
    )
    total_projects = serializers.IntegerField(
        source="stats.total_projects",
        read_only=True,
        default=0,
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "pseudo",
            "first_name",
            "last_name",
            "plan",
            "is_active",
            "is_staff",
            "is_banned_from_forum",
            "date_joined",
            "last_login",
            "storage_used_bytes",
            "renders_this_month",
            "total_projects",
        )
        read_only_fields = ("id", "email", "date_joined", "last_login")


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """PATCH limité : modération (ban/unban, promouvoir staff, ban forum, pseudo).

    Le pseudo est modifiable uniquement par le staff (les users normaux
    ne peuvent pas changer leur pseudo via /me).
    """

    class Meta:
        model = User
        fields = ("is_active", "is_staff", "is_banned_from_forum", "pseudo")

    def validate_pseudo(self, value: str) -> str:
        instance = self.instance
        qs = User.objects.filter(pseudo__iexact=value)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ce pseudo est déjà pris.")
        return value


class AdminRenderSerializer(serializers.ModelSerializer):
    """Render avec email de l'auteur (pas seulement l'id)."""

    user_email = serializers.CharField(source="user.email", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = None  # rempli au runtime — voir __init__
        fields = (
            "id",
            "user_id",
            "user_email",
            "source",
            "output_type",
            "status",
            "provider",
            "prompt",
            "title",
            "error_message",
            "created_at",
            "updated_at",
            "completed_at",
        )


# `Meta.model` est résolu au runtime pour éviter un import circulaire
# (admin_panel ne doit pas charger renders au moment de la définition).
def _init_render_serializer():
    from apps.renders.models import Render

    AdminRenderSerializer.Meta.model = Render


_init_render_serializer()
