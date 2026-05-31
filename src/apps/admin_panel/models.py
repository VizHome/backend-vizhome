"""Modèles internes du panel admin (audit log, snapshots).

L'app admin_panel ne devrait pas avoir de modèles métier (elle ne fait
que des read-only sur les autres apps), mais on a besoin de stocker :
- L'audit log des actions admin (qui a fait quoi, quand)
- Les snapshots quotidiens des métriques (historique long terme)
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class AdminAuditLog(models.Model):
    """Trace toutes les actions du staff (modération, ban, etc.).

    Stocke :
    - L'acteur (l'admin qui fait l'action) — null si l'acteur est supprimé
    - L'action sous forme de string courte (ex: 'user.ban', 'topic.pin')
    - La cible (type + id) — pour pouvoir retrouver l'objet
    - Un payload JSON libre (avant/après, raisons, etc.)
    - IP + user agent pour la traçabilité

    Indexé sur (created_at) + (target_type, target_id) pour les requêtes
    fréquentes "qui a touché cet objet récemment ?".
    """

    class Action(models.TextChoices):
        USER_BAN = 'user.ban', 'Bannir un user'
        USER_UNBAN = 'user.unban', 'Réactiver un user'
        USER_PROMOTE_STAFF = 'user.promote_staff', 'Promouvoir staff'
        USER_DEMOTE_STAFF = 'user.demote_staff', 'Retirer staff'
        TOPIC_PIN = 'topic.pin', 'Épingler un topic'
        TOPIC_UNPIN = 'topic.unpin', 'Désépingler un topic'
        TOPIC_LOCK = 'topic.lock', 'Verrouiller un topic'
        TOPIC_UNLOCK = 'topic.unlock', 'Déverrouiller un topic'
        TOPIC_DELETE = 'topic.delete', 'Supprimer un topic'
        REPLY_DELETE = 'reply.delete', 'Supprimer une réponse'
        REPLY_MARK_SOLUTION = 'reply.mark_solution', 'Marquer solution'

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='admin_actions',
    )
    actor_email = models.CharField(max_length=255, blank=True)  # snapshot
    action = models.CharField(max_length=50, choices=Action.choices)
    # Cible générique : pas de FK pour éviter les CASCADE qui supprimeraient
    # les logs si l'objet est supprimé (logs doivent survivre)
    target_type = models.CharField(max_length=50, blank=True)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    target_repr = models.CharField(max_length=255, blank=True)
    # Métadonnées libres (avant/après, raison, etc.)
    payload = models.JSONField(default=dict, blank=True)
    # Traçabilité réseau
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'admin_audit_log'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['target_type', 'target_id']),
            models.Index(fields=['action']),
        ]

    def __str__(self) -> str:
        actor = self.actor_email or '(deleted)'
        return f'[{self.created_at:%Y-%m-%d %H:%M}] {actor} → {self.action}'


class AdminDailySnapshot(models.Model):
    """Snapshot quotidien des métriques admin (historique long terme).

    Une entrée par jour, rempli par la management command
    `snapshot_admin_metrics` qu'on lance via Celery beat chaque nuit.

    Stocke l'overview complet en JSON pour pouvoir afficher l'évolution
    d'année en année sans recomputer depuis les tables sources.
    """

    date = models.DateField(unique=True)
    # Snapshot complet : copie de AdminOverviewView.get response
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'admin_daily_snapshot'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['-date']),
        ]

    def __str__(self) -> str:
        return f'Snapshot {self.date}'
