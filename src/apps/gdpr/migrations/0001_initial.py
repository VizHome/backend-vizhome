"""Initial migration : ExportRequest + DeletionRequest."""

from __future__ import annotations

import apps.gdpr.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ExportRequest",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "En attente"),
                            ("processing", "En cours"),
                            ("ready", "Prêt au téléchargement"),
                            ("expired", "Lien expiré"),
                            ("failed", "Échec"),
                        ],
                        db_index=True,
                        default="queued",
                        max_length=20,
                    ),
                ),
                ("file_key", models.CharField(blank=True, max_length=500)),
                ("file_size_bytes", models.BigIntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="gdpr_export_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Demande export RGPD",
                "verbose_name_plural": "Demandes export RGPD",
                "db_table": "gdpr_export_request",
                "ordering": ["-requested_at"],
            },
        ),
        migrations.AddIndex(
            model_name="exportrequest",
            index=models.Index(
                fields=["user", "-requested_at"],
                name="gdpr_export_user_id_b6e2fb_idx",
            ),
        ),
        migrations.CreateModel(
            name="DeletionRequest",
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
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                (
                    "scheduled_for",
                    models.DateTimeField(
                        default=apps.gdpr.models._default_scheduled_for
                    ),
                ),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        related_name="gdpr_deletion_request",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Demande suppression RGPD",
                "verbose_name_plural": "Demandes suppression RGPD",
                "db_table": "gdpr_deletion_request",
                "ordering": ["-requested_at"],
            },
        ),
    ]
