# backend/apps/accounts/apps.py
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    verbose_name = 'Comptes et vérification'

    def ready(self):
        from apps.accounts import signals  # noqa: F401
