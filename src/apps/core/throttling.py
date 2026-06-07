"""Throttles DRF transverses (utilisés par plusieurs apps).

Les throttles spécifiques à une app restent dans `apps/<app>/throttling.py`
(p. ex. `apps/accounts/throttling.py` pour login/register/forgot-password).
"""

from __future__ import annotations

from rest_framework.throttling import UserRateThrottle


class RenderCreateThrottle(UserRateThrottle):
    """Limite la cadence de POST /renders/ (génération IA coûteuse)."""

    scope = 'render-create'


class ForumWriteThrottle(UserRateThrottle):
    """Limite la cadence d'écriture forum (topics + replies) — anti-flood."""

    scope = 'forum-write'


class SupportCreateThrottle(UserRateThrottle):
    """Limite la création de tickets support — anti-spam user."""

    scope = 'support-create'
