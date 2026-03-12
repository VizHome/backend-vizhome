from django.conf import settings
from django.db import models


class SubscriptionPlan(models.Model):
    INTERVAL_MONTH = "month"
    INTERVAL_YEAR = "year"
    INTERVAL_CHOICES = [
        (INTERVAL_MONTH, "Monthly"),
        (INTERVAL_YEAR, "Yearly"),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price_cents = models.PositiveIntegerField(help_text="Price in cents")
    currency = models.CharField(max_length=10, default="usd")
    interval = models.CharField(max_length=10, choices=INTERVAL_CHOICES, default=INTERVAL_MONTH)

    # Stripe linkage (pre-created in Stripe dashboard)
    stripe_price_id = models.CharField(max_length=100, unique=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Subscription Plan"
        verbose_name_plural = "Subscription Plans"
        ordering = ["price_cents"]

    def __str__(self) -> str:
        return f"{self.name} ({self.price_cents/100:.2f} {self.currency}/{self.interval})"


class Subscription(models.Model):
    STATUS_INCOMPLETE = "incomplete"
    STATUS_ACTIVE = "active"
    STATUS_PAST_DUE = "past_due"
    STATUS_CANCELED = "canceled"
    STATUS_INCOMPLETE_EXPIRED = "incomplete_expired"
    STATUS_TRIALING = "trialing"
    STATUS_UNPAID = "unpaid"

    STATUS_CHOICES = [
        (STATUS_INCOMPLETE, "Incomplete"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAST_DUE, "Past due"),
        (STATUS_CANCELED, "Canceled"),
        (STATUS_INCOMPLETE_EXPIRED, "Incomplete expired"),
        (STATUS_TRIALING, "Trialing"),
        (STATUS_UNPAID, "Unpaid"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions")

    stripe_subscription_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_INCOMPLETE)

    current_period_end = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Subscription"
        verbose_name_plural = "Subscriptions"
        indexes = [
            models.Index(fields=["stripe_subscription_id"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.plan} [{self.status}]"
