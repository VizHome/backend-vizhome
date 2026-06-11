"""Ajoute les champs `pseudo` (unique) et `is_banned_from_forum` sur User.

Pour les users existants : génération automatique du pseudo depuis l'email
local-part, avec suffixe `_2`, `_3`, ... en cas de collision.
"""

from __future__ import annotations

import re

import django.core.validators
from django.db import migrations, models


def generate_pseudos_for_existing(apps, schema_editor):  # noqa: ANN001
    User = apps.get_model("accounts", "User")

    used: set[str] = set()
    for user in User.objects.all().order_by("date_joined"):
        # Base = local-part email, nettoyé pour matcher le validator
        # (lettre + alphanum/_/-, 3-30 chars)
        local = user.email.split("@")[0]
        base = re.sub(r"[^a-zA-Z0-9_-]", "", local)
        if not base or not base[0].isalpha():
            base = "user" + (base or str(user.pk))
        base = base[:30]
        if len(base) < 3:
            base = (base + "user")[:30]

        candidate = base
        i = 2
        while candidate in used or User.objects.filter(pseudo=candidate).exists():
            suffix = f"_{i}"
            candidate = base[: 30 - len(suffix)] + suffix
            i += 1
        used.add(candidate)
        user.pseudo = candidate
        user.save(update_fields=["pseudo"])


def noop_reverse(apps, schema_editor):  # noqa: ANN001
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        # 1. Ajoute le champ nullable+non-unique pour pouvoir le populer.
        #    (Pas de db_index ici sinon Django essaie de re-créer le `_like`
        #    index en step 3 lors de l'AlterField → unique=True.)
        migrations.AddField(
            model_name="user",
            name="pseudo",
            field=models.CharField(
                max_length=30,
                null=True,
                blank=True,
            ),
        ),
        # 2. Génère un pseudo pour chaque user existant
        migrations.RunPython(generate_pseudos_for_existing, noop_reverse),
        # 3. Verrouille : NOT NULL + UNIQUE + validator
        migrations.AlterField(
            model_name="user",
            name="pseudo",
            field=models.CharField(
                max_length=30,
                unique=True,
                db_index=True,
                help_text="Pseudo public unique, modifiable seulement par staff.",
                validators=[
                    django.core.validators.RegexValidator(
                        regex=r"^[a-zA-Z][a-zA-Z0-9_-]{2,29}$",
                        message=(
                            "Le pseudo doit faire 3 à 30 caractères, "
                            "commencer par une lettre, et ne contenir que "
                            "des lettres, chiffres, tirets ou underscores."
                        ),
                    )
                ],
            ),
        ),
        # 4. Nouveau champ pour la modération forum (ban du compte forum-only)
        migrations.AddField(
            model_name="user",
            name="is_banned_from_forum",
            field=models.BooleanField(default=False),
        ),
    ]
