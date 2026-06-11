"""Helpers de stockage pour les archives RGPD (upload + download URL signée).

On isole ces helpers de `apps.projects.presigned` pour éviter le couplage
inverse (gdpr → projects) et pour pouvoir adapter le bucket / le prefix si
besoin (rétention agressive sur les archives RGPD).
"""

from __future__ import annotations

import io
import logging

from django.conf import settings
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)


def upload_export_archive(key: str, content: bytes) -> int:
    """Persiste l'archive ZIP via le storage par défaut (FileSystem ou S3).

    On passe par `default_storage` pour rester compatible avec les tests
    (FileSystem) et la prod (django-storages S3). Retourne la taille du
    fichier en octets.
    """
    file_obj = io.BytesIO(content)
    default_storage.save(key, file_obj)
    return len(content)


def generate_export_download_url(key: str) -> str | None:
    """Génère l'URL de téléchargement de l'archive.

    En S3/MinIO, on signe une URL temporaire (24h) pour ne pas exposer
    l'objet publiquement. En FileSystem (tests / dev), `default_storage.url`
    suffit (sert via Django MEDIA_URL).
    """
    if getattr(settings, 'USE_S3', False):
        try:
            from apps.projects.presigned import get_public_client

            client = get_public_client()
            return client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                    'Key': key,
                },
                ExpiresIn=60 * 60 * 24,  # 24 heures
            )
        except Exception:
            logger.exception('Échec génération presigned URL pour export RGPD')
            return None

    try:
        return default_storage.url(key)
    except Exception:
        logger.exception('Échec génération URL export RGPD (default_storage)')
        return None


def delete_export_archive(key: str) -> None:
    """Supprime l'archive du storage. Idempotent — silencieux si absent."""
    if not key:
        return
    try:
        if default_storage.exists(key):
            default_storage.delete(key)
    except Exception:
        logger.exception('Échec suppression archive export RGPD %s', key)
