"""Filtres de la console « Paramètres & Utilisateurs ».

Trois besoins seulement : lire une clé dans la matrice des droits (un
dictionnaire Python n'a pas de « [] » dans un gabarit), tester l'appartenance à
une liste stockée sous forme de texte, et décomposer un montant en HT/TVA/TTC
selon les paramètres.
"""

from django import template

register = template.Library()


@register.filter
def get_item(source, cle):
    """``{{ dictionnaire|get_item:cle }}`` — la valeur, ou ``''``."""
    try:
        return source.get(cle, '')
    except AttributeError:
        return ''


@register.filter
def to_list(valeur):
    """Normalise une valeur « liste » en véritable liste, pour un test d'appartenance."""
    if valeur is None:
        return []
    if isinstance(valeur, (list, tuple)):
        return list(valeur)
    return [x.strip() for x in str(valeur).split(',') if x.strip()]


@register.filter
def tva(montant):
    """``{{ 12000|tva }}`` — la décomposition HT/TVA/TTC du montant.

    Le taux et le sens (prix TTC ou prix HT) viennent des paramètres : aucune
    taxe n'est écrite en dur dans un gabarit. À taux nul, ``active`` vaut faux
    et le gabarit n'affiche rien.
    """
    from apps.parametres.services import get_config
    from apps.parametres.tva import decomposition

    cfg = get_config()
    return decomposition(
        montant, cfg.get('ventes_tva') or 0, bool(cfg.get('ventes_tva_incluse')),
    )
