"""Tâches Celery pour le forum.

Pour activer le cleanup auto quotidien des uploads orphelins :
1. Django admin → django-celery-beat → Periodic tasks → Add
2. Task = `apps.forum.tasks.cleanup_forum_orphan_uploads_task`
3. Crontab = `0 3 * * *` (3h du matin tous les jours, ajustable)
4. Save → la tâche tourne automatiquement
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.core.management import call_command

logger = logging.getLogger(__name__)


@shared_task(name='forum.cleanup_orphan_uploads')
def cleanup_forum_orphan_uploads_task(hours: int = 24) -> None:
    """Wrapper Celery autour de la management command.

    Période de grâce par défaut : 24h (= un user a 24h pour publier après
    avoir uploadé une image avant qu'elle soit considérée orpheline).
    """
    logger.info('Forum cleanup orphan uploads (period=%dh) — start', hours)
    call_command('cleanup_forum_orphan_uploads', hours=hours)
    logger.info('Forum cleanup orphan uploads — done')
