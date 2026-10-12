from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from decimal import Decimal

from apps.accounts.models import User
from apps.produits.models import Produit
from apps.stocks.models import Stock
from apps.clients.models import Client, ReglementClient
from apps.ventes.models import Vente


class FideliteEtReglementsTests(APITestCase):
    def setUp(self):
        self.gestionnaire = User.objects.create_user(
            username='gestion', email='gestion@test.com', password='password123',
            role=User.Role.VENDEUR,
        )
        self.produit = Produit.objects.create(
            nom="Cru Premium 2016", type_vin="Rouge", marque="Château C",
            cout_revenir=Decimal('5000.00'), prix_vente=Decimal('12000.00'), statut=True,
        )
        Stock.objects.update_or_create(produit=self.produit, defaults={'quantite': 20, 'seuil_alerte': 2})

        self.client_obj = Client.objects.create(
            nom="Rakoto", prenom="Hery", telephone="0321112233",
            max_credit=Decimal('50000.00'),
        )
        self.ventes_url = reverse('ventes-list')

        response = self.client.post(
            reverse('token_obtain_pair'),
            {'username': 'gestion', 'password': 'password123'},
        )
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])

    def vendre(self, quantite=2, mode='ESPECES', client=None):
        return self.client.post(self.ventes_url, {
            "client": (client or self.client_obj).id,
            "mode_paiement": mode,
            "lignes": [{"produit_id": self.produit.id, "quantite": quantite}],
        }, format='json')

    def test_vente_a_credit_augmente_solde_et_points(self):
        response = self.vendre(mode='CREDIT')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.client_obj.refresh_from_db()
        # 2 x 12000 = 24000 porté au solde dû
        self.assertEqual(self.client_obj.solde_du, Decimal('24000.00'))
        # 24000 // 1000 (points_regle) = 24 points
        self.assertEqual(self.client_obj.points_fidelite, 24)

    def test_credit_interdit_sans_plafond(self):
        sans_credit = Client.objects.create(nom="Peu", prenom="Nina", telephone="0330000000")
        response = self.vendre(mode='CREDIT', client=sans_credit)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('client', response.data['errors'])

    def test_credit_refuse_depassement_plafond(self):
        response = self.vendre(quantite=5, mode='CREDIT')
        # 5 x 12000 = 60000 > 50000
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('client', response.data['errors'])
        # La transaction doit être intégralement annulée (stock intact)
        self.produit.refresh_from_db()
        self.assertEqual(Stock.objects.get(produit=self.produit).quantite, 20)

    def test_annulation_restaure_credit_et_points(self):
        response = self.vendre(mode='CREDIT')
        vente_id = response.data['data']['id']
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.solde_du, Decimal('24000.00'))

        admin = User.objects.create_superuser(username='admin2', email='a@test.com', password='password123')
        auth = self.client.post(reverse('token_obtain_pair'), {'username': 'admin2', 'password': 'password123'})
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + auth.data['access'])

        annuler = self.client.post(reverse('ventes-annuler', kwargs={'pk': vente_id}))
        self.assertEqual(annuler.status_code, status.HTTP_200_OK)
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.solde_du, Decimal('0.00'))
        self.assertEqual(self.client_obj.points_fidelite, 0)

    def test_vente_especes_attribue_points_sans_solde(self):
        response = self.vendre(mode='ESPECES', quantite=1)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.solde_du, Decimal('0.00'))
        self.assertEqual(self.client_obj.points_fidelite, 12)

    def test_reglement_reduit_solde_due(self):
        self.vendre(mode='CREDIT')
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.solde_du, Decimal('24000.00'))

        url = reverse('reglements-client-list')
        response = self.client.post(url, {
            "client": self.client_obj.id,
            "montant": "14000.00",
            "mode": "ESPECES",
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.solde_du, Decimal('10000.00'))
        self.assertEqual(ReglementClient.objects.count(), 1)

    def test_reglement_superieur_solde_refuse(self):
        url = reverse('reglements-client-list')
        response = self.client.post(url, {
            "client": self.client_obj.id,
            "montant": "10.00",
            "mode": "ESPECES",
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('montant', response.data['errors'])

    def test_niveau_recalcule_automatiquement(self):
        c = Client.objects.create(nom="Or", prenom="Mialy", telephone="0341112233")
        c.points_fidelite = 3000
        c.save()
        self.assertEqual(c.niveau, Client.Niveau.ARGENT)
        c.points_fidelite = 16000
        c.save()
        self.assertEqual(c.niveau, Client.Niveau.OR)

    def test_credit_disponible_et_plafond(self):
        self.vendre(mode='CREDIT')
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.credit_disponible, Decimal('26000.00'))
        vente = Vente.objects.first()
        self.assertTrue(vente.mode_paiement == Vente.ModePaiement.CREDIT)