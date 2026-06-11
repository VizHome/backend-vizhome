"""Garbage collector pour les images uploadées dans le forum mais jamais
utilisées dans un post.

Cas typique : un user ouvre l'éditeur de topic, drag-drop 3 images dans
TipTap (chacune POST /forum/upload-image → ForumUpload(used=False)), puis
ferme l'onglet sans publier. Les fichiers restent sur MinIO. Cette
commande les nettoie après une période de grâce (24h par défaut).

Usage :
    docker compose exec api python manage.py cleanup_forum_orphan_uploads
    docker compose exec api python manage.py cleanup_forum_orphan_uploads --hours 12 --dry-run

Configurer en tâche Celery beat quotidienne via Django admin
(django-celery-beat → PeriodicTasks → add) ou via cron Docker.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.forum.models import ForumUpload


class Command(BaseCommand):
    help = (
        'Supprime les ForumUpload `used=False` plus vieux que --hours heures '
        '(défaut 24), avec leur fichier MinIO associé.'
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Période de grâce en heures avant suppression (défaut: 24).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="N'effectue aucune suppression, juste un rapport.",
        )

    def handle(self, *args, **options) -> None:
        hours: int = options['hours']
        dry_run: bool = options['dry_run']

        threshold = timezone.now() - timedelta(hours=hours)
        orphans = ForumUpload.objects.filter(
            used=False,
            created_at__lt=threshold,
        )
        total = orphans.count()

        self.stdout.write(f'Trouvé {total} upload(s) orphelin(s) plus vieux que {hours}h.')
        if total == 0:
            return

        if dry_run:
            self.stdout.write(self.style.WARNING('--dry-run : aucune suppression.'))
            for u in orphans[:20]:
                self.stdout.write(f'  - {u.key} (créé {u.created_at:%Y-%m-%d %H:%M})')
            if total > 20:
                self.stdout.write(f'  … et {total - 20} autres.')
            return

        deleted_files = 0
        deleted_records = 0
        failed = 0
        for upload in orphans.iterator():
            # 1. Supprime le fichier MinIO (best-effort)
            try:
                if default_storage.exists(upload.key):
                    default_storage.delete(upload.key)
                deleted_files += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Échec suppression fichier {upload.key} : {e}'))
                failed += 1
                # On supprime quand même le record DB (sinon il restera
                # orphelin et on essaiera de le re-suppr indéfiniment).

            # 2. Supprime le record DB
            upload.delete()
            deleted_records += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'✓ {deleted_records} record(s) supprimé(s), '
                f'{deleted_files} fichier(s) MinIO supprimé(s)'
                + (f', {failed} échec(s) MinIO.' if failed else '.')
            )
        )
