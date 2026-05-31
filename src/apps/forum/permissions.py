"""Permissions DRF custom pour le forum.

- `IsAuthorOrReadOnly` : lecture publique, écriture seulement par l'auteur
- `IsAuthorOrStaff` : édition/suppression par l'auteur OU le staff (modo)
- `CanPostInCategory` : restreint la création de topic dans une cat
  `is_admin_only=True` aux seuls staff
"""
from __future__ import annotations

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
