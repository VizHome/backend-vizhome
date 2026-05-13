"""Account models : User custom + Preferences + Stats + Sessions."""
from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model : email comme login, pas de username."""

    class Plan(models.TextChoices):
        FREE = 'free', 'Gratuit'
        PRO = 'pro', 'Pro'
        ENTERPRISE = 'enterprise', 'Entreprise'

    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    avatar_url = models.URLField(max_length=500, blank=True)
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.FREE)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # email + password déjà requis

    class Meta:
        db_table = 'accounts_user'
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'
        ordering = ['-date_joined']

    def __str__(self) -> str:
        return self.email

    @property
    def name(self) -> str:
        """Nom complet, ou la partie avant @ si vide."""
        full = f'{self.first_name} {self.last_name}'.strip()
        return full or self.email.split('@')[0]


class UserPreferences(models.Model):
    """Préférences utilisateur (mappe les types du frontend useUser.ts)."""

    class Theme(models.TextChoices):
        LIGHT = 'light', 'Clair'
        DARK = 'dark', 'Sombre'
        SYSTEM = 'system', 'Système'

    class Language(models.TextChoices):
        FR = 'fr', 'Français'
        EN = 'en', 'English'
        ES = 'es', 'Español'
        DE = 'de', 'Deutsch'

    class RenderQuality(models.TextChoices):
        DRAFT = 'draft', 'Brouillon'
        STANDARD = 'standard', 'Standard'
        HIGH = 'high', 'Haute'

    class RenderFormat(models.TextChoices):
        PNG = 'png', 'PNG'
        JPG = 'jpg', 'JPG'
        WEBP = 'webp', 'WebP'

    class RenderResolution(models.TextChoices):
        R1024 = '1024', '1024px'
        R2048 = '2048', '2048px'
        R4096 = '4096', '4096px'

    class FontSize(models.TextChoices):
        SMALL = 'small', 'Petit'
        MEDIUM = 'medium', 'Moyen'
        LARGE = 'large', 'Grand'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preferences')

    # Apparence
    theme = models.CharField(max_length=10, choices=Theme.choices, default=Theme.SYSTEM)
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.FR)

    # Notifications
    notif_email_render = models.BooleanField(default=True)
    notif_email_newsletter = models.BooleanField(default=False)
    notif_push_render = models.BooleanField(default=True)
    notif_push_mentions = models.BooleanField(default=False)

    # Qualité de rendu
    render_quality = models.CharField(
        max_length=10, choices=RenderQuality.choices, default=RenderQuality.STANDARD
    )
    render_format = models.CharField(
        max_length=5, choices=RenderFormat.choices, default=RenderFormat.PNG
    )
    render_resolution = models.CharField(
        max_length=5, choices=RenderResolution.choices, default=RenderResolution.R2048
    )

    # Confidentialité
    analytics_enabled = models.BooleanField(default=True)
    marketing_enabled = models.BooleanField(default=False)

    # Sécurité
    two_factor_enabled = models.BooleanField(default=False)

    # Accessibilité
    reduced_motion = models.BooleanField(default=False)
    high_contrast = models.BooleanField(default=False)
    font_size = models.CharField(max_length=10, choices=FontSize.choices, default=FontSize.MEDIUM)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'accounts_preferences'

    def __str__(self) -> str:
        return f'Préférences de {self.user.email}'


# Quotas par défaut selon le plan (octets pour le storage)
PLAN_QUOTAS: dict[str, dict[str, int]] = {
    User.Plan.FREE: {'renders_limit': 5, 'storage_limit_bytes': 1 * 1024**3},
    User.Plan.PRO: {'renders_limit': 50, 'storage_limit_bytes': 5 * 1024**3},
    User.Plan.ENTERPRISE: {'renders_limit': 9999, 'storage_limit_bytes': 1024 * 1024**3},
}


class UserStats(models.Model):
    """Compteurs et quotas — mis à jour par les apps `renders` et `projects`."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='stats')
    renders_this_month = models.PositiveIntegerField(default=0)
    renders_limit = models.PositiveIntegerField(default=5)
    total_projects = models.PositiveIntegerField(default=0)
    storage_used_bytes = models.BigIntegerField(default=0)
    storage_limit_bytes = models.BigIntegerField(default=1 * 1024**3)  # 1 GB
    period_started_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'accounts_stats'

    def __str__(self) -> str:
        return f'Stats de {self.user.email}'


class UserSession(models.Model):
    """Trace d'un refresh token JWT pour permettre révocation côté user.

    Lié au JTI (JWT ID) du refresh token. Permet d'afficher les devices
    connectés dans /me/sessions et de révoquer à distance.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    refresh_jti = models.CharField(max_length=255, unique=True, db_index=True)
    device_name = models.CharField(max_length=200, blank=True)
    user_agent = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_active = models.DateTimeField(auto_now=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'accounts_session'
        ordering = ['-last_active']

    def __str__(self) -> str:
        return f'{self.user.email} — {self.device_name or "Inconnu"}'

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None
