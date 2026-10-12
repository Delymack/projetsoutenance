from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import User
from apps.produits.models import Produit
from apps.stocks.models import Stock
from apps.clients.models import Client
from apps.ventes.models import Vente, LigneVente
from apps.promotions.models import Promotion, PromotionProduit

class VentesEtStocksTests(APITestCase):
    def setUp(self):
        self.vendeur = User.objects.create_user(username='vendeur', email='vendeur@test.com', password='password123', role=User.Role.VENDEUR)
        self.client_obj = Client.objects.create(nom="Dupont", prenom="Jean", telephone="0102030405")
        
        self.produit = Produit.objects.create(
            nom="Vin Rouge 2015", type_vin="Rouge", marque="Château A",
            cout_revenir=Decimal('10.00'), prix_vente=Decimal('20.00'), statut=True
        )
        self.stock, _ = Stock.objects.update_or_create(produit=self.produit, defaults={'quantite': 10, 'seuil_alerte': 2})
        
        self.ventes_url = reverse('ventes-list')
        
        # S'authentifier
        response = self.client.post(reverse('token_obtain_pair'), {'username': 'vendeur', 'password': 'password123'})
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])

    def test_vente_stock_suffisant(self):
        data = {
            "client": self.client_obj.id,
            "mode_paiement": "ESPECES",
            "lignes": [
                {"produit_id": self.produit.id, "quantite": 3}
            ]
        }
        response = self.client.post(self.ventes_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['data']['total'], '60.00')  # 3 * 20.00
        
        # Vérifier stock diminué
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantite, 7)

    def test_vente_revendeur_applique_le_tarif_detailant(self):
        self.client_obj.type_client = Client.TypeClient.REVENDEUR
        self.client_obj.save()
        self.produit.prix_revendeur = Decimal('15.00')
        self.produit.save(update_fields=['prix_revendeur'])

        response = self.client.post(self.ventes_url, {
            "client": self.client_obj.id,
            "mode_paiement": "ESPECES",
            "lignes": [{"produit_id": self.produit.id, "quantite": 3}],
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['data']['total'], '45.00')
        self.assertEqual(
            response.data['data']['lignes'][0]['prix_unitaire'], '15.00',
        )

    def test_tarif_detailant_est_calcule_par_bouteille_en_carton(self):
        self.client_obj.type_client = Client.TypeClient.REVENDEUR
        self.client_obj.save()
        self.produit.prix_revendeur = Decimal('15.00')
        self.produit.unite_vente = self.produit.UniteVente.CARTON
        self.produit.contenance = 12
        self.produit.save(update_fields=[
            'prix_revendeur', 'unite_vente', 'contenance',
        ])
        self.stock.quantite = 24
        self.stock.save(update_fields=['quantite'])

        response = self.client.post(self.ventes_url, {
            "client": self.client_obj.id,
            "mode_paiement": "ESPECES",
            "lignes": [{
                "produit_id": self.produit.id, "quantite": 1, "unite": "CARTON",
            }],
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['data']['total'], '180.00')
        self.assertEqual(response.data['data']['lignes'][0]['contenance'], 12)

    def test_vente_stock_insuffisant(self):
        data = {
            "client": self.client_obj.id,
            "lignes": [{"produit_id": self.produit.id, "quantite": 15}]
        }
        response = self.client.post(self.ventes_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('stock', response.data['errors'])
        
        # Stock ne doit pas avoir bougé
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantite, 10)

    def test_vente_produit_inactif_refusee(self):
        produit_inactif = Produit.objects.create(
            nom="Vin Blanc inactif", type_vin="Blanc", marque="Château B",
            cout_revenir=Decimal('8.00'), prix_vente=Decimal('18.00'), statut=False
        )
        Stock.objects.update_or_create(produit=produit_inactif, defaults={'quantite': 5, 'seuil_alerte': 1})

        data = {
            "client": self.client_obj.id,
            "lignes": [{"produit_id": produit_inactif.id, "quantite": 2}]
        }
        response = self.client.post(self.ventes_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Format DRF imbriqué : erreurs du serializer LigneVente sous lignes[0]
        self.assertIn('produit', response.data['errors']['lignes'][0])

    def test_vente_lignes_doublons_refusee(self):
        data = {
            "client": self.client_obj.id,
            "lignes": [
                {"produit_id": self.produit.id, "quantite": 2},
                {"produit_id": self.produit.id, "quantite": 1}
            ]
        }
        response = self.client.post(self.ventes_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('lignes', response.data['errors'])

    def test_promotion_active_appliquee(self):
        now = timezone.now()
        promo = Promotion.objects.create(
            nom="Promo 10%", type_promotion="POURCENTAGE", valeur=Decimal('10.00'),
            date_debut=now - timedelta(days=1), date_fin=now + timedelta(days=5), statut=True
        )
        PromotionProduit.objects.create(promotion=promo, produit=self.produit)
        
        data = {
            "client": self.client_obj.id,
            "lignes": [{"produit_id": self.produit.id, "quantite": 2}]
        }
        response = self.client.post(self.ventes_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Prix normal = 40, avec 10% = 36
        self.assertEqual(response.data['data']['total'], '36.00')
        self.assertEqual(response.data['data']['lignes'][0]['remise'], '4.00')

    def test_annulation_vente_restaure_stock(self):
        # Création de la vente via le service ou l'API
        data = {
            "client": self.client_obj.id,
            "lignes": [{"produit_id": self.produit.id, "quantite": 2}]
        }
        res = self.client.post(self.ventes_url, data, format='json')
        vente_id = res.data['data']['id']
        
        # Le stock est maintenant à 8
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantite, 8)
        
        # On annule (nécessite admin pour l'annulation dans mon setup par défaut)
        # Mais le test utilise un superuser pour être sûr
        admin = User.objects.create_superuser(username='admin', email='admin@test.com', password='password123')
        res_auth = self.client.post(reverse('token_obtain_pair'), {'username': 'admin', 'password': 'password123'})
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + res_auth.data['access'])
        
        annuler_url = reverse('ventes-annuler', kwargs={'pk': vente_id})
        response_annul = self.client.post(annuler_url)
        self.assertEqual(response_annul.status_code, status.HTTP_200_OK)
        
        # Le stock est revenu à 10
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantite, 10)
