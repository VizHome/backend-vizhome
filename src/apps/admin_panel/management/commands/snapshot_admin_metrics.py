"""Snapshot quotidien des métriques admin pour historique long terme.

Lance chaque nuit via Celery beat (cf apps/admin_panel/tasks.py). Stocke
l'overview complet dans AdminDailySnapshot.payload (JSONField).

Pourquoi ? Le dashboard /admin/overview est calculé en temps réel par
agrégation SQL. Pour afficher une évolution sur 6 mois ou 1 an, recomputer
ça à chaque chargement coûterait cher. Les snapshots permettent de répondre
en O(N_days) au lieu de O(N_rows).

Usage manuel :
    docker compose exec api python manage.py snapshot_admin_metrics
    docker compose exec api python manage.py snapshot_admin_metrics --date 2026-05-30
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from django.core.management.base import BaseCommand
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Capture un snapshot quotidien de l'overview admin "
        "(stocké dans AdminDailySnapshot)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--date',
            type=str,
            default=None,
            help='Date du snapshot (YYYY-MM-DD). Défaut : aujourd\'hui.',
        )

    def handle(self, *args, **options) -> None:
        from apps.admin_panel.models import AdminDailySnapshot
        from apps.admin_panel.views import AdminOverviewView
        from rest_framework.test import APIRequestFactory

        # Date du snapshot
        date_str = options.get('date')
        snapshot_date = (
            datetime.strptime(date_str, '%Y-%m-%d').date()
            if date_str
            else timezone.now().date()
        )

        # Construit une fausse request pour appeler AdminOverviewView en interne
        # (le request.user n'est pas utilisé dans les agrégations)
        factory = APIRequestFactory()
        request = factory.get('/api/v1/admin/overview')

        view = AdminOverviewView()
        response = view.get(request)
        payload: dict[str, Any] = response.data

        # JSONField PostgreSQL n'avale pas les datetime/date natifs.
        # On serialize via DjangoJSONEncoder (gère datetime/date/UUID/Decimal)
        # puis reparse en dict 100% JSON-safe.
        payload = json.loads(json.dumps(payload, cls=DjangoJSONEncoder))

        obj, created = AdminDailySnapshot.objects.update_or_create(
            date=snapshot_date,
            defaults={'payload': payload},
        )
        verb = 'créé' if created else 'mis à jour'
        self.stdout.write(self.style.SUCCESS(
            f'✓ Snapshot {snapshot_date} {verb} '
            f'({len(payload)} sections capturées).'
        ))
