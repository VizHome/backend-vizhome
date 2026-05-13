"""Signaux : auto-création de Preferences et Stats à l'inscription."""
from __future__ import annotations

from typing import Any

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PLAN_QUOTAS, User, UserPreferences, UserStats


@receiver(post_save, sender=User)
def create_user_relations(
    sender: type[User], instance: User, created: bool, **kwargs: Any
) -> None:
    """À la création d'un user, instancier ses Preferences et Stats."""
    if not created:
        return

    UserPreferences.objects.create(user=instance)

    quotas = PLAN_QUOTAS[instance.plan]
    UserStats.objects.create(
        user=instance,
        renders_limit=quotas['renders_limit'],
        storage_limit_bytes=quotas['storage_limit_bytes'],
    )
