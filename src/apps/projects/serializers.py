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
            'id',
            'title',
            'description',
            'thumbnail_url',
            'is_archived',
            'models_count',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'thumbnail_url',
            'models_count',
            'created_at',
            'updated_at',
        )

    def get_thumbnail_url(self, obj: Project) -> str | None:
        return _absolute(self.context.get('request'), obj.thumbnail.url) if obj.thumbnail else None

    def get_models_count(self, obj: Project) -> int:
        return obj.imported_models.count()


class ProjectDetailSerializer(ProjectListSerializer):
    """Vue détaillée incluant la scène + les modèles + annotations."""

    scene = serializers.SerializerMethodField()
    imported_models = serializers.SerializerMethodField()
    annotations = serializers.SerializerMethodField()

    class Meta(ProjectListSerializer.Meta):
        fields = (
            *ProjectListSerializer.Meta.fields,
            'scene',
            'imported_models',
            'annotations',
        )

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
        fields = ('title', 'description', 'is_archived')


# ─── Scene ────────────────────────────────────────────────────────────────────
class SceneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scene
        fields = ('data', 'version', 'updated_at')
        read_only_fields = ('version', 'updated_at')


# ─── ImportedModel ────────────────────────────────────────────────────────────
class ImportedModelSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    mtl_file_url = serializers.SerializerMethodField()

    class Meta:
        model = ImportedModel
        fields = (
            'id',
            'name',
            'format',
            'file_url',
            'mtl_file_url',
            'file_size_bytes',
            'position',
            'rotation',
            'scale',
            'created_at',
        )
        read_only_fields = (
            'id',
            'file_url',
            'mtl_file_url',
            'file_size_bytes',
            'created_at',
        )

    def get_file_url(self, obj: ImportedModel) -> str | None:
        return _absolute(self.context.get('request'), obj.file.url) if obj.file else None

    def get_mtl_file_url(self, obj: ImportedModel) -> str | None:
        return _absolute(self.context.get('request'), obj.mtl_file.url) if obj.mtl_file else None


class ImportedModelUploadSerializer(serializers.Serializer):
    """Upload classique (multipart). Pour les fichiers < ~10MB."""

    name = serializers.CharField(max_length=200)
    file = serializers.FileField()
    mtl_file = serializers.FileField(required=False)

    def validate_file(self, value):
        ext = os.path.splitext(value.name)[1].lstrip('.').lower()
        if ext not in {choice.value for choice in ImportedModel.Format}:
            raise serializers.ValidationError(
                f'Format non supporté : .{ext}. Formats acceptés : .glb, .gltf, .obj, .fbx, .stl'
            )
        return value


class PresignedUploadRequestSerializer(serializers.Serializer):
    """Demande une URL pré-signée pour upload direct vers MinIO.

    Sécurité :
    - Extension whitelist (.glb, .gltf, .obj, .fbx, .stl)
    - Filename sanitisé (refuse path traversal et caractères dangereux)
    - Taille max : 100 MB (les modèles 3D plus gros doivent passer par
      l'upload S3 multipart, pas encore implémenté côté frontend)
    - content_type whitelist alignée sur l'extension demandée
    """

    # 100 MB — au delà, on doit basculer en multipart upload S3
    MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024

    # Mapping extension → content-types acceptables
    # Le `application/octet-stream` est toléré partout (browsers le retournent
    # pour les formats peu courants) mais on refuse les types clairement faux
    # (un .glb avec content-type `text/html` est suspect).
    CONTENT_TYPE_WHITELIST = {
        'glb': {'model/gltf-binary', 'application/octet-stream'},
        'gltf': {'model/gltf+json', 'application/json', 'application/octet-stream'},
        'obj': {'text/plain', 'model/obj', 'application/octet-stream'},
        'fbx': {'application/octet-stream'},
        'stl': {'model/stl', 'application/sla', 'application/octet-stream'},
    }

    name = serializers.CharField(max_length=200)
    file_name = serializers.CharField(max_length=200)
    file_size_bytes = serializers.IntegerField(min_value=1, max_value=MAX_FILE_SIZE_BYTES)
    content_type = serializers.CharField(
        max_length=100, required=False, default='application/octet-stream'
    )

    def validate_file_name(self, value: str) -> str:
        # Sanitisation contre path traversal et caractères dangereux.
        # On garde uniquement le basename — pas de dossier dans le filename.
        # Sanitisation : on REFUSE tout filename qui ressemble à un chemin.
        # Pas de `basename()` ici : ça masquerait un path traversal (`../x.glb`
        # deviendrait `x.glb` qui passerait la check). On valide sur la valeur
        # brute pour rejeter explicitement les filenames contenant `/`, `\`,
        # `..`, des null bytes ou des chars de contrôle.
        sanitized = value.strip()
        if not sanitized or sanitized.startswith('.'):
            raise serializers.ValidationError('Nom de fichier invalide.')
        # Caractères dangereux pour S3 / shell / path traversal
        forbidden_chars = ('\x00', '\n', '\r', '\\', '/')
        if any(c in sanitized for c in forbidden_chars) or '..' in sanitized:
            raise serializers.ValidationError('Nom de fichier contient des caractères interdits.')
        # Extension whitelist
        ext = os.path.splitext(sanitized)[1].lstrip('.').lower()
        if ext not in {choice.value for choice in ImportedModel.Format}:
            raise serializers.ValidationError(
                f'Format non supporté : .{ext}. Formats acceptés : .glb, .gltf, .obj, .fbx, .stl'
            )
        return sanitized

    def validate(self, attrs: dict) -> dict:
        """Cohérence content_type ↔ extension (browser peut mentir, mais
        on refuse les valeurs clairement incohérentes)."""
        ext = os.path.splitext(attrs['file_name'])[1].lstrip('.').lower()
        ct = (attrs.get('content_type') or '').lower().strip()
        allowed = self.CONTENT_TYPE_WHITELIST.get(ext, set())
        if ct and ct not in allowed:
            # On normalise sur octet-stream plutôt que rejeter, sauf si la valeur
            # ressemble à un type clairement malveillant (HTML, script).
            if ct.startswith(('text/html', 'application/javascript', 'application/x-')):
                raise serializers.ValidationError(
                    {'content_type': f'Type MIME incompatible avec .{ext}'}
                )
            attrs['content_type'] = 'application/octet-stream'
        return attrs


class PresignedUploadConfirmSerializer(serializers.Serializer):
    """Confirmation post-upload : enregistre l'ImportedModel en DB."""

    name = serializers.CharField(max_length=200)
    key = serializers.CharField(max_length=500)  # la key S3 retournée par /upload-url
    mtl_key = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ImportedModelUpdateSerializer(serializers.ModelSerializer):
    """PATCH — uniquement transform et nom."""

    class Meta:
        model = ImportedModel
        fields = ('name', 'position', 'rotation', 'scale')


# ─── Annotation ───────────────────────────────────────────────────────────────
class AnnotationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Annotation
        fields = (
            'id',
            'type',
            'position',
            'content',
            'color',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


# ─── ShareLink ────────────────────────────────────────────────────────────────
class ShareLinkSerializer(serializers.ModelSerializer):
    share_url = serializers.SerializerMethodField()
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = ShareLink
        fields = (
            'id',
            'token',
            'share_url',
            'permission',
            'expires_at',
            'last_used_at',
            'created_at',
            'is_expired',
        )
        read_only_fields = (
            'id',
            'token',
            'share_url',
            'last_used_at',
            'created_at',
            'is_expired',
        )

    def get_share_url(self, obj: ShareLink) -> str:
        from django.conf import settings

        return f'{settings.FRONTEND_URL}/shared/{obj.token}'


class ShareLinkCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShareLink
        fields = ('permission', 'expires_at')
