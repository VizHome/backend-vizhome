"""Tâches Celery pour les flux RGPD (export + suppression différée)."""

from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import timedelta
from typing import Any

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.emails import send_templated_email

from .models import EXPORT_LINK_TTL_HOURS, DeletionRequest, ExportRequest
from .storage import (
    delete_export_archive,
    generate_export_download_url,
    upload_export_archive,
)

logger = logging.getLogger(__name__)


# ─── Export ──────────────────────────────────────────────────────────────────
def _serialize_user_data(user) -> dict[str, Any]:
    """Construit le dict des données personnelles à exporter.

    Garantit la portabilité (art. 20 RGPD) : tout est sérialisable en JSON,
    pas d'objet Django brut. On capture profil + préférences + stats +
    projets + renders + posts forum + tickets support + sessions actives.
    """
    data: dict[str, Any] = {
        'profil': {
            'id': user.pk,
            'email': user.email,
            'pseudo': user.pseudo,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'avatar_url': user.avatar_url,
            'plan': user.plan,
            'date_joined': user.date_joined.isoformat(),
            'last_login': user.last_login.isoformat() if user.last_login else None,
        },
    }

    # Préférences
    if hasattr(user, 'preferences'):
        prefs = user.preferences
        data['preferences'] = {
            'theme': prefs.theme,
            'language': prefs.language,
            'notif_email_render': prefs.notif_email_render,
            'notif_email_newsletter': prefs.notif_email_newsletter,
            'notif_push_render': prefs.notif_push_render,
            'notif_push_mentions': prefs.notif_push_mentions,
            'render_quality': prefs.render_quality,
            'render_format': prefs.render_format,
            'render_resolution': prefs.render_resolution,
            'analytics_enabled': prefs.analytics_enabled,
            'marketing_enabled': prefs.marketing_enabled,
            'two_factor_enabled': prefs.two_factor_enabled,
            'reduced_motion': prefs.reduced_motion,
            'high_contrast': prefs.high_contrast,
            'font_size': prefs.font_size,
        }

    # Stats (compteurs + quotas)
    if hasattr(user, 'stats'):
        s = user.stats
        data['stats'] = {
            'renders_this_month': s.renders_this_month,
            'renders_limit': s.renders_limit,
            'total_projects': s.total_projects,
            'storage_used_bytes': s.storage_used_bytes,
            'storage_limit_bytes': s.storage_limit_bytes,
            'period_started_at': s.period_started_at.isoformat(),
        }

    # Projets 3D (méta uniquement — pas de blob, ils sont dans MinIO)
    data['projets'] = [
        {
            'id': p.pk,
            'title': p.title,
            'description': p.description,
            'is_archived': p.is_archived,
            'created_at': p.created_at.isoformat(),
            'updated_at': p.updated_at.isoformat(),
        }
        for p in user.projects.all()
    ]

    # Renders IA (méta + prompt)
    data['renders'] = [
        {
            'id': r.pk,
            'source': r.source,
            'output_type': r.output_type,
            'prompt': r.prompt,
            'style_hint': r.style_hint,
            'status': r.status,
            'provider': r.provider,
            'title': r.title,
            'created_at': r.created_at.isoformat(),
        }
        for r in user.renders.all()
    ]

    # Forum : topics + réponses
    data['forum_topics'] = [
        {
            'id': t.pk,
            'category': t.category.slug if t.category_id else None,
            'title': t.title,
            'content': t.content,
            'created_at': t.created_at.isoformat(),
        }
        for t in user.topics.all()
    ]
    data['forum_replies'] = [
        {
            'id': r.pk,
            'topic_id': r.topic_id,
            'content': r.content,
            'is_solution': r.is_solution,
            'created_at': r.created_at.isoformat(),
        }
        for r in user.forum_replies.all()
    ]

    # Tickets support + messages
    tickets_data = []
    for t in user.support_tickets.all():
        tickets_data.append(
            {
                'id': t.pk,
                'subject': t.subject,
                'category': t.category,
                'status': t.status,
                'priority': t.priority,
                'created_at': t.created_at.isoformat(),
                'messages': [
                    {
                        'id': m.pk,
                        'from_staff': m.from_staff,
                        'body': m.body,
                        'created_at': m.created_at.isoformat(),
                    }
                    for m in t.messages.all()
                ],
            }
        )
    data['support_tickets'] = tickets_data

    # Sessions actives (méta — pas le token brut)
    data['sessions'] = [
        {
            'device_name': s.device_name,
            'ip_address': s.ip_address,
            'location': s.location,
            'created_at': s.created_at.isoformat(),
            'last_active': s.last_active.isoformat(),
            'revoked_at': s.revoked_at.isoformat() if s.revoked_at else None,
        }
        for s in user.sessions.all()
    ]

    return data


def _build_zip(data: dict[str, Any]) -> bytes:
    """Construit l'archive ZIP en mémoire (data.json + README)."""
    buffer = io.BytesIO()
    readme = (
        '# Export RGPD VizHome\n\n'
        'Ce ZIP contient toutes les données personnelles associées à votre '
        'compte VizHome.\n\n'
        'Fichiers :\n'
        '- data.json — profil, préférences, stats, projets, renders, '
        'forum, support, sessions.\n\n'
        'Ce lien de téléchargement est valable 24 heures. Au-delà, demande '
        'un nouvel export depuis Mon compte → Confidentialité.\n'
    )
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('README.md', readme)
        zf.writestr(
            'data.json',
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
        )
    return buffer.getvalue()


@shared_task(name='gdpr.build_user_export_zip', bind=True, max_retries=2)
def build_user_export_zip(self, export_id: int) -> None:
    """Génère l'archive ZIP RGPD pour une `ExportRequest`.

    Étapes :
    1. Charge l'export et le user.
    2. Sérialise les données → ZIP en mémoire.
    3. Upload via `default_storage` (MinIO en prod, FileSystem en tests).
    4. Marque `status=READY`, fixe `expires_at = now + 24h`.
    5. Envoie un email au user avec le lien.
    """
    try:
        export = ExportRequest.objects.select_related('user').get(pk=export_id)
    except ExportRequest.DoesNotExist:
        logger.warning('Export RGPD %s introuvable', export_id)
        return

    user = export.user

    export.status = ExportRequest.Status.PROCESSING
    export.save(update_fields=['status'])

    try:
        payload = _serialize_user_data(user)
        archive_bytes = _build_zip(payload)
        # Clé MinIO unique par export. Sous-dossier user pour faciliter
        # un éventuel garbage collector ciblé.
        key = f'gdpr/exports/{user.pk}/export-{export.pk}.zip'

        size = upload_export_archive(key, archive_bytes)

        export.file_key = key
        export.file_size_bytes = size
        export.status = ExportRequest.Status.READY
        export.completed_at = timezone.now()
        export.expires_at = timezone.now() + timedelta(hours=EXPORT_LINK_TTL_HOURS)
        export.save(
            update_fields=[
                'file_key',
                'file_size_bytes',
                'status',
                'completed_at',
                'expires_at',
            ]
        )

        # Notifie le user par email (fail-silently — non bloquant pour le job)
        try:
            download_url = generate_export_download_url(key)
            frontend = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
            privacy_url = f'{frontend}/account/privacy'
            send_templated_email(
                subject='Votre export RGPD VizHome est prêt',
                recipients=[user.email],
                template='gdpr_export_ready',
                context={
                    'cta_url': download_url or privacy_url,
                    'cta_label': 'Télécharger mes données',
                    'privacy_url': privacy_url,
                    'preheader': 'Ton archive de données personnelles est disponible 24h.',
                },
            )
        except Exception:
            logger.exception('Échec envoi email export RGPD %s', export.pk)

    except Exception as exc:
        logger.exception('Échec préparation export RGPD %s', export.pk)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30) from exc
        export.status = ExportRequest.Status.FAILED
        export.error_message = str(exc)[:2000]
        export.completed_at = timezone.now()
        export.save(update_fields=['status', 'error_message', 'completed_at'])


# ─── Cleanup périodique des exports expirés ──────────────────────────────────
@shared_task(name='gdpr.cleanup_expired_exports')
def cleanup_expired_exports() -> int:
    """Supprime du storage les archives RGPD expirées (> 24h).

    À planifier sur Celery beat (typiquement toutes les heures). Retourne
    le nombre d'exports nettoyés.
    """
    now = timezone.now()
    qs = ExportRequest.objects.filter(
        status=ExportRequest.Status.READY,
        expires_at__lte=now,
    )
    cleaned = 0
    for export in qs:
        if export.file_key:
            delete_export_archive(export.file_key)
        export.status = ExportRequest.Status.EXPIRED
        export.file_key = ''
        export.save(update_fields=['status', 'file_key'])
        cleaned += 1
    if cleaned:
        logger.info('GDPR: %s export(s) expiré(s) nettoyé(s)', cleaned)
    return cleaned


# ─── Hard delete des comptes en attente (Celery beat quotidien) ──────────────
@shared_task(name='gdpr.cleanup_pending_deletions')
def cleanup_pending_deletions() -> int:
    """Hard delete les comptes dont la `scheduled_for` est échue.

    À planifier sur Celery beat — typiquement chaque jour à 03:00.
    Pour chaque `DeletionRequest` :
    - pas annulée (`cancelled_at is None`)
    - pas encore exécutée (`completed_at is None`)
    - échéance dépassée (`scheduled_for <= now`)

    On appelle `user.delete()` qui cascade sur tous les FK → projets,
    renders, forum, support, etc. La `DeletionRequest` elle-même est
    supprimée en cascade (FK CASCADE sur user).

    Pour garder une trace de l'opération, on log avant la suppression et
    on archive un message dans les logs (pas de DB après suppression).
    """
    user_model = get_user_model()
    now = timezone.now()

    pending = DeletionRequest.objects.filter(
        cancelled_at__isnull=True,
        completed_at__isnull=True,
        scheduled_for__lte=now,
    ).select_related('user')

    deleted = 0
    for deletion in pending:
        user = deletion.user
        user_pk = user.pk
        user_email = user.email
        try:
            # Note avant cascade : la deletion request va disparaître aussi
            logger.info(
                'GDPR hard delete: user=%s pk=%s requested_at=%s scheduled_for=%s',
                user_email,
                user_pk,
                deletion.requested_at.isoformat(),
                deletion.scheduled_for.isoformat(),
            )
            # `user.delete()` cascade sur toutes les FK avec
            # on_delete=CASCADE (projets, renders, sessions, forum,
            # tickets, gdpr.DeletionRequest elle-même…).
            user_model.objects.filter(pk=user_pk).delete()
            deleted += 1
        except Exception:
            logger.exception(
                'Échec hard delete user pk=%s — sera retentée demain',
                user_pk,
            )

    if deleted:
        logger.info('GDPR: %s compte(s) supprimé(s) définitivement', deleted)
    return deleted
