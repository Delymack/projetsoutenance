from django.conf import settings

from apps.accounts.models import User
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


def _email_of(sociallogin):
    """Email fiable du login social (extra_data Google, sinon compte/email)."""
    data = sociallogin.account.extra_data
    return (
        data.get('email')
        or sociallogin.account.email
        or sociallogin.user.email
        or ''
    ).strip().lower()


class GoogleSocialAdapter(DefaultSocialAccountAdapter):
    """
    Adaptateur « Continuer avec Google ».

    Règles d'accès :
      * Un compte Google n'est créé que si son adresse (ou son domaine) est
        autorisée via GOOGLE_ALLOWED_EMAILS / GOOGLE_ALLOWED_DOMAINS.
      * Sans aucune restriction configurée, toute adresse est acceptée
        (utile en développement : penser à restreindre en production).
      * Si l'adresse correspond déjà à un utilisateur, la connexion Google
        est simplement liée à ce compte (aucune création).

    Les comptes créés via Google sont des vendeurs (rôle VENDEUR). Accès au
    back-office (is_staff) uniquement si GOOGLE_STAFF=True est configuré
    (désactivé par défaut — l'administrateur promeut les comptes manuellement).
    """

    def _allowed_lists(self):
        return {
            'domains': [d.lower().strip() for d in settings.GOOGLE_ALLOWED_DOMAINS if d],
            'emails': [e.lower().strip() for e in settings.GOOGLE_ALLOWED_EMAILS if e],
        }

    def has_restrictions(self):
        lists = self._allowed_lists()
        return bool(lists['domains'] or lists['emails'])

    def is_allowed_email(self, email):
        email = (email or '').strip().lower()
        if not email:
            return False
        if not self.has_restrictions():
            return True
        lists = self._allowed_lists()
        domain = email.split('@')[-1]
        return domain in lists['domains'] or email in lists['emails']

    def is_open_for_signup(self, request, sociallogin):
        email = _email_of(sociallogin)
        if self.is_allowed_email(email):
            return True
        # Adresse déjà connue → simple liaison, pas une véritable inscription.
        return bool(email) and User.objects.filter(email__iexact=email).exists()

    def pre_social_login(self, request, sociallogin):
        """Liaison par adresse email à un compte existant."""
        if sociallogin.user and sociallogin.user.pk:
            return
        email = _email_of(sociallogin)
        if not email:
            return
        existing = User.objects.filter(email__iexact=email).first()
        if existing is not None:
            sociallogin.user = existing
        return super().pre_social_login(request, sociallogin)

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        data = sociallogin.account.extra_data
        user.is_staff = getattr(settings, 'GOOGLE_STAFF', False)
        user.role = User.Role.VENDEUR
        if data.get('sub'):
            user.google_uid = data['sub']
        if data.get('given_name'):
            user.first_name = data['given_name']
        if data.get('family_name'):
            user.last_name = data['family_name']
        if data.get('picture'):
            user.avatar_url = data['picture']
        user.save(update_fields=[
            'is_staff', 'role', 'google_uid',
            'first_name', 'last_name', 'avatar_url',
        ])
        return user

    def post_social_login(self, request, sociallogin):
        """Rafraîchit l'avatar / l'identité sur chaque connexion Google."""
        user = sociallogin.user
        data = sociallogin.account.extra_data
        if user and user.pk and data:
            changes = {}
            if data.get('picture'):
                changes['avatar_url'] = data['picture']
            if data.get('sub'):
                changes['google_uid'] = data['sub']
            if data.get('given_name'):
                changes['first_name'] = data['given_name']
            if data.get('family_name'):
                changes['last_name'] = data['family_name']
            if changes:
                User.objects.filter(pk=user.pk).update(**changes)
        return super().post_social_login(request, sociallogin)