"""
Règles de gestion propres au poste de caisse.

Ces règles sont volontairement hors des vues et des services : elles sont
lues par la caisse (affichage), par les API (autorisation) et par le
Z-Report (contrôle), et doivent rester identiques aux trois endroits.
"""

from decimal import Decimal

from django.conf import settings


def _config(cle, defaut):
    return getattr(settings, 'SOCIETE', {}).get(cle, defaut)


def plafond_remise(utilisateur, montant_brut):
    """
    Montant de remise manuelle qu'un utilisateur peut accorder d'office.

    Un administrateur n'est pas plafonné. Un vendeur est limité à un
    pourcentage du brut de la ligne : le geste commercial au comptoir reste
    possible, l'abus ne l'est pas. Le contrôle réel est refait côté service.
    """
    from apps.accounts.models import User

    role = getattr(utilisateur, 'role', None)
    if role in (User.Role.ADMIN, User.Role.GESTIONNAIRE) or getattr(utilisateur, 'is_superuser', False):
        return None  # aucun plafond

    pct = Decimal(str(_config('remise_max_vendeur_pct', 0) or 0))
    if pct <= 0:
        return Decimal('0.00')
    return (Decimal(montant_brut) * pct / Decimal('100')).quantize(Decimal('0.01'))


def session_caisse_requise():
    """Vrai si le caissier doit ouvrir sa caisse avant d'encaisser."""
    return bool(_config('caisse_session_requise', True))


def jours_validite_reservation():
    return int(_config('reservation_validite_jours', 7) or 7)


def devise():
    return _config('devise', 'Ar')
