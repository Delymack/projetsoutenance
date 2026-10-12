"""Endpoint public de la page d'accueil : textes + les deux couleurs.

``GET /api/accueil/`` est la source de vérité de la page principale du
frontend : les textes (par langue) et la palette (2 couleurs maximum) sont
modifiables depuis la console ``/admin/parametres/`` sans redéployer le site.

Toute valeur absente ou invalide retombe sur les valeurs par défaut de
``apps.parametres.defaults`` : l'API répond toujours un JSON exploitable.
"""

import json
import re

from django.http import JsonResponse
from django.views import View

from apps.parametres.services import get_param

#: Langues acceptées (miroir du frontend).
LANGUES = ('fr', 'mg', 'en')

#: Champs textuels attendus par langue.
CHAMPS = (
    'eyebrow', 'titre', 'motsCles', 'ctaCatalogue', 'ctaPromos',
    'selectionEyebrow', 'selectionTitre', 'voirCatalogue',
)

#: Palette par défaut : noir profond + or (2 couleurs maximum).
COULEUR_DEFAUT_FOND = '#0C0A09'
COULEUR_DEFAUT_ACCENT = '#C9A227'

_COULEUR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
_MOTS_MAX = 6


def _couleur(valeur, defaut):
    """Valide une couleur hexadécimale ; renvoie ``defaut`` sinon."""
    if isinstance(valeur, str) and _COULEUR_RE.match(valeur.strip()):
        return valeur.strip()
    return defaut


def _textes():
    """Textes par langue, champ par champ (les champs invalides sont ignorés)."""
    brut = get_param('accueil_textes')
    if isinstance(brut, str):
        try:
            brut = json.loads(brut)
        except (TypeError, ValueError):
            brut = {}
    if not isinstance(brut, dict):
        brut = {}

    sortie = {}
    for langue in LANGUES:
        bloc = brut.get(langue)
        if not isinstance(bloc, dict):
            continue
        champs = {}
        for champ in CHAMPS:
            valeur = bloc.get(champ)
            if champ == 'motsCles':
                if isinstance(valeur, list):
                    mots = [str(m).strip() for m in valeur if str(m).strip()]
                    if mots:
                        champs[champ] = mots[:_MOTS_MAX]
            elif isinstance(valeur, str) and valeur.strip():
                champs[champ] = valeur.strip()
        if champs:
            sortie[langue] = champs
    return sortie


class AccueilView(View):
    """``GET /api/accueil/`` — public, sans authentification."""

    http_method_names = ['get']

    def get(self, request):
        return JsonResponse({
            'textes': _textes(),
            'couleurFond': _couleur(get_param('accueil_couleur_fond'), COULEUR_DEFAUT_FOND),
            'couleurAccent': _couleur(get_param('accueil_couleur_accent'), COULEUR_DEFAUT_ACCENT),
        })
