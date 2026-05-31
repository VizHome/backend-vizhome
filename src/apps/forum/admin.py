"""Admin Django pour modération du forum."""
from __future__ import annotations

from django.contrib import admin

from .models import Category, Reply, Topic


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'order', 'is_admin_only', 'topics_count')
    list_editable = ('order', 'is_admin_only')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'category', 'author', 'is_pinned', 'is_locked',
        'replies_count', 'views_count', 'created_at',
    )
    list_filter = ('category', 'is_pinned', 'is_locked', 'created_at')
    list_editable = ('is_pinned', 'is_locked')
    search_fields = ('title', 'content', 'author__email')
    autocomplete_fields = ('author', 'category')
    date_hierarchy = 'created_at'
    readonly_fields = ('views_count', 'replies_count', 'last_reply_at', 'created_at', 'updated_at')


@admin.register(Reply)
class ReplyAdmin(admin.ModelAdmin):
    list_display = ('topic', 'author', 'is_solution', 'created_at')
    list_filter = ('is_solution', 'created_at')
    list_editable = ('is_solution',)
    search_fields = ('content', 'author__email', 'topic__title')
    autocomplete_fields = ('author', 'topic')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'updated_at')
