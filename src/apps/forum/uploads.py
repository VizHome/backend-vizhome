"""Helpers pour le suivi des images uploadées dans les posts du forum.

Architecture :
- `ForumUpload` (modèle) trace chaque upload avec un flag `used`
- `extract_used_keys(html)` parse le HTML d'un Topic/Reply et retourne
  l'ensemble des clés MinIO référencées en `<img src>`
- Le signal `mark_uploads_used` (signals.py) appelle ça à chaque
  save de Topic ou Reply pour mettre à jour le flag
- La management command `cleanup_forum_orphan_uploads` supprime les
  uploads dont `used=False` et `created_at < now() - threshold`
"""

from __future__ import annotations

import re

from django.conf import settings

# Regex tolérant aux variations : <img src="..."> ou <img attrs… src='...' attrs…>
_IMG_SRC_RE = re.compile(
    r'<img\b[^>]*?\bsrc=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def _public_base_url() -> str:
    """Construit le préfixe complet d'une image hostée sur notre MinIO.

    Ex: 'http://localhost:9000/vizhome-media/'
    Avec MINIO_S3_CUSTOM_DOMAIN='localhost:9000/vizhome-media' et
    MINIO_S3_URL_PROTOCOL='http:'.
    """
    domain = (getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', '') or '').rstrip('/')
    protocol = getattr(settings, 'AWS_S3_URL_PROTOCOL', 'http:') or 'http:'
    if not domain:
        return ''
    return f'{protocol}//{domain}/'


def extract_used_keys(html: str) -> set[str]:
    """Extrait les clés MinIO depuis les `<img src>` du HTML d'un post.

    Retourne un set de clés (sans le préfixe public). Filtre uniquement
    les images dont l'URL commence par notre domaine public — les images
    externes (Imgur, CDN tiers) sont ignorées.

    Ex: <img src="http://localhost:9000/vizhome-media/forum/uploads/4/2026/05/abc.png">
         → {'forum/uploads/4/2026/05/abc.png'}
    """
    if not html:
        return set()

    prefix = _public_base_url()
    if not prefix:
        # Pas de config MinIO → on ne tracke pas
        return set()

    keys: set[str] = set()
    for src in _IMG_SRC_RE.findall(html):
        if not src.startswith(prefix):
            continue
        # Strip le préfixe + d'éventuels query params (?versionId=, etc.)
        key = src[len(prefix) :].split('?', 1)[0].split('#', 1)[0]
        if key:
            keys.add(key)
    return keys
