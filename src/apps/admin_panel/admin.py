"""Admin Django pour AdminAuditLog + AdminDailySnapshot."""

from __future__ import annotations

from django.contrib import admin

from .models import AdminAuditLog, AdminDailySnapshot


@admin.register(AdminAuditLog)
class AdminAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'actor_email',
        'action',
        'target_type',
        'target_id',
        'target_repr',
        'ip_address',
    )
    list_filter = ('action', 'target_type', 'created_at')
    search_fields = ('actor_email', 'target_repr', 'ip_address')
    date_hierarchy = 'created_at'
    readonly_fields = (
        'actor',
        'actor_email',
        'action',
        'target_type',
        'target_id',
        'target_repr',
        'payload',
        'ip_address',
        'user_agent',
        'created_at',
    )

    def has_add_permission(self, request) -> bool:
        return False  # Crées uniquement via log_admin_action()

    def has_change_permission(self, request, obj=None) -> bool:
        return False  # Read-only


@admin.register(AdminDailySnapshot)
class AdminDailySnapshotAdmin(admin.ModelAdmin):
    list_display = ('date', 'created_at')
    date_hierarchy = 'date'
    readonly_fields = ('date', 'payload', 'created_at')

    def has_add_permission(self, request) -> bool:
        return False
