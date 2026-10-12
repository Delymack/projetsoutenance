"""Signaux des produits : cohérence du stock.

À la création (ou mise à jour) d'un produit, on garantit l'existence de sa
ligne de stock (quantité initiale 0) pour éviter les erreurs
« Aucun stock défini » en caisse.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.produits.models import Produit
from apps.stocks.models import Stock


@receiver(post_save, sender=Produit)
def garantir_stock_produit(sender, instance, **kwargs):
    Stock.objects.get_or_create(
        produit=instance,
        defaults={'quantite': 0, 'seuil_alerte': 10},
    )