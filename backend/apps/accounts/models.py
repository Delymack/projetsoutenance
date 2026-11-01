# backend/apps/accounts/models.py
import uuid
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.db.models import Q


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        GESTIONNAIRE = 'GESTIONNAIRE', 'Gestionnaire'
        VENDEUR = 'VENDEUR', 'Vendeur'
        CLIENT = 'CLIENT', 'Client'

    # Nullable : l'inscription peut se faire par SMS seul, sans adresse e-mail.
    # ``unique=True`` + ``null=True`` autorise plusieurs comptes sans e-mail
    # tandis que toute adresse renseignée reste unique.
    email = models.EmailField(unique=True, null=True, blank=True)
    telephone = models.CharField(max_length=30, blank=True, null=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VENDEUR)
    avatar_url = models.URLField(blank=True, max_length=500)
    avatar = models.CharField(max_length=100, blank=True, null=True)
    google_uid = models.CharField(max_length=128, blank=True, default='')
    is_2fa_enabled = models.BooleanField(default=False)
    code_recuperation_expire_le = models.DateTimeField(blank=True, null=True)
    code_recuperation_hash = models.CharField(max_length=128, blank=True, default='')
    totp_secret = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name='Secret TOTP (obfusqué)',
    )
    totp_enabled = models.BooleanField(default=False, verbose_name='Double authentification (2FA)')
    recovery_codes = models.TextField(blank=True, default='', verbose_name='Codes de secours (hachés)')

    class Meta:
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'

    def __str__(self):
        return self.username or self.email

    @property
    def has_management_access(self):
        return self.is_superuser or self.role in (self.Role.ADMIN, self.Role.GESTIONNAIRE)

    def save(self, *args, **kwargs):
        # Les rôles de gestion portent l'accès au back-office : le rôle est la
        # source de vérité, pas le drapeau `is_staff` (qu'un vendeur pourrait
        # recevoir accidentellement sans obtenir de droit de gestion).
        if self.role in (self.Role.ADMIN, self.Role.GESTIONNAIRE):
            self.is_staff = True
        if self.role == self.Role.ADMIN:
            self.is_superuser = True
        super().save(*args, **kwargs)


class LoginEvent(models.Model):
    """Historique des connexions (succès / échec) — traçabilité & alerte 2FA."""

    class Statut(models.TextChoices):
        SUCCESS = 'SUCCESS', 'Succès'
        FAILED = 'FAILED', 'Échec'
        LOCKED = 'LOCKED', 'Verrouillé'

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='connexions',
        verbose_name='Utilisateur',
    )
    statut = models.CharField(
        max_length=10,
        choices=Statut.choices,
        default=Statut.SUCCESS,
        verbose_name='Statut',
    )
    ip = models.GenericIPAddressField(null=True, blank=True, verbose_name='Adresse IP')
    user_agent = models.TextField(blank=True, default='', verbose_name='Navigateur')
    appareil = models.CharField(
        max_length=120,
        blank=True,
        default='',
        verbose_name='Appareil',
    )
    cree_le = models.DateTimeField(default=timezone.now, verbose_name='Date')

    class Meta:
        verbose_name = 'événement de connexion'
        verbose_name_plural = 'événements de connexion'
        ordering = ('-cree_le',)
        db_table = 'accounts_login_event'

    def __str__(self):
        return f'{self.user} · {self.get_statut_display()} · {self.appareil or self.ip}'


class UserNotification(models.Model):
    """État personnel (lu / masqué) d'une alerte d'administration."""

    class Etat(models.TextChoices):
        NON_LUE = 'NON_LUE', 'Non lue'
        LUE = 'LUE', 'Lue'
        MASQUEE = 'MASQUEE', 'Masquée'

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Utilisateur',
    )
    key = models.CharField(max_length=200, verbose_name='Clé')
    etat = models.CharField(
        max_length=10,
        choices=Etat.choices,
        default=Etat.NON_LUE,
        verbose_name='État',
    )
    cree_le = models.DateTimeField(default=timezone.now, verbose_name='Créée le')

    class Meta:
        verbose_name = 'notification utilisateur'
        verbose_name_plural = 'notifications utilisateur'
        ordering = ('-cree_le',)
        db_table = 'accounts_user_notification'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'key'],
                name='uniq_user_notification_user_key',
            ),
        ]

    def __str__(self):
        return f'{self.user} · {self.key} · {self.get_etat_display()}'


class VerificationCode(models.Model):
    CONTACT_EMAIL = 'email'
    CONTACT_SMS = 'sms'
    CONTACT_TYPES = (
        (CONTACT_EMAIL, 'Email'),
        (CONTACT_SMS, 'SMS'),
    )

    PURPOSE_SIGNUP = 'signup'
    PURPOSE_LOGIN = 'login'
    PURPOSES = (
        (PURPOSE_SIGNUP, 'Inscription'),
        (PURPOSE_LOGIN, 'Connexion'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contact = models.CharField(max_length=150, db_index=True)
    contact_type = models.CharField(max_length=5, choices=CONTACT_TYPES, default=CONTACT_EMAIL)
    code_hash = models.CharField(max_length=255)
    purpose = models.CharField(max_length=10, choices=PURPOSES, default=PURPOSE_LOGIN)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    last_sent_at = models.DateTimeField(default=timezone.now)
    user_data = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Code de vérification"
        verbose_name_plural = "Codes de vérification"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['contact', 'purpose', 'is_used']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"{self.contact} - {self.purpose}"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=10)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_blocked(self):
        return self.attempts >= 5

    def can_resend(self):
        return (timezone.now() - self.last_sent_at).total_seconds() >= 60

    def increment_attempts(self):
        self.attempts += 1
        self.save(update_fields=['attempts'])

    def set_used(self):
        self.is_used = True
        self.save(update_fields=['is_used'])

    def set_code(self, code):
        self.code_hash = make_password(code)
        self.last_sent_at = timezone.now()
        self.save(update_fields=['code_hash', 'last_sent_at'])

    def verify_code(self, code):
        if self.is_used or self.is_expired or self.is_blocked:
            return False
        return check_password(code, self.code_hash)
