"""Tâches Celery pour la génération asynchrone de rendus IA."""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models import F
from django.utils import timezone

from apps.accounts.models import UserStats

from .models import Render
from .providers import ProviderError, get_provider

logger = logging.getLogger(__name__)

# Instructions injectées AVANT le prompt utilisateur selon la source du
# render. Sans elles, le modèle image-to-image de Gemini a tendance à
# "éditer" l'image d'entrée (il redessine le croquis en plus propre, ou
# incruste le bloc 3D gris tel quel dans un décor) au lieu de la
# transformer en rendu photoréaliste.
SOURCE_INSTRUCTIONS: dict[str, str] = {
    Render.Source.SKETCH: (
        'Transform this rough hand-drawn sketch into a photorealistic '
        'architectural photograph. Use the sketch ONLY as a guide for the '
        'composition, layout and proportions. Render real materials, '
        'realistic lighting, vegetation, sky and surroundings. The final '
        'image must look like a professional photograph of a real building, '
        'with absolutely no visible sketch lines or drawing style. '
    ),
    Render.Source.SCREENSHOT: (
        'This image is an untextured 3D massing model (plain gray volume). '
        'Replace the gray volume entirely with a fully detailed, '
        'photorealistic building that keeps the same overall shape, '
        'footprint and camera angle. Add realistic facade materials, '
        'windows, doors, roofing, landscaping and ambient context. '
        'Do NOT keep any gray untextured surface in the final image. '
    ),
}


@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def generate_render(self, render_id: int) -> None:
    """Traite un Render en pending : appelle le provider IA et stocke le résultat.

    En cas d'erreur transitoire (réseau, rate limit), retry jusqu'à 2 fois.
    En cas d'erreur métier (prompt invalide, quota provider…), marque failed.
    """
    try:
        render = Render.objects.select_related('user__stats').get(pk=render_id)
    except Render.DoesNotExist:
        logger.error('Render %s introuvable', render_id)
        return

    if render.is_terminal:
        logger.warning('Render %s déjà terminal (%s), skip', render.pk, render.status)
        return

    render.status = Render.Status.PROCESSING
    render.started_at = timezone.now()
    render.save(update_fields=['status', 'started_at', 'updated_at'])

    try:
        provider = get_provider(settings.RENDERS_DEFAULT_PROVIDER)

        input_bytes: bytes | None = None
        if render.input_image:
            with render.input_image.open('rb') as f:
                input_bytes = f.read()

        # Préfixe l'instruction de transformation selon la source (no-op
        # pour source=prompt qui n'a pas d'image d'entrée à transformer).
        instruction = SOURCE_INSTRUCTIONS.get(render.source, '')
        full_prompt = f'{instruction}{render.prompt}'.strip()

        result = provider.generate(
            prompt=full_prompt,
            output_type=render.output_type,
            input_image_bytes=input_bytes,
            style_hint=render.style_hint,
        )

        # Stocke le résultat (le storage backend décide où — local en dev, S3 en prod)
        ext = 'png' if 'png' in result.mime_type else 'jpg'
        filename = f'render_{render.pk}.{ext}'
        render.result_image.save(filename, ContentFile(result.image_bytes), save=False)
        render.provider = provider.name
        render.provider_response_id = result.provider_response_id
        render.status = Render.Status.DONE
        render.completed_at = timezone.now()
        render.save()

        # Incrément atomique du compteur mensuel
        UserStats.objects.filter(user=render.user).update(
            renders_this_month=F('renders_this_month') + 1
        )

        logger.info('Render %s terminé via %s', render.pk, provider.name)

    except ProviderError as e:
        # Erreur métier : ne pas retry
        logger.warning('Render %s échoué : %s', render.pk, e)
        render.status = Render.Status.FAILED
        render.error_message = str(e)
        render.completed_at = timezone.now()
        render.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])

    except Exception as e:
        logger.exception('Render %s : erreur inattendue', render.pk)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e) from e
        render.status = Render.Status.FAILED
        render.error_message = f'Erreur interne après {self.max_retries} retries : {e}'
        render.completed_at = timezone.now()
        render.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
