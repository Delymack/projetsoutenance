"""Données de compte affichées dans la console « Utilisateurs & paramètres ».

La page reste une vue rapide : les formulaires officiels de l'admin Django
gèrent les mots de passe, les permissions fines et la 2FA.
"""

from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()

def lister_utilisateurs(request):
    """Comptes utiles à la liste de la console, triés par importance."""
    comptes = list(User.objects.order_by('-is_superuser', 'role', 'username'))

    for u in comptes:
        u.nom_complet = ' '.join(x for x in (u.first_name, u.last_name) if x) or '—'
        u.initiales = ((u.first_name or u.username)[:1] + (u.last_name or '')[:1]).upper()
        u.est_vide = not u.last_login
        # Django ne propose la page de mot de passe qu'en modification : on
        # construit l'URL pour ne pas dépendre de ce détail d'implémentation.
        u.url_modifier = reverse('admin:accounts_user_change', args=[u.pk])
        u.url_mot_de_passe = reverse('admin:auth_user_password_change', args=[u.pk])
        u.url_supprimer = reverse('admin:accounts_user_delete', args=[u.pk])
        u.peut_etre_supprime = u.pk != getattr(request.user, 'pk', None)
    comptes.sort(key=lambda u: (not u.is_superuser, not u.is_active, u.username.lower()))
    return comptes
