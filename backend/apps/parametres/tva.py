"""Décomposition HT / TVA / TTC des montants affichés sur les documents.

Le taux et le sens (``prix TTC`` ou ``prix HT``) viennent des paramètres, ce
qui évite d'écrire la taxe en dur dans chaque gabarit. À taux nul — le cas
par défaut d'un commerce malgache non assujetti — tout reste neutre : le
gabarit n'affiche alors aucune ligne de TVA.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.utils.translation import gettext_lazy as _

CENT = Decimal('0.01')


def _arrondi(valeur):
    return Decimal(valeur).quantize(CENT, rounding=ROUND_HALF_UP)


def base_vers_ttc(montant, taux, deja_ttc):
    """Convertit un prix catalogue en montant facturé TTC."""
    montant = _arrondi(montant or 0)
    taux = _arrondi(taux or 0)
    if deja_ttc or taux <= 0:
        return montant
    return _arrondi(montant * (Decimal('1') + taux / Decimal('100')))


def ttc_vers_base(montant, taux, deja_ttc):
    """Retrouve le prix catalogue HT à partir d’un montant TTC enregistré."""
    montant = _arrondi(montant or 0)
    taux = _arrondi(taux or 0)
    if deja_ttc or taux <= 0:
        return montant
    return _arrondi(montant / (Decimal('1') + taux / Decimal('100')))


def decomposition(montant_ttc, taux, incluse):
    """Retourne ``{ht, tva, ttc, taux, libelle}`` pour un montant donné.

    * ``incluse`` : le prix contient déjà la taxe (on l'extrait) ;
    * sinon : la taxe s'ajoute au prix (elle vaut le montant × le taux).
    """
    montant_ttc = _arrondi(montant_ttc or 0)
    taux = _arrondi(taux or 0)
    if taux <= 0:
        return {
            'ht': montant_ttc, 'tva': Decimal('0.00'), 'ttc': montant_ttc,
            'taux': Decimal('0.00'), 'libelle': '', 'active': False,
        }
    if incluse:
        ht = _arrondi(montant_ttc / (Decimal('1') + taux / Decimal('100')))
        tva = _arrondi(montant_ttc - ht)
    else:
        ht = montant_ttc
        tva = _arrondi(montant_ttc * taux / Decimal('100'))
        montant_ttc = _arrondi(ht + tva)
    return {
        'ht': ht, 'tva': tva, 'ttc': montant_ttc, 'taux': taux,
        'libelle': _('TVA {} %').format(taux).replace('\xa0', ' '),
        'active': True,
    }
