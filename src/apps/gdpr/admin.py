"""Admin Django pour visualiser les demandes RGPD.

Pas d'action de modification : les staff ne doivent pas pouvoir altérer
les `DeletionRequest` ou `ExportRequest` à la main (sinon on contourne le
flow de consentement utilisateur). Lecture seule sauf forçage manuel.
"""

from __future__ import annotations

from typing import ClassVar

from django.contrib import admin

from .models import DeletionRequest, ExportRequest


@admin.register(ExportRequest)
class ExportRequestAdmin(admin.ModelAdmin):
    list_display: ClassVar[tuple[str, ...]] = (
        'id',
        'user',
        'status',
        'requested_at',
        'completed_at',
        'expires_at',
        'file_size_bytes',
    )
    list_filter: ClassVar[tuple[str, ...]] = ('status',)
    search_fields: ClassVar[tuple[str, ...]] = ('user__email', 'user__pseudo')
    readonly_fields: ClassVar[tuple[str, ...]] = (
        'user',
        'status',
        'file_key',
        'file_size_bytes',
        'error_message',
        'requested_at',
        'completed_at',
        'expires_at',
    )
    ordering: ClassVar[tuple[str, ...]] = ('-requested_at',)

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return False


@admin.register(DeletionRequest)
class DeletionRequestAdmin(admin.ModelAdmin):
    list_display: ClassVar[tuple[str, ...]] = (
        'id',
        'user',
        'requested_at',
        'scheduled_for',
        'cancelled_at',
        'completed_at',
    )
    list_filter: ClassVar[tuple[str, ...]] = ('cancelled_at', 'completed_at')
    search_fields: ClassVar[tuple[str, ...]] = ('user__email', 'user__pseudo')
    readonly_fields: ClassVar[tuple[str, ...]] = (
        'user',
        'requested_at',
        'scheduled_for',
        'cancelled_at',
        'completed_at',
        'notes',
    )
    ordering: ClassVar[tuple[str, ...]] = ('-requested_at',)

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return False
