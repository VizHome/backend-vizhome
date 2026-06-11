"""Admin Django pour les abonnés newsletter (opt-in via form de contact)."""

from __future__ import annotations

from django.contrib import admin

from .models import NewsletterSubscriber


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ('email', 'source', 'is_active', 'subscribed_at')
    list_filter = ('source', 'is_active', 'subscribed_at')
    search_fields = ('email',)
    readonly_fields = ('subscribed_at',)
    ordering = ('-subscribed_at',)
