"""Modèle léger pour stocker les opt-ins newsletter via le form de contact.

On ne stocke PAS le contenu du message (envoyé par email à l'équipe et oublié)
pour respecter la minimisation RGPD : seul le mail + horodatage + source.
Le user peut se désinscrire à tout moment en répondant à n'importe quelle
newsletter.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class NewsletterSubscriber(models.Model):
    """Email opt-in via le formulaire de contact public."""

    SOURCE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ('contact_form', 'Formulaire de contact'),
        ('footer', 'Inscription footer'),
        ('manual', 'Ajout manuel staff'),
    ]

    email = models.EmailField(unique=True, db_index=True)
    source = models.CharField(
        max_length=32,
        choices=SOURCE_CHOICES,
        default='contact_form',
    )
    is_active = models.BooleanField(default=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ['-subscribed_at']
        verbose_name = 'Abonné newsletter'
        verbose_name_plural = 'Abonnés newsletter'

    def __str__(self) -> str:
        return f'{self.email} ({self.source})'
