"""Helpers pour générer des presigned URLs MinIO/S3.

Le frontend reçoit ces URLs et PUT directement les gros fichiers vers MinIO,
sans passer par Django (économise CPU/RAM et lève la limite de taille
multipart).

⚠️ Subtilité signature SigV4 : la signature inclut le HOST de l'URL. On a deux
endpoints différents :
- interne (Docker) : http://minio:9000 — utilisé pour head_object, delete, etc.
- public (browser) : http://localhost:9000 — utilisé pour les presigned URLs

Donc on utilise DEUX clients boto3 distincts.
"""
from __future__ import annotations

import boto3
from botocore.config import Config
from django.conf import settings


def _public_endpoint_url() -> str:
    """Construit l'URL publique de MinIO depuis CUSTOM_DOMAIN (sans bucket suffix)."""
    host = (settings.AWS_S3_CUSTOM_DOMAIN or '').split('/')[0]
    protocol = settings.AWS_S3_URL_PROTOCOL or 'http:'
    return f'{protocol}//{host}'


def _make_client(endpoint_url: str):
    return boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
        config=Config(
            signature_version='s3v4',
            s3={'addressing_style': 'path'},
        ),
    )


def get_internal_client():
    """Client pour les opérations server-side (head_object, delete…)."""
    return _make_client(settings.AWS_S3_ENDPOINT_URL)


def get_public_client():
    """Client pour générer des presigned URLs valides depuis le browser."""
    return _make_client(_public_endpoint_url())


def generate_upload_url(
    key: str,
    content_type: str = 'application/octet-stream',
    expires_in: int = 3600,
) -> str:
    """Génère une URL pré-signée PUT pour upload direct par le frontend.

    L'URL est signée avec le host public (localhost:9000 en dev) pour que la
    signature soit valide quand le navigateur l'utilise.
    """
    client = get_public_client()
    return client.generate_presigned_url(
        'put_object',
        Params={
            'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
            'Key': key,
            'ContentType': content_type,
        },
        ExpiresIn=expires_in,
    )


def head_object(key: str) -> dict | None:
    """Récupère les métadonnées d'un objet (notamment ContentLength).

    Utilise le client interne (réseau Docker → MinIO).
    """
    client = get_internal_client()
    try:
        return client.head_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key
        )
    except client.exceptions.NoSuchKey:
        return None
    except Exception:
        return None


def copy_object(source_key: str, dest_key: str) -> None:
    """Copie un objet à l'intérieur du même bucket (server-side, ultra-rapide).

    Pas de transfert réseau via Django — MinIO copie en interne.
    """
    client = get_internal_client()
    client.copy_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        CopySource={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': source_key},
        Key=dest_key,
    )
