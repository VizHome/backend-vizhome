"""Serializers DRF pour l'app gdpr."""

from __future__ import annotations

from typing import ClassVar

from rest_framework import serializers

from .models import DeletionRequest, ExportRequest


class ExportRequestSerializer(serializers.ModelSerializer):
    """Représentation publique d'une demande d'export.

    `download_url` n'est posée que si l'export est prêt et non expiré
    (calculée à la volée via une URL signée MinIO 24h).
    """

    download_url = serializers.SerializerMethodField()
    is_ready = serializers.BooleanField(read_only=True)

    class Meta:
        model = ExportRequest
        fields: ClassVar[tuple[str, ...]] = (
            'id',
            'status',
            'requested_at',
            'completed_at',
            'expires_at',
            'file_size_bytes',
            'is_ready',
            'download_url',
            'error_message',
        )
        read_only_fields = fields

    def get_download_url(self, obj: ExportRequest) -> str | None:
        """Génère une URL signée à la demande (24h max).

        On ne la stocke pas en DB pour éviter qu'elle traîne dans les logs
        ou les exports admin. Elle est régénérée à chaque GET status par le
        user concerné. En storage S3/MinIO on signe l'URL ; en FileSystem
        (tests / dev sans S3) on renvoie l'URL MEDIA classique.
        """
        if not obj.is_ready or not obj.file_key:
            return None
        from .storage import generate_export_download_url

        return generate_export_download_url(obj.file_key)


class DeletionRequestSerializer(serializers.ModelSerializer):
    """Représentation publique d'une demande de suppression."""

    is_pending = serializers.BooleanField(read_only=True)
    is_cancellable = serializers.BooleanField(read_only=True)

    class Meta:
        model = DeletionRequest
        fields: ClassVar[tuple[str, ...]] = (
            'id',
            'requested_at',
            'scheduled_for',
            'cancelled_at',
            'completed_at',
            'notes',
            'is_pending',
            'is_cancellable',
        )
        read_only_fields: ClassVar[tuple[str, ...]] = (
            'id',
            'requested_at',
            'scheduled_for',
            'cancelled_at',
            'completed_at',
            'is_pending',
            'is_cancellable',
        )


class DeleteAccountInputSerializer(serializers.Serializer):
    """Confirmation explicite + notes facultatives pour POST /me/delete-account.

    Le `confirm` doit valoir littéralement `DELETE` pour limiter les
    suppressions accidentelles (UI : l'utilisateur tape `DELETE` dans un
    input avant de pouvoir cliquer).
    """

    confirm = serializers.CharField(write_only=True)
    notes = serializers.CharField(
        required=False, allow_blank=True, write_only=True, max_length=2000
    )

    def validate_confirm(self, value: str) -> str:
        if value.strip() != 'DELETE':
            raise serializers.ValidationError('Confirme la suppression en envoyant "DELETE".')
        return value
