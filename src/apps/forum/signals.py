"""Signaux post_save / post_delete pour maintenir les compteurs en cache
et tracker les uploads d'images utilisées dans les posts.

Évite les requêtes COUNT(*) à chaque GET liste — on cache directement les
valeurs sur Category.topics_count et Topic.replies_count.
"""

from __future__ import annotations

from django.db.models import F
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Category, ForumUpload, Reply, Topic
from .uploads import extract_used_keys


# ─── Topic ↔ Category ──────────────────────────────────────────────────────
@receiver(post_save, sender=Topic)
def _topic_created(sender, instance: Topic, created: bool, **kwargs) -> None:
    if created:
        Category.objects.filter(pk=instance.category_id).update(topics_count=F('topics_count') + 1)


@receiver(post_delete, sender=Topic)
def _topic_deleted(sender, instance: Topic, **kwargs) -> None:
    # Garde-fou : ne pas descendre en négatif si la cat est déjà supprimée
    Category.objects.filter(pk=instance.category_id, topics_count__gt=0).update(
        topics_count=F('topics_count') - 1
    )


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
    Topic.objects.filter(pk=instance.topic_id, replies_count__gt=0).update(
        replies_count=F('replies_count') - 1
    )


# ─── ForumUpload : mark `used=True` les images référencées dans un post ──
def _mark_used(content: str, user_id: int) -> None:
    """Mark `used=True` les ForumUpload de cet user dont la key apparaît
    dans le HTML du post. Idempotent (filter sur used=False seulement)."""
    keys = extract_used_keys(content)
    if not keys:
        return
    now = timezone.now()
    # On ne touche que les uploads de l'auteur lui-même (sécurité : un user
    # ne peut pas "valider" l'upload d'un autre user en référençant sa key).
    ForumUpload.objects.filter(
        user_id=user_id,
        key__in=keys,
        used=False,
    ).update(used=True, first_used_at=now)


@receiver(post_save, sender=Topic)
def _topic_mark_uploads_used(sender, instance: Topic, **kwargs) -> None:
    _mark_used(instance.content, instance.author_id)


@receiver(post_save, sender=Reply)
def _reply_mark_uploads_used(sender, instance: Reply, **kwargs) -> None:
    _mark_used(instance.content, instance.author_id)
