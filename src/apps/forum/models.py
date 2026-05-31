"""Modèles du forum communautaire.

Architecture MVP :
- `Category` : regroupement haut niveau (Annonces, Support, Idées, etc.)
- `Topic` : un sujet ouvert par un user, contient un message initial + des replies
- `Reply` : réponse à un topic (pas de threading nested pour simplifier l'UX)

Pas inclus dans le MVP :
- Likes / votes (ajoutable via une table M2M)
- Notifications / subscriptions (ajoutable via un modèle Subscription)
- Tags libres (ajoutable via M2M Tag)
- Édition d'historique (ajoutable via django-simple-history)
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    """Catégorie haut-niveau du forum (Annonces, Support, etc.)."""

    slug = models.SlugField(unique=True, max_length=80)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    # Icône Lucide (ex: 'megaphone', 'help-circle', 'lightbulb', 'bug')
    icon = models.CharField(max_length=50, blank=True)
    # Tailwind color (ex: 'blue', 'red', 'amber', 'green')
    color = models.CharField(max_length=20, blank=True)
    # Ordre d'affichage dans la liste des catégories (asc)
    order = models.PositiveIntegerField(default=0)
    # True : seuls les staff peuvent créer un Topic dans cette cat
    # (typiquement pour "Annonces"). Les replies restent ouvertes à tous.
    is_admin_only = models.BooleanField(default=False)
    # Cache du nombre de topics, mis à jour via signaux post_save/post_delete
    topics_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'forum_category'
        ordering = ['order', 'name']
        verbose_name_plural = 'Categories'

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            self.slug = slugify(self.name)[:80]
        super().save(*args, **kwargs)


class Topic(models.Model):
    """Sujet de discussion dans une catégorie."""

    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name='topics'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='topics'
    )
    title = models.CharField(max_length=200)
    # slug pour URL friendly (ex: /forum/12-comment-importer-un-modele-glb)
    # Inclut un suffixe id pour éviter les collisions.
    slug = models.SlugField(max_length=220, blank=True)
    # Markdown supporté côté frontend (rendu par useMarkdown + DOMPurify)
    content = models.TextField()
    # Pinné en haut de la liste de la cat (par staff uniquement)
    is_pinned = models.BooleanField(default=False)
    # Verrouillé : aucune nouvelle reply acceptée (par staff ou owner)
    is_locked = models.BooleanField(default=False)
    # Compteurs cachés (sync via signaux + endpoint POST views)
    views_count = models.PositiveIntegerField(default=0)
    replies_count = models.PositiveIntegerField(default=0)
    # Mis à jour à chaque nouvelle reply (pour ordering "last activity")
    last_reply_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'forum_topic'
        ordering = ['-is_pinned', '-last_reply_at', '-created_at']
        indexes = [
            models.Index(fields=['-last_reply_at']),
            models.Index(fields=['category', '-last_reply_at']),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            # Slug provisoire, sera updaté avec l'id après création
            self.slug = slugify(self.title)[:200]
        super().save(*args, **kwargs)


class Reply(models.Model):
    """Réponse à un Topic."""

    topic = models.ForeignKey(
        Topic, on_delete=models.CASCADE, related_name='replies'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='forum_replies'
    )
    content = models.TextField()
    # Marquée par l'auteur du topic comme la solution acceptée
    is_solution = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'forum_reply'
        ordering = ['created_at']  # chronologique ASC (lecture naturelle)
        indexes = [
            models.Index(fields=['topic', 'created_at']),
        ]

    def __str__(self) -> str:
        return f'Reply by {self.author} on "{self.topic.title[:40]}"'
