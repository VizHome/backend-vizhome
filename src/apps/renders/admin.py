"""Admin Django pour la supervision des renders."""

from __future__ import annotations

from django.contrib import admin

from .models import Render


@admin.register(Render)
class RenderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "source",
        "output_type",
        "status",
        "provider",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "source", "output_type", "provider")
    search_fields = ("user__email", "prompt", "style_hint", "title")
    readonly_fields = (
        "provider_response_id",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    )
    raw_id_fields = ("user",)
    date_hierarchy = "created_at"
