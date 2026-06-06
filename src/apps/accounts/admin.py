"""Admin Django pour les modèles d'accounts."""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, UserPreferences, UserSession, UserStats


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)
    list_display = (
        "email",
        "first_name",
        "last_name",
        "plan",
        "is_active",
        "is_staff",
        "date_joined",
    )
    list_filter = ("plan", "is_active", "is_staff", "is_superuser")
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("date_joined", "last_login")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Profil"), {"fields": ("first_name", "last_name", "avatar_url")}),
        (_("Plan"), {"fields": ("plan",)}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Dates"), {"fields": ("date_joined", "last_login")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )


@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    list_display = ("user", "theme", "language", "render_quality", "two_factor_enabled")
    list_filter = ("theme", "language", "render_quality")
    search_fields = ("user__email",)
    raw_id_fields = ("user",)


@admin.register(UserStats)
class UserStatsAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "renders_this_month",
        "renders_limit",
        "total_projects",
        "storage_used_bytes",
    )
    search_fields = ("user__email",)
    raw_id_fields = ("user",)


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "device_name",
        "ip_address",
        "created_at",
        "last_active",
        "is_active",
    )
    list_filter = ("revoked_at",)
    search_fields = ("user__email", "device_name", "ip_address")
    readonly_fields = ("refresh_jti", "created_at", "last_active")
    raw_id_fields = ("user",)
