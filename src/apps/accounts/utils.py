"""Utilitaires : parsing User-Agent + extraction IP."""
from __future__ import annotations

import re

from django.http import HttpRequest


def parse_device_name(user_agent: str) -> str:
    """Parse minimaliste du User-Agent → 'Chrome — Windows' etc."""
    if not user_agent:
        return 'Inconnu'

    # OS
    if re.search(r'iPad', user_agent):
        os = 'iPad'
    elif re.search(r'iPhone', user_agent):
        os = 'iPhone'
    elif re.search(r'Android', user_agent):
        os = 'Android'
    elif re.search(r'Windows', user_agent):
        os = 'Windows'
    elif re.search(r'Mac OS X', user_agent):
        os = 'Mac'
    elif re.search(r'Linux', user_agent):
        os = 'Linux'
    else:
        os = 'Inconnu'

    # Browser (ordre important : Edge avant Chrome, etc.)
    if re.search(r'Edg/', user_agent):
        browser = 'Edge'
    elif re.search(r'CriOS', user_agent):
        browser = 'Chrome'
    elif re.search(r'FxiOS', user_agent):
        browser = 'Firefox'
    elif re.search(r'Firefox', user_agent):
        browser = 'Firefox'
    elif re.search(r'Chrome', user_agent):
        browser = 'Chrome'
    elif re.search(r'Safari', user_agent):
        browser = 'Safari'
    else:
        browser = 'Navigateur'

    return f'{browser} — {os}'


def get_client_ip(request: HttpRequest) -> str | None:
    """Extrait l'IP du client en tenant compte des proxies."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')
