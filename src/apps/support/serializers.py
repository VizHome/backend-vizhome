"""Serializers DRF pour le support."""
from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import SupportMessage, SupportTicket


class _AuthorMiniSerializer(serializers.Serializer):
    """Représentation minimale d'un auteur de message (compatible forum)."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    pseudo = serializers.CharField(read_only=True)
    is_staff = serializers.BooleanField(read_only=True)


class SupportMessageSerializer(serializers.ModelSerializer):
    author = _AuthorMiniSerializer(read_only=True)

    class Meta:
        model = SupportMessage
        fields = ('id', 'author', 'from_staff', 'body', 'created_at')
        read_only_fields = ('id', 'author', 'from_staff', 'created_at')


class SupportMessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportMessage
        fields = ('body',)

    def validate_body(self, value: str) -> str:
        clean = (value or '').strip()
        if len(clean) < 2:
            raise serializers.ValidationError('Le message est trop court.')
        if len(clean) > 10_000:
            raise serializers.ValidationError('Le message est trop long (max 10 000 caractères).')
        return clean


class SupportTicketListSerializer(serializers.ModelSerializer):
    """Liste — compact, sans le détail des messages."""

    user_email = serializers.CharField(source='user.email', read_only=True)
    user_pseudo = serializers.CharField(source='user.pseudo', read_only=True)
    assignee_pseudo = serializers.CharField(
        source='assignee.pseudo', read_only=True, default=None,
    )
    messages_count = serializers.IntegerField(read_only=True)
    last_message_at = serializers.DateTimeField(read_only=True)
    last_message_from_staff = serializers.BooleanField(read_only=True)

    class Meta:
        model = SupportTicket
        fields = (
            'id', 'subject', 'category', 'status', 'priority',
            'user_email', 'user_pseudo',
            'assignee_pseudo',
            'messages_count', 'last_message_at', 'last_message_from_staff',
            'created_at', 'updated_at', 'closed_at',
        )
        read_only_fields = fields


class SupportTicketDetailSerializer(SupportTicketListSerializer):
    """Détail — inclut les messages threadés."""

    messages = SupportMessageSerializer(many=True, read_only=True)

    class Meta(SupportTicketListSerializer.Meta):
        fields = SupportTicketListSerializer.Meta.fields + ('messages',)


class SupportTicketCreateSerializer(serializers.ModelSerializer):
    """Création — body est le 1er message, transformé en SupportMessage."""

    body = serializers.CharField(write_only=True, min_length=2, max_length=10_000)

    class Meta:
        model = SupportTicket
        fields = ('subject', 'category', 'priority', 'body')

    def validate_subject(self, value: str) -> str:
        clean = value.strip()
        if len(clean) < 5:
            raise serializers.ValidationError('Le sujet doit faire au moins 5 caractères.')
        return clean

    def create(self, validated_data: dict[str, Any]) -> SupportTicket:
        body = validated_data.pop('body')
        user = self.context['request'].user
        ticket = SupportTicket.objects.create(user=user, **validated_data)
        SupportMessage.objects.create(
            ticket=ticket,
            author=user,
            from_staff=False,
            body=body,
        )
        # Notifie l'équipe support (mail aux staff actifs).
        # fail_silently=True à l'intérieur → un SMTP down ne bloque pas la création.
        from .notifications import notify_staff_new_ticket
        notify_staff_new_ticket(ticket)
        return ticket


class SupportTicketUpdateStatusSerializer(serializers.ModelSerializer):
    """Staff change le status / la priority / assigne."""

    class Meta:
        model = SupportTicket
        fields = ('status', 'priority', 'assignee')
