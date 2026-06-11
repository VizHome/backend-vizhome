"""Modèles RGPD : ExportRequest + DeletionRequest.

Deux flux distincts mais complémentaires :

* `ExportRequest` : un user peut récupérer une archive ZIP de ses données
  personnelles (profil, projets, renders, tickets, etc.). Préparée en tâche
  Celery, mise à disposition via une URL signée 24h, puis garbage-collectée.

* `DeletionRequest` : un user demande la suppression de son compte. On
  désactive le compte immédiatement (`is_active=False`), on fixe une
  échéance à 30 jours, et une tâche Celery beat hard-delete l'utilisateur
  une fois ce délai écoulé. Tant que l'échéance n'est pas atteinte, le
  user peut annuler.
"""

from __future__ import annotations

from datetime import timedelta
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone

# Délai légal RGPD : 30 jours entre la demande et la suppression définitive.
# Conformément à l'art. 17 du RGPD, on peut différer la suppression pour
# permettre au user de se rétracter (« droit au remords »).
DELETION_GRACE_PERIOD_DAYS = 30

# Durée de vie d'un export généré (URL signée + objet MinIO).
EXPORT_LINK_TTL_HOURS = 24


def _default_scheduled_for() -> timezone.datetime:
    """Calcule l'échéance par défaut d'une demande de suppression."""
    return timezone.now() + timedelta(days=DELETION_GRACE_PERIOD_DAYS)


class ExportRequest(models.Model):
    """Demande d'export RGPD des données d'un user.

    Le user peut demander une archive ZIP de ses données personnelles. La
    génération est asynchrone (Celery). On garde l'historique des demandes
    pour traçabilité, mais une seule peut être active à un instant donné
    (le frontend GET /me/export-data/status récupère la plus récente).
    """

    class Status(models.TextChoices):
        QUEUED = 'queued', 'En attente'
        PROCESSING = 'processing', 'En cours'
        READY = 'ready', 'Prêt au téléchargement'
        EXPIRED = 'expired', 'Lien expiré'
        FAILED = 'failed', 'Échec'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gdpr_export_requests',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    # Clé MinIO de l'archive ZIP générée (vide tant que status != READY).
    file_key = models.CharField(max_length=500, blank=True)
    file_size_bytes = models.BigIntegerField(default=0)
    error_message = models.TextField(blank=True)

    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    # Échéance après laquelle l'archive est supprimée du storage et le
    # status passe à EXPIRED (TTL 24h par défaut).
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'gdpr_export_request'
        ordering: ClassVar[list[str]] = ['-requested_at']
        verbose_name = 'Demande export RGPD'
        verbose_name_plural = 'Demandes export RGPD'
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=['user', '-requested_at']),
        ]

    def __str__(self) -> str:
        return f'Export {self.user_id} ({self.status})'

    @property
    def is_ready(self) -> bool:
        """L'archive est-elle prête et non expirée ?"""
        if self.status != self.Status.READY:
            return False
        return self.expires_at is None or self.expires_at > timezone.now()


class DeletionRequest(models.Model):
    """Demande de suppression de compte RGPD (soft delete + délai 30j).

    Un seul `DeletionRequest` peut exister par user (OneToOne). À la
    création :

    1. `user.is_active = False` (soft delete immédiat → le user ne peut
       plus se connecter et n'apparaît plus dans les listes publiques).
    2. `scheduled_for = now + 30j` (échéance hard delete).
    3. Une tâche Celery beat quotidienne scanne les requests dues et
       appelle `user.delete()` pour cascade-purger toutes les données.

    Le user peut annuler tant que `completed_at is None` (le compte est
    réactivé : `is_active = True`).
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gdpr_deletion_request',
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    # Échéance par défaut : J+30. Calculée à la création.
    scheduled_for = models.DateTimeField(default=_default_scheduled_for)
    # Mis à jour quand le user annule (peut être null → toujours en attente).
    cancelled_at = models.DateTimeField(null=True, blank=True)
    # Mis à jour quand la tâche cron hard-delete l'utilisateur.
    completed_at = models.DateTimeField(null=True, blank=True)
    # Notes libres (optionnel — pourquoi le user demande la suppression).
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'gdpr_deletion_request'
        ordering: ClassVar[list[str]] = ['-requested_at']
        verbose_name = 'Demande suppression RGPD'
        verbose_name_plural = 'Demandes suppression RGPD'

    def __str__(self) -> str:
        if self.completed_at:
            etat = 'effectuée'
        elif self.cancelled_at:
            etat = 'annulée'
        else:
            etat = f'planifiée pour {self.scheduled_for:%Y-%m-%d}'
        return f'Suppression {self.user_id} ({etat})'

    @property
    def is_pending(self) -> bool:
        """La demande est-elle encore active (ni annulée, ni effectuée) ?"""
        return self.cancelled_at is None and self.completed_at is None

    @property
    def is_cancellable(self) -> bool:
        """Le user peut-il encore annuler la suppression ?"""
        # Tant que pas hard-deleté, on autorise l'annulation (même si
        # l'échéance est dépassée tant que la task cron n'est pas passée).
        return self.is_pending
