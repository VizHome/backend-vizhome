"""Modèles support : SupportTicket + SupportMessage.

Mini-helpdesk : un user ouvre un ticket avec un sujet + 1er message, le staff
y répond via des messages threadés. Le ticket transitionne entre 4 statuts
(open / pending / resolved / closed). Pas d'attachments dans cette v1.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class SupportTicket(models.Model):
    """Ticket de support ouvert par un user, géré par le staff."""

    class Status(models.TextChoices):
        OPEN = 'open', 'Ouvert'  # User a posté, staff n'a pas encore répondu
        PENDING = 'pending', 'En cours'  # Staff a pris en charge / discussion active
        RESOLVED = (
            'resolved',
            'Résolu',
        )  # Staff a marqué résolu, en attente confirmation
        CLOSED = 'closed', 'Fermé'  # Définitif, plus de réponses possibles

    class Priority(models.TextChoices):
        LOW = 'low', 'Faible'
        MEDIUM = 'medium', 'Moyenne'
        HIGH = 'high', 'Haute'
        URGENT = 'urgent', 'Urgente'

    class Category(models.TextChoices):
        TECHNICAL = 'technical', 'Problème technique'
        BILLING = 'billing', 'Facturation'
        ACCOUNT = 'account', 'Compte / accès'
        FEATURE = 'feature', 'Demande de fonctionnalité'
        OTHER = 'other', 'Autre'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='support_tickets',
    )
    subject = models.CharField(max_length=200)
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.OTHER,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )

    # Staff qui a pris en charge (null jusqu'à la 1ère réponse staff)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_support_tickets',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'support_ticket'
        ordering = ['-updated_at']
        verbose_name = 'Ticket de support'
        verbose_name_plural = 'Tickets de support'

    def __str__(self) -> str:
        return f'#{self.pk} — {self.subject[:50]}'

    def mark_closed(self) -> None:
        self.status = self.Status.CLOSED
        self.closed_at = timezone.now()
        self.save(update_fields=['status', 'closed_at', 'updated_at'])


class SupportMessage(models.Model):
    """Un message dans la conversation d'un ticket.

    Auteur = user du ticket OU n'importe quel staff. Le 1er message est créé
    en même temps que le ticket (cf TicketCreateSerializer).
    """

    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='support_messages',
    )
    # Snapshot du flag staff au moment du message (utile si l'auteur perd
    # le rôle staff plus tard — l'historique reste lisible).
    from_staff = models.BooleanField(default=False)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'support_message'
        ordering = ['created_at']

    def __str__(self) -> str:
        who = 'staff' if self.from_staff else 'user'
        return f'#{self.ticket_id} [{who}] {self.body[:40]}'
