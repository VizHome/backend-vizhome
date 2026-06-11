"""Modèles de l'app projects : Project + Scene + ImportedModel + Annotation + ShareLink."""

from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


def _default_transform() -> dict:
    return {'x': 0.0, 'y': 0.0, 'z': 0.0}


def _default_scale() -> dict:
    return {'x': 1.0, 'y': 1.0, 'z': 1.0}


def _generate_share_token() -> str:
    return secrets.token_urlsafe(32)


class Project(models.Model):
    """Un projet 3D — conteneur d'une scène Three.js et de ses assets."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='projects'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    thumbnail = models.ImageField(upload_to='projects/thumbnails/%Y/%m/', blank=True, null=True)
    is_archived = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'projects_project'
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['user', '-updated_at'])]

    def __str__(self) -> str:
        return f'{self.title} ({self.user.email})'


class Scene(models.Model):
    """État Three.js complet — caméra, lumières, météo, navigation, etc.

    Le schéma du JSON est owned par le frontend (composables useThree*).
    Backend persiste tel quel, sans validation de structure.
    """

    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='scene')
    data = models.JSONField(default=dict, blank=True)
    version = models.PositiveIntegerField(default=1)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'projects_scene'

    def __str__(self) -> str:
        return f'Scene de {self.project.title} (v{self.version})'


class ImportedModel(models.Model):
    """Modèle 3D importé dans un projet (GLB/OBJ/FBX/STL)."""

    class Format(models.TextChoices):
        GLB = 'glb', 'GLB'
        GLTF = 'gltf', 'glTF'
        OBJ = 'obj', 'Wavefront OBJ'
        FBX = 'fbx', 'FBX'
        STL = 'stl', 'STL'

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='imported_models')
    name = models.CharField(max_length=200)
    format = models.CharField(max_length=10, choices=Format.choices)

    file = models.FileField(upload_to='projects/models/%Y/%m/')
    mtl_file = models.FileField(
        upload_to='projects/models/%Y/%m/',
        blank=True,
        null=True,
        help_text='Fichier .mtl associé (uniquement pour les .obj)',
    )
    file_size_bytes = models.BigIntegerField(
        help_text='Taille totale (file + mtl) — utilisée pour les quotas storage',
    )

    # Transform Three.js (3 axes)
    position = models.JSONField(default=_default_transform)
    rotation = models.JSONField(default=_default_transform)
    scale = models.JSONField(default=_default_scale)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'projects_imported_model'
        ordering = ['created_at']

    def __str__(self) -> str:
        return f'{self.name} ({self.format})'


class Annotation(models.Model):
    """Annotation 3D positionnée dans une scène (note, mesure, etc.)."""

    class Type(models.TextChoices):
        NOTE = 'note', 'Note'
        MEASURE = 'measure', 'Mesure'
        MARKER = 'marker', 'Marqueur'

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='annotations')
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.NOTE)
    position = models.JSONField()  # {x, y, z}
    content = models.TextField(blank=True)
    color = models.CharField(max_length=20, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'projects_annotation'
        ordering = ['created_at']

    def __str__(self) -> str:
        return f'{self.type} on {self.project.title}'


class ShareLink(models.Model):
    """Lien public d'un projet — accès read-only via token URL."""

    class Permission(models.TextChoices):
        VIEW = 'view', 'Lecture seule'
        # EDIT n'est pas implémenté pour l'instant ; à ajouter avec un flow de
        # claim si on veut un mode collaboratif

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='share_links')
    token = models.CharField(
        max_length=64, unique=True, db_index=True, default=_generate_share_token
    )
    permission = models.CharField(
        max_length=20, choices=Permission.choices, default=Permission.VIEW
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_share_links',
    )

    class Meta:
        db_table = 'projects_share_link'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'Share {self.token[:8]}… for {self.project.title}'

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at < timezone.now()
