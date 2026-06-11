"""Envoi d'emails transactionnels HTML brandés VizHome.

Tous les emails sortants passent par `send_templated_email` : une paire de
templates `emails/<name>.html` + `emails/<name>.txt` (fallback texte) est
rendue avec le contexte fourni, enrichi de `frontend_url`.

Les templates vivent dans `apps/core/templates/emails/` et étendent
`emails/base_email.html` (layout table email-safe, styles inline,
compatible Gmail / Outlook).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_templated_email(
    *,
    subject: str,
    recipients: Sequence[str],
    template: str,
    context: dict | None = None,
    fail_silently: bool = True,
    reply_to: Sequence[str] | None = None,
) -> bool:
    """Rend `emails/<template>.html` + `.txt` et envoie l'email.

    Retourne True si l'envoi a réussi. En mode `fail_silently` (défaut),
    les erreurs SMTP sont loggées mais ne remontent pas : un email de
    notification ne doit jamais faire échouer le flux métier appelant.
    """
    if not recipients:
        return False

    ctx = {
        'frontend_url': settings.FRONTEND_URL,
        'subject': subject,
        **(context or {}),
    }
    text_body = render_to_string(f'emails/{template}.txt', ctx)
    html_body = render_to_string(f'emails/{template}.html', ctx)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=list(recipients),
        reply_to=list(reply_to) if reply_to else None,
    )
    msg.attach_alternative(html_body, 'text/html')

    try:
        msg.send(fail_silently=False)
    except Exception:
        if not fail_silently:
            raise
        logger.exception("Échec envoi email template '%s'", template)
        return False
    return True
