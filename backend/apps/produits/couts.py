"""Coût effectif d'un produit, en SQL.

``Produit.cout_effectif`` fait cette règle au niveau objet (marge unitaire,
valorisation d'une ligne de stock). Les agrégats, eux, sont évalués par la base :
ils ont besoin de la même règle exprimée en SQL, sans quoi ``Sum`` et ``Count``
donneraient un chiffre différent de celui qu'affiche la fiche produit.

La règle : le coût de revient s'il est renseigné, sinon le prix d'achat (cuvée
achetée), sinon zéro.

``prefix`` permet d'atteindre le même produit à travers une jointure — c'est ce
dont a besoin ``apps.stocks.valorisation``, qui lit ``produit__cout_revenir``.
"""
from decimal import Decimal

from django.db.models import Case, DecimalField, F, Value, When
from django.db.models.functions import Coalesce


def cout_effectif_expression(prefix='', decimal_places=2):
    """Coût unitaire retenu pour un produit : coût de revient, sinon prix d'achat.

    ``prefix='produit__'`` vise un produit joint, ``prefix=''`` le produit courant.
    """
    return Coalesce(
        Case(
            When(**{f'{prefix}cout_revenir__gt': 0}, then=F(f'{prefix}cout_revenir')),
            default=Coalesce(F(f'{prefix}prix_achat'), Value(Decimal('0'))),
        ),
        Value(Decimal('0')),
        output_field=DecimalField(max_digits=14, decimal_places=decimal_places),
    )


def marge_unitaire_expression(prefix='', decimal_places=2):
    """Marge brute unitaire : prix de vente moins coût effectif."""
    return F(f'{prefix}prix_vente') - cout_effectif_expression(prefix, decimal_places)
