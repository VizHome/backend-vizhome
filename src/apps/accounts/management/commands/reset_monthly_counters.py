"""Reset le compteur renders_this_month pour tous les utilisateurs.

À exécuter mensuellement (le 1er du mois) via cron ou Celery beat.

Usage :
    python manage.py reset_monthly_counters
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import UserStats


class Command(BaseCommand):
    help = "Reset les compteurs mensuels (renders_this_month) de tous les users"

    def handle(self, *args, **opts) -> None:
        updated = UserStats.objects.update(
            renders_this_month=0,
            period_started_at=timezone.now(),
        )
        self.stdout.write(self.style.SUCCESS(f"✓ {updated} compteurs reset."))
