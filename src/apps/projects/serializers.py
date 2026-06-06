"""Serializers DRF de l'app projects."""

from __future__ import annotations

import os

from rest_framework import serializers

from .models import (
    Annotation,
    ImportedModel,
    Project,
    Scene,
    ShareLink,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _absolute(request, url: str | None) -> str | None:
    if not url:
        return None
    return request.build_absolute_uri(url) if request else url


# ─── Project ──────────────────────────────────────────────────────────────────
class ProjectListSerializer(serializers.ModelSerializer):
    """Vue compacte pour le listing."""

    thumbnail_url = serializers.SerializerMethodField()
    models_count = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            "id",
            "title",
            "description",
            "thumbnail_url",
            "is_archived",
            "models_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "thumbnail_url",
            "models_count",
            "created_at",
            "updated_at",
        )

    def get_thumbnail_url(self, obj: Project) -> str | None:
        return (
            _absolute(self.context.get("request"), obj.thumbnail.url)
            if obj.thumbnail
            else None
        )

    def get_models_count(self, obj: Project) -> int:
        return obj.imported_models.count()


class ProjectDetailSerializer(ProjectListSerializer):
    """Vue détaillée incluant la scène + les modèles + annotations."""

    scene = serializers.SerializerMethodField()
    imported_models = serializers.SerializerMethodField()
    annotations = serializers.SerializerMethodField()

    class Meta(ProjectListSerializer.Meta):
        fields = (*ProjectListSerializer.Meta.fields, "scene", "imported_models", "annotations")

    def get_scene(self, obj: Project) -> dict:
        return SceneSerializer(obj.scene).data

    def get_imported_models(self, obj: Project) -> list[dict]:
        return ImportedModelSerializer(
            obj.imported_models.all(), many=True, context=self.context
        ).data

    def get_annotations(self, obj: Project) -> list[dict]:
        return AnnotationSerializer(obj.annotations.all(), many=True).data


class ProjectCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ("title", "description", "is_archived")


# ─── Scene ────────────────────────────────────────────────────────────────────
class SceneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scene
        fields = ("data", "version", "updated_at")
        read_only_fields = ("version", "updated_at")


# ─── ImportedModel ────────────────────────────────────────────────────────────
class ImportedModelSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    mtl_file_url = serializers.SerializerMethodField()

    class Meta:
        model = ImportedModel
        fields = (
            "id",
            "name",
            "format",
            "file_url",
            "mtl_file_url",
            "file_size_bytes",
            "position",
            "rotation",
            "scale",
            "created_at",
        )
        read_only_fields = (
            "id",
            "file_url",
            "mtl_file_url",
            "file_size_bytes",
            "created_at",
        )

    def get_file_url(self, obj: ImportedModel) -> str | None:
        return (
            _absolute(self.context.get("request"), obj.file.url) if obj.file else None
        )

    def get_mtl_file_url(self, obj: ImportedModel) -> str | None:
        return (
            _absolute(self.context.get("request"), obj.mtl_file.url)
            if obj.mtl_file
            else None
        )


class ImportedModelUploadSerializer(serializers.Serializer):
    """Upload classique (multipart). Pour les fichiers < ~10MB."""

    name = serializers.CharField(max_length=200)
    file = serializers.FileField()
    mtl_file = serializers.FileField(required=False)

    def validate_file(self, value):
        ext = os.path.splitext(value.name)[1].lstrip(".").lower()
        if ext not in {choice.value for choice in ImportedModel.Format}:
            raise serializers.ValidationError(
                f"Format non supporté : .{ext}. "
                f"Formats acceptés : .glb, .gltf, .obj, .fbx, .stl"
            )
        return value


class PresignedUploadRequestSerializer(serializers.Serializer):
    """Demande une URL pré-signée pour upload direct vers MinIO."""

    name = serializers.CharField(max_length=200)
    file_name = serializers.CharField(max_length=200)
    file_size_bytes = serializers.IntegerField(min_value=1)
    content_type = serializers.CharField(
        max_length=100, required=False, default="application/octet-stream"
    )

    def validate_file_name(self, value):
        ext = os.path.splitext(value)[1].lstrip(".").lower()
        if ext not in {choice.value for choice in ImportedModel.Format}:
            raise serializers.ValidationError(
                f"Format non supporté : .{ext}. "
                f"Formats acceptés : .glb, .gltf, .obj, .fbx, .stl"
            )
        return value


class PresignedUploadConfirmSerializer(serializers.Serializer):
    """Confirmation post-upload : enregistre l'ImportedModel en DB."""

    name = serializers.CharField(max_length=200)
    key = serializers.CharField(max_length=500)  # la key S3 retournée par /upload-url
    mtl_key = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ImportedModelUpdateSerializer(serializers.ModelSerializer):
    """PATCH — uniquement transform et nom."""

    class Meta:
        model = ImportedModel
        fields = ("name", "position", "rotation", "scale")


# ─── Annotation ───────────────────────────────────────────────────────────────
class AnnotationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Annotation
        fields = (
            "id",
            "type",
            "position",
            "content",
            "color",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


# ─── ShareLink ────────────────────────────────────────────────────────────────
class ShareLinkSerializer(serializers.ModelSerializer):
    share_url = serializers.SerializerMethodField()
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = ShareLink
        fields = (
            "id",
            "token",
            "share_url",
            "permission",
            "expires_at",
            "last_used_at",
            "created_at",
            "is_expired",
        )
        read_only_fields = (
            "id",
            "token",
            "share_url",
            "last_used_at",
            "created_at",
            "is_expired",
        )

    def get_share_url(self, obj: ShareLink) -> str:
        from django.conf import settings

        return f"{settings.FRONTEND_URL}/shared/{obj.token}"


class ShareLinkCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShareLink
        fields = ("permission", "expires_at")
