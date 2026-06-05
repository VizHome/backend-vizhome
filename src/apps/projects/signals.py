"""Signaux : auto-Scene à la création, sync storage stats à l'upload/delete de modèles."""

from __future__ import annotations

from typing import Any

from django.db.models import F
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.accounts.models import UserStats

from .models import ImportedModel, Project, Scene


@receiver(post_save, sender=Project)
def create_scene_for_new_project(
    sender: type[Project], instance: Project, created: bool, **kwargs: Any
) -> None:
    """À la création d'un projet, instancie sa Scene vide."""
    if created:
        Scene.objects.create(project=instance)
        UserStats.objects.filter(user=instance.user).update(
            total_projects=F("total_projects") + 1
        )


@receiver(post_delete, sender=Project)
def decrement_project_count(
    sender: type[Project], instance: Project, **kwargs: Any
) -> None:
    UserStats.objects.filter(user=instance.user).update(
        total_projects=F("total_projects") - 1
    )


@receiver(post_save, sender=ImportedModel)
def increment_storage_on_model_save(
    sender: type[ImportedModel], instance: ImportedModel, created: bool, **kwargs: Any
) -> None:
    """À l'ajout d'un ImportedModel, incrémente le storage usage du user."""
    if created:
        UserStats.objects.filter(user=instance.project.user).update(
            storage_used_bytes=F("storage_used_bytes") + instance.file_size_bytes
        )


@receiver(post_delete, sender=ImportedModel)
def decrement_storage_on_model_delete(
    sender: type[ImportedModel], instance: ImportedModel, **kwargs: Any
) -> None:
    UserStats.objects.filter(user=instance.project.user).update(
        storage_used_bytes=F("storage_used_bytes") - instance.file_size_bytes
    )
    # Nettoie les fichiers du storage
    if instance.file:
        instance.file.delete(save=False)
    if instance.mtl_file:
        instance.mtl_file.delete(save=False)
