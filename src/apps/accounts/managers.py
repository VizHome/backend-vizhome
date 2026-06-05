"""Custom user manager — email is the unique identifier (no username)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager

if TYPE_CHECKING:
    from .models import User


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _generate_pseudo_from_email(self, email: str) -> str:
        """Génère un pseudo unique depuis le local-part de l'email.

        Stratégie : sanitize → tronque à 30 chars → ajoute `_2`, `_3`… sur
        collision. Garantit la conformité au validator PSEUDO_VALIDATOR
        (commence par une lettre, alphanum + _ -, 3-30 chars).

        Utilisé quand le pseudo n'est pas fourni (tests, OAuth signup,
        seed scripts, management commands).
        """
        local = email.split("@")[0]
        base = re.sub(r"[^a-zA-Z0-9_-]", "", local)
        if not base or not base[0].isalpha():
            base = "user" + (base or "")
        base = base[:30]
        if len(base) < 3:
            base = (base + "user")[:30]

        candidate = base
        i = 2
        while self.model.objects.filter(pseudo=candidate).exists():
            suffix = f"_{i}"
            candidate = base[: 30 - len(suffix)] + suffix
            i += 1
        return candidate

    def _create_user(
        self, email: str, password: str | None, **extra_fields: Any
    ) -> User:
        if not email:
            raise ValueError("L'email est obligatoire.")
        email = self.normalize_email(email)
        # Auto-gen pseudo si pas fourni (compat tests/OAuth/seed/CLI)
        if not extra_fields.get("pseudo"):
            extra_fields["pseudo"] = self._generate_pseudo_from_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> User:
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> User:
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Un superuser doit avoir is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Un superuser doit avoir is_superuser=True.")

        return self._create_user(email, password, **extra_fields)
