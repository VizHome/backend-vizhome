"""Crée les 5 catégories par défaut du forum.

Idempotent : update_or_create par slug. À lancer une seule fois après
les migrations initiales :

    docker compose exec api python manage.py seed_forum_categories
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.forum.models import Category

DEFAULTS = [
    {
        'slug': 'annonces',
        'name': 'Annonces',
        'description': 'Nouveautés produit, releases, événements VizHome.',
        'icon': 'megaphone',
        'color': 'blue',
        'order': 1,
        'is_admin_only': True,
    },
    {
        'slug': 'idees',
        'name': 'Idées & suggestions',
        'description': 'Propose des features ou améliorations pour VizHome.',
        'icon': 'lightbulb',
        'color': 'amber',
        'order': 2,
        'is_admin_only': False,
    },
    {
        'slug': 'support',
        'name': 'Support',
        'description': "Besoin d'aide ? Pose ta question à la communauté.",
        'icon': 'help-circle',
        'color': 'green',
        'order': 3,
        'is_admin_only': False,
    },
    {
        'slug': 'bugs',
        'name': 'Bug reports',
        'description': 'Signale un bug. Précise étapes, résultat attendu et observé.',
        'icon': 'bug',
        'color': 'red',
        'order': 4,
        'is_admin_only': False,
    },
    {
        'slug': 'discussions',
        'name': 'Discussions générales',
        'description': 'Pour tout ce qui ne rentre pas ailleurs.',
        'icon': 'messages-square',
        'color': 'slate',
        'order': 5,
        'is_admin_only': False,
    },
]


class Command(BaseCommand):
    help = 'Seed les catégories par défaut du forum.'

    def handle(self, *args, **options) -> None:
        created = 0
        updated = 0
        for cat in DEFAULTS:
            obj, was_created = Category.objects.update_or_create(
                slug=cat['slug'],
                defaults=cat,
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f'  + créé : {obj.name}'))
            else:
                updated += 1
                self.stdout.write(self.style.WARNING(f'  ~ updaté : {obj.name}'))

        self.stdout.write(
            self.style.SUCCESS(f'✓ Seed terminé. {created} créé(s), {updated} updaté(s).')
        )
