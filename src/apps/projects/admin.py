"""Admin Django pour l'app projects."""
from __future__ import annotations

from django.contrib import admin

from .models import Annotation, ImportedModel, Project, Scene, ShareLink


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'user', 'is_archived', 'created_at', 'updated_at')
    list_filter = ('is_archived',)
    search_fields = ('title', 'user__email')
    raw_id_fields = ('user',)


@admin.register(Scene)
class SceneAdmin(admin.ModelAdmin):
    list_display = ('project', 'version', 'updated_at')
    raw_id_fields = ('project',)


@admin.register(ImportedModel)
class ImportedModelAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'project', 'format', 'file_size_bytes', 'created_at')
    list_filter = ('format',)
    search_fields = ('name', 'project__title')
    raw_id_fields = ('project',)


@admin.register(Annotation)
class AnnotationAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'type', 'created_at')
    list_filter = ('type',)
    raw_id_fields = ('project',)


@admin.register(ShareLink)
class ShareLinkAdmin(admin.ModelAdmin):
    list_display = ('token_short', 'project', 'permission', 'expires_at', 'created_at')
    list_filter = ('permission',)
    search_fields = ('project__title', 'token')
    raw_id_fields = ('project', 'created_by')
    readonly_fields = ('token', 'last_used_at')

    def token_short(self, obj):
        return obj.token[:12] + '…'
