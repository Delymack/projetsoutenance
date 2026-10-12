"""État du stock, dans le modèle et dans la liste de l'admin.

`Stock.etat_stock` est documenté avec trois états (plans/LOGIQUE_ACTION.md) mais
n'en renvoyait que deux : un stock sain valait `None`. La liste de l'admin
appelait alors `.replace()` sur `None`, et l'API exposait `null` au lieu de
`STOCK_NORMAL`.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.produits.models import Produit
from apps.stocks.models import Stock


class EtatStockTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='MotDePasse123',
        )
        self.produit = Produit.objects.create(
            nom='Cuvée 2018', type_vin='Rouge', marque='Domaine',
            cout_revenir=Decimal('5000.00'), prix_vente=Decimal('10000.00'),
            statut=True,
        )
        # Un stock est déjà créé avec le produit (signal) : on le met à jour.
        # Stock sain : quantite > seuil_alerte -> STOCK_NORMAL attendu.
        self.stock, _ = Stock.objects.update_or_create(
            produit=self.produit, defaults={'quantite': 50, 'seuil_alerte': 10},
        )

    def test_un_stock_sain_est_normal(self):
        self.assertEqual(self.stock.etat_stock, 'STOCK_NORMAL')

    def test_la_liste_des_stocks_affiche_un_stock_sain(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin:stocks_stock_changelist'))

        self.assertEqual(response.status_code, 200, response.content)
        self.assertContains(response, 'STOCK NORMAL')