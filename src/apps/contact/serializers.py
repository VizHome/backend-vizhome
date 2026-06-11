"""Serializers du form de contact public.

Le serializer valide la payload envoyée par `useContact.send()` côté frontend
(`composables/useContact.ts`). Les choix de `subject` correspondent aux
valeurs hardcodées dans le Select du formulaire (`pages/contact.vue`).
"""

from __future__ import annotations

from rest_framework import serializers

SUBJECT_CHOICES = [
    ('general', 'Question générale'),
    ('sales', 'Demande commerciale'),
    ('support', 'Support technique'),
    ('partnership', 'Partenariat'),
    ('feedback', "Retour d'expérience"),
    ('other', 'Autre'),
]


class ContactMessageSerializer(serializers.Serializer):
    """Représente un message envoyé via /api/v1/contact/."""

    name = serializers.CharField(min_length=3, max_length=100, trim_whitespace=True)
    email = serializers.EmailField()
    subject = serializers.ChoiceField(choices=SUBJECT_CHOICES)
    message = serializers.CharField(min_length=20, max_length=1000, trim_whitespace=True)
    privacy_accepted = serializers.BooleanField()
    newsletter_opt_in = serializers.BooleanField(required=False, default=False)

    def validate_privacy_accepted(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError(
                "L'acceptation de la politique de confidentialité est obligatoire."
            )
        return value
