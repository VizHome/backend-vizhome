"""Tâches Celery du panel admin.

Pour activer le snapshot auto quotidien :
1. Django admin → django-celery-beat → Periodic tasks → Add
2. Task = `admin_panel.snapshot_metrics`
3. Crontab = `5 0 * * *` (00:05 chaque nuit)
4. Save → Celery beat lance la task automatiquement
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.core.management import call_command

logger = logging.getLogger(__name__)


@shared_task(name='admin_panel.snapshot_metrics')
def snapshot_admin_metrics_task() -> None:
    """Wrapper Celery autour de la management command snapshot_admin_metrics.

    Exécute snapshot_admin_metrics sans argument (date = today).
    """
    logger.info('Admin snapshot metrics — start')
    call_command('snapshot_admin_metrics')
    logger.info('Admin snapshot metrics — done')
