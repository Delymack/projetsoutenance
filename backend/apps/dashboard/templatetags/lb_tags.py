"""Filtres de présentation partagés par tout l'admin (design system WineAdmin).

Remplace `django.contrib.humanize` (non installé) et centralise le formatage
des montants et des pourcentages sur la devise de la société.
"""
from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

register = template.Library()


def _devise():
    return settings.SOCIETE.get('devise', 'Ar')


@register.filter
def intcomma(value):
    """Sépare les milliers par une espace fine insécable : 1 234 567."""
    try:
        nombre = int(value)
    except (TypeError, ValueError):
        return value
    signe = '-' if nombre < 0 else ''
    return mark_safe(f"{signe}{abs(nombre):,}".replace(',', '\u202f'))


@register.filter
def montant(value, decimales=0):
    """Montant formaté à la devise de la société : ``12 500 Ar``."""
    try:
        quantite = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value
    arrondi = Decimal(1).scaleb(-int(decimales))
    quantite = quantite.quantize(arrondi, rounding='ROUND_HALF_UP')
    entier = int(quantite)
    signe = '-' if entier < 0 else ''
    nombre = f"{signe}{abs(entier):,}".replace(',', '\u202f')
    if decimales:
        _, _, dec = f"{abs(quantite):f}".partition('.')
        return mark_safe(f"{nombre},{dec} {_devise()}")
    return mark_safe(f"{nombre} {_devise()}")


@register.filter
def pourcent(value, decimales=1):
    """Formate un ratio (0..1) en pourcentage lisible."""
    try:
        ratio = float(value) * 100
    except (TypeError, ValueError):
        return value
    return f"{ratio:.{int(decimales)}f} %".replace('.', ',')


@register.filter
def initiales(nom, prenom=''):
    """Initiales d'un nom/prénom pour les avatars."""
    return ''.join(filter(None, [(nom or '')[:1], (prenom or '')[:1]])).upper()


@register.filter
def stars(pourcentage):
    """Note sur 5 étoiles à partir d'un pourcentage (0..100)."""
    try:
        valeur = max(0.0, min(1.0, float(pourcentage) / 100))
    except (TypeError, ValueError):
        return ''
    pleines = int(valeur * 5)
    return '★' * pleines + '☆' * (5 - pleines)


@register.filter
def sans_plus(value):
    """Retire le « + » d'un numéro pour un lien `tel:` ou wa.me."""
    return str(value or '').lstrip('+')


@register.filter
def call(fonction, argument):
    """Appelle une fonction du contexte en lui passant un argument.

    Django ne permet pas d'écrire ``{{ f x }}`` dans un template ; ce filtre
    comble ce manque pour les petits calculs de présentation (icône d'un mode
    de paiement, par exemple), sans avoir à dupliquer la logique côté template.
    """
    if not callable(fonction):
        return fonction
    try:
        return fonction(argument)
    except Exception:
        # Une icône manquante ne doit pas faire tomber la page de caisse.
        return ''


@register.simple_tag
def devise():
    """Devise courante, utilisable directement dans un template."""
    return _devise()
