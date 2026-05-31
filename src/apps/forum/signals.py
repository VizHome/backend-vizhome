"""Signaux post_save / post_delete pour maintenir les compteurs en cache.

Évite les requêtes COUNT(*) à chaque GET liste — on cache directement les
valeurs sur Category.topics_count et Topic.replies_count.
"""
from __future__ import annotations

from django.db.models import F
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Category, Reply, Topic


# ─── Topic ↔ Category ──────────────────────────────────────────────────────
@receiver(post_save, sender=Topic)
def _topic_created(sender, instance: Topic, created: bool, **kwargs) -> None:
    if created:
        Category.objects.filter(pk=instance.category_id).update(
            topics_count=F('topics_count') + 1
        )


@receiver(post_delete, sender=Topic)
def _topic_deleted(sender, instance: Topic, **kwargs) -> None:
    # Garde-fou : ne pas descendre en négatif si la cat est déjà supprimée
    Category.objects.filter(
        pk=instance.category_id, topics_count__gt=0
    ).update(topics_count=F('topics_count') - 1)


# ─── Reply ↔ Topic ─────────────────────────────────────────────────────────
@receiver(post_save, sender=Reply)
def _reply_created(sender, instance: Reply, created: bool, **kwargs) -> None:
    if created:
        Topic.objects.filter(pk=instance.topic_id).update(
            replies_count=F('replies_count') + 1,
            last_reply_at=timezone.now(),
        )


@receiver(post_delete, sender=Reply)
def _reply_deleted(sender, instance: Reply, **kwargs) -> None:
    Topic.objects.filter(
        pk=instance.topic_id, replies_count__gt=0
    ).update(replies_count=F('replies_count') - 1)
