"""Django admin pour SupportTicket / SupportMessage."""
from django.contrib import admin

from .models import SupportMessage, SupportTicket


class SupportMessageInline(admin.TabularInline):
    model = SupportMessage
    extra = 0
    readonly_fields = ('author', 'from_staff', 'created_at')
    fields = ('author', 'from_staff', 'body', 'created_at')


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject', 'user', 'status', 'priority', 'assignee', 'updated_at')
    list_filter = ('status', 'priority', 'category')
    search_fields = ('subject', 'user__email', 'user__pseudo')
    raw_id_fields = ('user', 'assignee')
    inlines = [SupportMessageInline]
    readonly_fields = ('created_at', 'updated_at', 'closed_at')


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket', 'author', 'from_staff', 'created_at')
    list_filter = ('from_staff',)
    raw_id_fields = ('ticket', 'author')
    readonly_fields = ('created_at',)
