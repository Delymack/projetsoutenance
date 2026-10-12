"""Modes de paiement proposés à la caisse.

Deux choses, volontairement séparées :

* le **vocabulaire** — les codes possibles — vit dans ``Vente.ModePaiement``
  et ne bouge pas : une vente enregistrée doit rester relisible dans dix ans ;
* l'**activation** — ce que le caissier peut réellement choisir — vit dans le
  paramètre ``ventes_modes_paiement``.

Retirer un mode de la liste ne rend donc pas les ventes historiques invalides :
seule la saisie au comptoir est restreinte.
"""

from apps.ventes.models import Vente

PARAM_MODES = 'ventes_modes_paiement'


def _libelles():
    return dict(Vente.ModePaiement.choices)


def codes_actifs():
    """Codes proposés à la caisse, dans l'ordre choisi par l'administrateur."""
    from apps.parametres.services import get_param

    config = get_param(PARAM_MODES) or []
    if isinstance(config, str):
        config = [c for c in config.split(',') if c]
    connus = _libelles()
    codes = [c for c in config if c in connus]
    # Un paramètre vide ou corrompu ne doit pas rendre la caisse inutilisable :
    # on retombe alors sur l'intégralité des modes connus.
    return codes or [m.value for m in Vente.ModePaiement]


def modes_actifs():
    """[(code, libellé)] pour les gabarits."""
    libelles = _libelles()
    return [(code, libelles[code]) for code in codes_actifs()]


def est_actif(code):
    return code in codes_actifs()
