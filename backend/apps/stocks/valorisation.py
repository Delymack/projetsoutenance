"""Valorisation du stock.

La valeur d'une bouteille n'est pas la même selon la cuvée : une bouteille
produite au domaine a un coût de revient (raisins, main-d'œuvre,
embouteillage), une bouteille achetée à une coopérative n'en a pas et n'a qu'un
prix d'achat. La valorisation doit donc retenir l'un ou l'autre, selon la
cuvée — sinon un stock acheté vaut zéro, et le tableau de bord annonce un
inventaire faux.

``Produit.cout_effectif`` porte cette règle au niveau objet ; ce module la porte
au niveau SQL, pour que les agrégats (``Sum``, ``Count``) restent calculables par
la base plutôt qu'en Python. Les deux lectures doivent rester identiques.
"""
from decimal import Decimal

from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce

from apps.produits.couts import cout_effectif_expression


def cout_unitaire_expression(decimal_places=2):
    """Coût unitaire d'une ligne de stock, c'est-à-dire celui de son produit."""
    return cout_effectif_expression(prefix='produit__', decimal_places=decimal_places)


def valeur_ligne_expression(decimal_places=2):
    """Expression SQL de la valeur d'une ligne de stock (quantité × coût)."""
    return F('quantite') * cout_unitaire_expression(decimal_places)


def valeur_stock_totale():
    """Valeur totale du stock, au coût. Réutilisée par le stock, le tableau de
    bord et les rapports pour n'afficher qu'un seul chiffre."""
    from apps.stocks.models import Stock
    return Stock.objects.aggregate(
        valeur=Coalesce(
            Sum(valeur_ligne_expression()),
            Value(Decimal('0')),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )
    )['valeur']


def valeur_stock(stock):
    """Valeur au coût d'une ligne de stock, en Python."""
    return Decimal(stock.quantite) * stock.produit.cout_effectif
