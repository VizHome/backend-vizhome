"""Serializers DRF pour le forum."""

from __future__ import annotations

from rest_framework import serializers

from .models import Category, Reply, Topic


class _AuthorMiniSerializer(serializers.Serializer):
    """Représentation publique légère d'un user (pas de données sensibles)."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    avatar_url = serializers.CharField(read_only=True)
    is_staff = serializers.BooleanField(read_only=True)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = (
            "id",
            "slug",
            "name",
            "description",
            "icon",
            "color",
            "order",
            "is_admin_only",
            "topics_count",
            "created_at",
        )
        read_only_fields = ("id", "slug", "topics_count", "created_at")


class TopicListSerializer(serializers.ModelSerializer):
    """Version allégée pour la liste — pas le contenu complet."""

    author = _AuthorMiniSerializer(read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Topic
        fields = (
            "id",
            "slug",
            "title",
            "author",
            "category_slug",
            "category_name",
            "is_pinned",
            "is_locked",
            "views_count",
            "replies_count",
            "last_reply_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class TopicDetailSerializer(serializers.ModelSerializer):
    """Version complète avec le contenu et l'auteur résolu."""

    author = _AuthorMiniSerializer(read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Topic
        fields = (
            "id",
            "slug",
            "title",
            "content",
            "author",
            "category",
            "category_slug",
            "category_name",
            "is_pinned",
            "is_locked",
            "views_count",
            "replies_count",
            "last_reply_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "slug",
            "author",
            "category_slug",
            "category_name",
            "is_pinned",
            "is_locked",
            "views_count",
            "replies_count",
            "last_reply_at",
            "created_at",
            "updated_at",
        )


class TopicCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Topic
        fields = ("category", "title", "content")

    def validate_title(self, value: str) -> str:
        if len(value.strip()) < 5:
            raise serializers.ValidationError("Titre trop court (5 caractères min).")
        return value.strip()

    def validate_content(self, value: str) -> str:
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Contenu trop court (10 caractères min).")
        return value


class ReplySerializer(serializers.ModelSerializer):
    author = _AuthorMiniSerializer(read_only=True)

    class Meta:
        model = Reply
        fields = (
            "id",
            "topic",
            "author",
            "content",
            "is_solution",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "topic",
            "author",
            "is_solution",
            "created_at",
            "updated_at",
        )


class ReplyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reply
        fields = ("content",)

    def validate_content(self, value: str) -> str:
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Réponse trop courte.")
        return value
