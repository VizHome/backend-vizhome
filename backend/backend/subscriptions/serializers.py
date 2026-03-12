from rest_framework import serializers

from .models import Subscription, SubscriptionPlan


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    price = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPlan
        fields = [
            "id",
            "name",
            "description",
            "price_cents",
            "price",
            "currency",
            "interval",
            "stripe_price_id",
        ]

    def get_price(self, obj: SubscriptionPlan) -> str:
        return f"{obj.price_cents/100:.2f} {obj.currency}/{obj.interval}"


class CreateCheckoutSessionSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField()
    success_url = serializers.URLField()
    cancel_url = serializers.URLField()


class CurrentSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            "id",
            "status",
            "stripe_subscription_id",
            "current_period_end",
            "is_active",
            "plan",
        ]

    def get_is_active(self, obj: Subscription) -> bool:
        return obj.status == Subscription.STATUS_ACTIVE
