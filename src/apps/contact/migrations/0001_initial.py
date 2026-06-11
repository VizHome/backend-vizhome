"""Initial migration : NewsletterSubscriber."""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies: list = []

    operations = [
        migrations.CreateModel(
            name="NewsletterSubscriber",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "email",
                    models.EmailField(db_index=True, max_length=254, unique=True),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("contact_form", "Formulaire de contact"),
                            ("footer", "Inscription footer"),
                            ("manual", "Ajout manuel staff"),
                        ],
                        default="contact_form",
                        max_length=32,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("subscribed_at", models.DateTimeField(auto_now_add=True)),
                ("unsubscribed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Abonné newsletter",
                "verbose_name_plural": "Abonnés newsletter",
                "ordering": ["-subscribed_at"],
            },
        ),
    ]
