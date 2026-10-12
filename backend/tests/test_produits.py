from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from apps.accounts.models import User
from apps.clients.models import Client
from apps.parametres.services import invalidate, save_config
from apps.produits.models import Produit
from apps.promotions.models import Promotion, PromotionProduit

class ProduitTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='admin', email='admin@test.com', password='password123')
        self.vendeur = User.objects.create_user(username='vendeur', email='vendeur@test.com', password='password123', role=User.Role.VENDEUR)
        self.produits_url = reverse('produits-list')

        # Création de produits initiaux
        self.produit1 = Produit.objects.create(
            nom="Vin Rouge Bdx", type_vin="Rouge", marque="Domaine X",
            cout_revenir=10.0, prix_vente=20.0, statut=True
        )

    def tearDown(self):
        invalidate()
        super().tearDown()

    def authenticate_admin(self):
        response = self.client.post(reverse('token_obtain_pair'), {'username': 'admin', 'password': 'password123'})
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])

    def test_creation_produit_par_admin(self):
        self.authenticate_admin()
        data = {
            "nom": "Vin Blanc Sec",
            "type_vin": "Blanche",
            "marque": "Domaine Y",
            "volume": "75cl",
            "cout_revenir": 8.0,
            "prix_vente": 15.0
        }
        response = self.client.post(self.produits_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Produit.objects.count(), 2)

    def test_recherche_produit(self):
        # Accessible sans auth grâce à IsAdminOrReadOnly ? Non, par défaut tout nécessite auth,
        # Sauf que les routes produits ont IsAdminOrReadOnly (donc Vendeur peut lire si auth)
        response = self.client.post(reverse('token_obtain_pair'), {'username': 'vendeur', 'password': 'password123'})
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])
        
        response = self.client.get(f"{self.produits_url}?search=Bdx")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['nom'], "Vin Rouge Bdx")

    def test_catalogue_affiche_le_tarif_detailant_du_client(self):
        client_pro = Client.objects.create(
            nom='Commerce', prenom='Partenaire', telephone='0340000001',
            type_client=Client.TypeClient.REVENDEUR,
        )
        self.produit1.prix_revendeur = 15
        self.produit1.save(update_fields=['prix_revendeur'])
        self.client.force_authenticate(user=self.vendeur)

        response = self.client.get(
            self.produits_url, {'client': client_pro.pk},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['results'][0]['prix_unitaire_vente'], '15.00',
        )

    def test_catalogue_applique_le_tarif_par_bouteille_au_pack_professionnel(self):
        client_pro = Client.objects.create(
            nom='Commerce', prenom='Partenaire', telephone='0340000004',
            type_client=Client.TypeClient.REVENDEUR,
        )
        self.produit1.unite_vente = Produit.UniteVente.PACK
        self.produit1.contenance = 6
        self.produit1.prix_conditionnement = 100
        self.produit1.prix_revendeur = 15
        self.produit1.save(update_fields=[
            'unite_vente', 'contenance', 'prix_conditionnement', 'prix_revendeur',
        ])
        self.client.force_authenticate(user=self.vendeur)

        public = self.client.get(self.produits_url)
        professionnel = self.client.get(
            self.produits_url, {'client': client_pro.pk},
        )

        self.assertEqual(public.status_code, status.HTTP_200_OK)
        self.assertEqual(professionnel.status_code, status.HTTP_200_OK)
        self.assertEqual(public.data['results'][0]['prix_unitaire_vente'], '100.00')
        self.assertEqual(professionnel.data['results'][0]['prix_unitaire_vente'], '90.00')

    def test_tarif_professionnel_du_conditionnement_est_calcule_par_bouteille(self):
        self.produit1.unite_vente = Produit.UniteVente.PACK
        self.produit1.contenance = 6
        self.produit1.prix_conditionnement = 100
        self.produit1.prix_revendeur = 15

        self.assertEqual(
            self.produit1.prix_unitaire_pour_client(
                Client.TypeClient.REVENDEUR,
                Produit.UniteVente.PACK,
            ),
            Decimal('90.00'),
        )

    def test_tarif_public_du_conditionnement_configure_reste_prioritaire(self):
        self.produit1.unite_vente = Produit.UniteVente.PACK
        self.produit1.contenance = 6
        self.produit1.prix_conditionnement = 100

        self.assertEqual(
            self.produit1.prix_unitaire_pour_client(
                Client.TypeClient.PARTICULIER,
                Produit.UniteVente.PACK,
            ),
            Decimal('100.00'),
        )

    def test_tarif_revendeur_nul_replie_vers_le_tarif_public(self):
        self.produit1.prix_revendeur = 0

        self.assertEqual(
            self.produit1.prix_unitaire_pour_client(
                Client.TypeClient.REVENDEUR,
                Produit.UniteVente.BOUTEILLE,
            ),
            Decimal('20.00'),
        )

    def test_catalogue_applique_la_tva_aux_tarifs_public_et_professionnel_ht(self):
        client_pro = Client.objects.create(
            nom='Commerce', prenom='Partenaire', telephone='0340000002',
            type_client=Client.TypeClient.REVENDEUR,
        )
        self.produit1.prix_revendeur = 15
        self.produit1.save(update_fields=['prix_revendeur'])
        save_config({
            'ventes_tva': '20',
            'ventes_tva_incluse': '0',
        })
        self.client.force_authenticate(user=self.vendeur)

        public = self.client.get(self.produits_url)
        professionnel = self.client.get(
            self.produits_url, {'client': client_pro.pk},
        )

        self.assertEqual(public.status_code, status.HTTP_200_OK)
        self.assertEqual(professionnel.status_code, status.HTTP_200_OK)
        self.assertEqual(public.data['results'][0]['prix_unitaire_vente'], '24.00')
        self.assertEqual(professionnel.data['results'][0]['prix_unitaire_vente'], '18.00')

    def test_catalogue_ne_rajoute_pas_la_tva_a_un_tarif_deja_ttc(self):
        client_pro = Client.objects.create(
            nom='Commerce', prenom='Partenaire', telephone='0340000003',
            type_client=Client.TypeClient.REVENDEUR,
        )
        self.produit1.prix_revendeur = 15
        self.produit1.save(update_fields=['prix_revendeur'])
        save_config({
            'ventes_tva': '20',
            'ventes_tva_incluse': '1',
        })
        self.client.force_authenticate(user=self.vendeur)

        response = self.client.get(
            self.produits_url, {'client': client_pro.pk},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['prix_unitaire_vente'], '15.00')

    def test_catalogue_ajoute_la_tva_si_les_prix_sont_ht(self):
        save_config({
            'ventes_tva': '20',
            'ventes_tva_incluse': '0',
        })
        self.client.force_authenticate(user=self.vendeur)

        response = self.client.get(self.produits_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['results'][0]['prix_unitaire_vente'], '24.00',
        )

    def test_statistiques_produits_avec_promotion_active(self):
        """L'endpoint /statistiques/ fonctionne et compte les produits en promo."""
        self.authenticate_admin()
        from datetime import timedelta
        from django.utils import timezone
        promo = Promotion.objects.create(
            nom="Promo cave", type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=10,
            date_debut=timezone.now() - timedelta(days=1),
            date_fin=timezone.now() + timedelta(days=1),
            statut=True,
        )
        PromotionProduit.objects.create(promotion=promo, produit=self.produit1)

        response = self.client.get(f"{self.produits_url}statistiques/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], 1)
        self.assertEqual(response.data['en_promo'], 1)
