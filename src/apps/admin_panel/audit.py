"""Helpers pour logger les actions admin de façon uniforme."""

from __future__ import annotations

from typing import Any

from rest_framework.request import Request

from .models import AdminAuditLog


def _get_client_ip(request: Request) -> str | None:
    """Récupère l'IP client en tenant compte du reverse proxy (X-Forwarded-For)."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def log_admin_action(
    request: Request,
    action: str,
    *,
    target: Any | None = None,
    payload: dict[str, Any] | None = None,
) -> AdminAuditLog | None:
    """Enregistre une action admin dans l'audit log.

    `target` peut être n'importe quel modèle Django — on snapshot son
    `type` (nom de classe) + `id` + `str()` representation.
    `payload` est un dict JSON libre (ex: {'before': ..., 'after': ...}).

    Retourne le AdminAuditLog créé, ou None si l'utilisateur n'est pas
    authentifié (cas anormal, ne devrait pas arriver pour les actions admin).
    """
    actor = getattr(request, "user", None)
    if not actor or not actor.is_authenticated:
        return None

    target_type = ""
    target_id = None
    target_repr = ""
    if target is not None:
        target_type = type(target).__name__
        target_id = getattr(target, "pk", None)
        try:
            target_repr = str(target)[:255]
        except Exception:
            target_repr = f"{target_type}#{target_id}"

    return AdminAuditLog.objects.create(
        actor=actor,
        actor_email=getattr(actor, "email", "") or "",
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_repr=target_repr,
        payload=payload or {},
        ip_address=_get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
    )
