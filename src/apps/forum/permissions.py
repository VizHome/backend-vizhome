"""Permissions DRF custom pour le forum.

- `IsAuthorOrReadOnly` : lecture publique, écriture seulement par l'auteur
- `IsAuthorOrStaff` : édition/suppression par l'auteur OU le staff (modo)
- `IsAuthorWithinTimeWindowOrStaff` : édition/suppression par l'auteur
  uniquement dans une fenêtre temporelle (défaut 15 min), staff toujours OK
- `CanPostInCategory` : restreint la création de topic dans une cat
  `is_admin_only=True` aux seuls staff
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class IsAuthorOrReadOnly(BasePermission):
    """GET ouvert à tous, écriture seulement par l'auteur de l'objet."""

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return getattr(obj, 'author_id', None) == request.user.id


class IsAuthorOrStaff(BasePermission):
    """Auteur OU staff (modo) peut modifier/supprimer."""

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        if request.method in SAFE_METHODS:
            return True
        if request.user.is_staff:
            return True
        return getattr(obj, 'author_id', None) == request.user.id


class IsAuthorWithinTimeWindowOrStaff(BasePermission):
    """Édition limitée dans le temps pour l'auteur, illimitée pour le staff.

    L'auteur peut éditer son propre post dans les `EDIT_WINDOW_MINUTES`
    minutes qui suivent sa création (15 min par défaut). Passé ce délai,
    seul le staff peut éditer. DELETE reste autorisée à l'auteur tant
    que le post n'est pas trop vieux (même fenêtre).

    Lit `EDIT_WINDOW_MINUTES` sur la view si défini, sinon 15.
    """

    message = (
        "La fenêtre d'édition (15 minutes après publication) est dépassée. "
        "Seul le staff peut maintenant modifier ce message."
    )

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        if request.method in SAFE_METHODS:
            return True
        if request.user.is_staff:
            return True
        if getattr(obj, 'author_id', None) != request.user.id:
            return False
        # Author : check fenêtre temporelle
        window_min = getattr(view, 'EDIT_WINDOW_MINUTES', 15)
        deadline = obj.created_at + timedelta(minutes=window_min)
        return timezone.now() <= deadline
