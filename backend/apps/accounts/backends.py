"""
Backends d'authentification de la cave.

EmailOrUsernameBackend : permet de se connecter indifféremment avec
l'identifiant de connexion ou l'adresse e-mail (unique sur le modèle User).

Sécurité renforcée : verrouillage temporaire du compte (l'identifiant ou
l'e-mail) après LOGIN_MAX_ATTEMPTS échecs consécutifs, pour LOGIN_LOCKOUT_MINUTES
minutes, même si le mot de passe est ensuite correct. Les compteurs sont
stockés en cache (mémoire/Redis) et purgés à chaque connexion réussie.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from apps.accounts.services import clear_attempts, is_locked, record_failed_attempt


class EmailOrUsernameBackend(ModelBackend):
    """Authentifie par identifiant OU e-mail.

    Comportement conservé pour l'identifiant (correspondance exacte),
    puis repli sur l'e-mail (insensible à la casse). Aucune fuite sur
    l'existence d'un compte : hachage « leurre » si l'utilisateur manque.
    """

    def has_perm(self, user_obj, perm, obj=None):
        if (
            getattr(user_obj, 'is_active', False)
            and getattr(user_obj, 'is_staff', False)
            and getattr(user_obj, 'has_management_access', False)
        ):
            return True
        return super().has_perm(user_obj, perm, obj)

    def has_module_perms(self, user_obj, app_label):
        if (
            getattr(user_obj, 'is_active', False)
            and getattr(user_obj, 'is_staff', False)
            and getattr(user_obj, 'has_management_access', False)
        ):
            return True
        return super().has_module_perms(user_obj, app_label)

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if not isinstance(username, str) or not username.strip():
            return None
        value = username.strip()

        if is_locked(value):
            record_failed_attempt(value)
            return None

        user = self._recuperer_utilisateur(User, value)
        if user is None:
            User().set_password(password or '')  # temps de réponse homogène
            record_failed_attempt(value)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            clear_attempts(value)
            return user
        record_failed_attempt(value)
        return None

    def _recuperer_utilisateur(self, User, value):
        try:
            return User._default_manager.get_by_natural_key(value)
        except User.DoesNotExist:
            pass
        try:
            return User._default_manager.get(email__iexact=value)
        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            return None