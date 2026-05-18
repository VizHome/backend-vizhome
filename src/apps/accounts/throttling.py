"""Throttles DRF spécifiques aux endpoints d'auth sensibles."""
from __future__ import annotations

from rest_framework.throttling import AnonRateThrottle


class RegisterThrottle(AnonRateThrottle):
    scope = 'register'


class ForgotPasswordThrottle(AnonRateThrottle):
    scope = 'forgot-password'


class LoginThrottle(AnonRateThrottle):
    scope = 'login'
