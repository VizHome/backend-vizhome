"""Permissions DRF custom pour l'app projects."""

from __future__ import annotations

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class IsProjectOwner(BasePermission):
    """Le user doit être propriétaire du Project (vérification sur l'objet)."""

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        # obj peut être un Project, ou un objet lié (Scene, ImportedModel, …)
        project = obj if hasattr(obj, "user") else obj.project
        return project.user_id == request.user.id
