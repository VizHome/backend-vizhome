"""Modèles de l'app renders : un seul model Render couvre les 3 sources."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class Render(models.Model):
    """Une demande de génération IA — du prompt brut jusqu'au résultat stocké."""

    class Source(models.TextChoices):
        PROMPT = 'prompt', 'Prompt textuel'
        SKETCH = 'sketch', 'Croquis 2D'
        SCREENSHOT = 'screenshot', 'Capture 3D'

    class OutputType(models.TextChoices):
        IMAGE_2D = '2d', 'Image 2D'
        MODEL_3D = '3d', 'Modèle 3D'

    class Status(models.TextChoices):
        PENDING = 'pending', 'En attente'
        PROCESSING = 'processing', 'En cours'
        DONE = 'done', 'Terminé'
        FAILED = 'failed', 'Échoué'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='renders'
    )

    # ─── Input ────────────────────────────────────────────────────────────────
    source = models.CharField(max_length=20, choices=Source.choices)
    output_type = models.CharField(
        max_length=10, choices=OutputType.choices, default=OutputType.IMAGE_2D
    )
    prompt = models.TextField(blank=True)
    style_hint = models.CharField(max_length=200, blank=True)
    input_image = models.ImageField(
        upload_to='renders/inputs/%Y/%m/', blank=True, null=True
    )

    # ─── Output ───────────────────────────────────────────────────────────────
    result_image = models.ImageField(
        upload_to='renders/outputs/%Y/%m/', blank=True, null=True
    )

    # ─── État du pipeline ─────────────────────────────────────────────────────
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    error_message = models.TextField(blank=True)

    # ─── Provider IA ──────────────────────────────────────────────────────────
    provider = models.CharField(max_length=50, blank=True)
    provider_response_id = models.CharField(max_length=200, blank=True)
    cost_credits = models.PositiveIntegerField(default=1)

    # ─── Métadonnées galerie ──────────────────────────────────────────────────
    title = models.CharField(max_length=200, blank=True)

    # ─── Timestamps ───────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'renders_render'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self) -> str:
        snippet = (self.prompt or self.style_hint or self.source)[:50]
        return f'#{self.pk} {self.source}: {snippet}'

    @property
    def is_terminal(self) -> bool:
        return self.status in (self.Status.DONE, self.Status.FAILED)
