from django.contrib import admin

from .models import SubscriptionPlan, Subscription


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price_cents", "currency", "interval", "is_active", "stripe_price_id")
    list_filter = ("is_active", "interval", "currency")
    search_fields = ("name", "stripe_price_id")
    ordering = ("price_cents",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "current_period_end", "stripe_subscription_id")
    list_filter = ("status", "plan")
    search_fields = ("stripe_subscription_id", "user__username", "user__email")
    autocomplete_fields = ("user", "plan")
