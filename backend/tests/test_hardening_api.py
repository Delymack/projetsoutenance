from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from decimal import Decimal

from apps.accounts.models import User
from apps.produits.models import Produit
from apps.stocks.models import Stock
from apps.clients.models import Client


class HardeningAPI(APITestCase):
    """Protections d'intégrité : pas de suppression destructrice via l'API."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', email='admin@test.com',
            password='password123', role=User.Role.ADMIN,
        )
        self.client_obj = Client.objects.create(nom="Dupont", prenom="Jean", telephone="0102030405")
        self.produit = Produit.objects.create(
            nom="Vin Rouge 2015", type_vin="Rouge", marque="Château A",
            cout_revenir=Decimal('10.00'), prix_vente=Decimal('20.00'), statut=True
        )
        Stock.objects.update_or_create(produit=self.produit, defaults={'quantite': 10, 'seuil_alerte': 2})
        response = self.client.post(
            reverse('token_obtain_pair'),
            {'username': 'admin', 'password': 'password123'}
        )
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])

    def _creer_vente(self):
        data = {
            "client": self.client_obj.id,
            "mode_paiement": "ESPECES",
            "lignes": [{"produit_id": self.produit.id, "quantite": 3}],
        }
        response = self.client.post(reverse('ventes-list'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return response.data['data']['id']

    def test_vente_destroy_interdit_sans_restauration(self):
        vente_id = self._creer_vente()
        stock = Stock.objects.get(produit=self.produit)
        self.assertEqual(stock.quantite, 7)

        response = self.client.delete(reverse('ventes-detail', args=[vente_id]))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        stock.refresh_from_db()
        self.assertEqual(stock.quantite, 7)

    def test_vente_update_interdit(self):
        vente_id = self._creer_vente()
        response = self.client.patch(
            reverse('ventes-detail', args=[vente_id]), {'total': '1.00'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_reglement_delete_restaure_solde(self):
        self.client_obj.solde_du = Decimal('100.00')
        self.client_obj.save()

        reglement = self.client.post(reverse('reglements-client-list'), {
            "client": self.client_obj.id, "montant": "40.00", "mode": "ESPECES",
        }, format='json')
        reglement_id = reglement.data['data']['id']
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.solde_du, Decimal('60.00'))

        response = self.client.delete(reverse('reglements-client-detail', args=[reglement_id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.solde_du, Decimal('100.00'))
