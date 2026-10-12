from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status

from apps.accounts.models import User
from apps.produits.models import Produit
from apps.promotions.models import Promotion, PromotionProduit
from apps.promotions.services import impact_promotions, top_promos_impact
from apps.produits.serializers import ProduitDetailSerializer
from apps.clients.models import Client
from apps.parametres.services import invalidate, save_config
from apps.stocks.models import Stock
from apps.ventes.models import Vente, LigneVente


def dans_le_futur(jours=10):
    return timezone.now() + timedelta(days=jours)


def dans_le_passe(jours=5):
    return timezone.now() - timedelta(days=jours)


class PromotionTests(APITestCase):
    """
    Tests CRUD + filtres + permissions de l'API promotions.
    Permission attendue : IsAdminOrReadOnly.
    """

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123'
        )
        self.vendeur = User.objects.create_user(
            username='vendeur', email='vendeur@test.com', password='password123',
            role=User.Role.VENDEUR
        )
        self.promotions_url = reverse('promotions-list')

        self.produit1 = Produit.objects.create(
            nom="Vin Rouge A", type_vin="Rouge", marque="Domaine A",
            cout_revenir=Decimal('10.00'), prix_vente=Decimal('20.00'), statut=True
        )
        self.produit2 = Produit.objects.create(
            nom="Vin Blanc B", type_vin="Blanc", marque="Domaine B",
            cout_revenir=Decimal('8.00'), prix_vente=Decimal('16.00'), statut=True
        )

        self.promo_active = Promotion.objects.create(
            nom="Promo active 10%",
            type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=Decimal('10.00'),
            date_debut=dans_le_passe(), date_fin=dans_le_futur(),
            statut=True
        )
        PromotionProduit.objects.create(promotion=self.promo_active, produit=self.produit1)

        self.promo_expiree = Promotion.objects.create(
            nom="Promo expirée 20%",
            type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=Decimal('20.00'),
            date_debut=dans_le_passe(30), date_fin=dans_le_passe(10),
            statut=True
        )

    def tearDown(self):
        invalidate()
        super().tearDown()

    def authenticate(self, user):
        response = self.client.post(
            reverse('token_obtain_pair'),
            {'username': user.username, 'password': 'password123'}
        )
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])

    # --- Lecture / listes ---

    def test_liste_promotions_vendeur(self):
        self.authenticate(self.vendeur)
        response = self.client.get(self.promotions_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)

    def test_detail_promotion_inclut_produits(self):
        self.authenticate(self.vendeur)
        url = reverse('promotions-detail', args=[self.promo_active.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        noms = [p['nom'] for p in response.data['produits']]
        self.assertIn("Vin Rouge A", noms)

    def test_acces_sans_authentification(self):
        # Lecture publique : le catalogue affiche les campagnes en cours avec
        # leur badge de prix, sans compte (comme pour les produits).
        reponse = self.client.get(self.promotions_url)
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(reponse.data['count'], Promotion.objects.count())
        noms = [p['nom'] for p in reponse.data['results']]
        self.assertIn("Promo active 10%", noms)

        # L'écriture, elle, reste fermée aux visiteurs.
        refus = self.client.post(
            self.promotions_url,
            {"nom": "Promo pirate", "type_promotion": "POURCENTAGE", "valeur": "10",
             "date_debut": dans_le_passe().isoformat(), "date_fin": dans_le_futur().isoformat()},
            format='json',
        )
        self.assertIn(
            refus.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
        self.assertEqual(Promotion.objects.count(), 2)

    # --- Filtres ---

    def test_filtre_active(self):
        self.authenticate(self.vendeur)
        response = self.client.get(f"{self.promotions_url}?active=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        noms = [p['nom'] for p in response.data['results']]
        self.assertIn("Promo active 10%", noms)
        self.assertNotIn("Promo expirée 20%", noms)

    def test_filtre_par_type(self):
        self.authenticate(self.vendeur)
        response = self.client.get(f"{self.promotions_url}?type_promotion=POURCENTAGE")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)

    # --- Création (écriture admin) ---

    def test_creation_promotion_par_admin(self):
        self.authenticate(self.admin)
        data = {
            "nom": "Promo fêtes",
            "type_promotion": "POURCENTAGE",
            "valeur": "15.00",
            "date_debut": (timezone.now() + timedelta(days=1)).isoformat(),
            "date_fin": (timezone.now() + timedelta(days=8)).isoformat(),
            "produits_ids": [self.produit1.id, self.produit2.id],
        }
        response = self.client.post(self.promotions_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        promo = Promotion.objects.get(nom="Promo fêtes")
        self.assertEqual(promo.produits.count(), 2)

    def test_creation_promotion_refusee_vendeur(self):
        self.authenticate(self.vendeur)
        data = {
            "nom": "Promo pirate",
            "type_promotion": "POURCENTAGE",
            "valeur": "10.00",
            "date_debut": dans_le_passe().isoformat(),
            "date_fin": dans_le_futur().isoformat(),
        }
        response = self.client.post(self.promotions_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Promotion.objects.count(), 2)

    def test_valeur_negative_refusee(self):
        # Le modèle impose MinValueValidator(0) sur la valeur
        self.authenticate(self.admin)
        data = {
            "nom": "Promo invalide",
            "type_promotion": "MONTANT_FIXE",
            "valeur": "-5.00",
            "date_debut": dans_le_passe().isoformat(),
            "date_fin": dans_le_futur().isoformat(),
        }
        response = self.client.post(self.promotions_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- Comportement métier ---

    def test_est_active_reflete_la_fenetre_de_dates(self):
        self.assertFalse(self.promo_expiree.est_active)
        self.assertTrue(self.promo_active.est_active)

    def test_serializer_promotion_active_expose_prix_final(self):
        """Le POS affiche prix barré + prix promo à partir de promotion_active."""
        # Promo 10% sur produit1 (20.00) -> prix final 18.00
        serializer = ProduitDetailSerializer(self.produit1)
        promo = serializer.data['promotion_active']
        self.assertEqual(promo['nom'], "Promo active 10%")
        self.assertEqual(promo['remise_unitaire'], Decimal('2.00'))
        self.assertEqual(promo['prix_final'], Decimal('18.00'))

    def test_serializer_sans_promotion(self):
        # produit2 n'a aucune promotion attachée
        serializer = ProduitDetailSerializer(self.produit2)
        self.assertIsNone(serializer.data['promotion_active'])

    def test_serializer_promotion_avec_tarif_detailant(self):
        self.produit1.prix_revendeur = Decimal('15.00')
        self.produit1.save(update_fields=['prix_revendeur'])

        serializer = ProduitDetailSerializer(
            self.produit1,
            context={'type_client': Client.TypeClient.REVENDEUR},
        )

        self.assertEqual(serializer.data['prix_unitaire_vente'], '15.00')
        self.assertEqual(
            serializer.data['promotion_active']['prix_final'], Decimal('13.50'),
        )

    def test_serializer_prend_la_meilleure_promotion(self):
        # 30% (6.00) bat 10% (2.00) sur produit1
        now = timezone.now()
        Promotion.objects.create(
            nom="Promo 30%", type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=Decimal('30.00'),
            date_debut=dans_le_passe(), date_fin=dans_le_futur(), statut=True
        )
        # La M2M est déjà liée via PromotionProduit pour la promo 10% seulement :
        # la nouvelle promotion n'est liée à aucun produit, on la lie à produit1.
        promo30 = Promotion.objects.get(nom="Promo 30%")
        PromotionProduit.objects.create(promotion=promo30, produit=self.produit1)

        serializer = ProduitDetailSerializer(self.produit1)
        promo = serializer.data['promotion_active']
        self.assertEqual(promo['nom'], "Promo 30%")
        self.assertEqual(promo['prix_final'], Decimal('14.00'))

    def test_simulation_applique_tva_ht_au_prix_et_a_la_promotion(self):
        save_config({
            'ventes_tva': '20',
            'ventes_tva_incluse': '0',
        })
        self.authenticate(self.vendeur)

        response = self.client.post(
            reverse('promotions-simuler'),
            {'lignes': [{'produit_id': self.produit1.pk, 'quantite': 1}]},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], Decimal('21.60'))
        self.assertEqual(response.data['lignes'][0]['prix_unitaire'], Decimal('24.00'))
        self.assertEqual(response.data['lignes'][0]['remise'], Decimal('2.40'))

    def test_suppression_promotion_par_admin(self):
        self.authenticate(self.admin)
        url = reverse('promotions-detail', args=[self.promo_active.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Promotion.objects.count(), 1)


def creer_produit_stock(nom, prix_vente):
    produit = Produit.objects.create(
        nom=nom, type_vin="Rouge", marque="Domaine Test",
        cout_revenir=Decimal('5.00'), prix_vente=Decimal(str(prix_vente)), statut=True
    )
    Stock.objects.update_or_create(
        produit=produit, defaults={'quantite': 20, 'seuil_alerte': 2}
    )
    return produit


class VenteRetientPromotionTests(APITestCase):
    """
    La vente enregistre la promotion réellement appliquée sur chaque ligne
    (FK LigneVente.promotion) et alimente l'impact réel des promotions.
    """

    def setUp(self):
        self.vendeur = User.objects.create_user(
            username='vendeur', email='vendeur@test.com', password='password123',
            role=User.Role.VENDEUR,
        )
        self.client_obj = Client.objects.create(
            nom="Dupont", prenom="Jean", telephone="0102030405"
        )
        self.produit = creer_produit_stock("Vin Rouge 2015", 20)
        self.promo = Promotion.objects.create(
            nom="Promo 10%", type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=Decimal('10.00'),
            date_debut=dans_le_passe(), date_fin=dans_le_futur(), statut=True,
        )
        PromotionProduit.objects.create(promotion=self.promo, produit=self.produit)
        response = self.client.post(
            reverse('token_obtain_pair'),
            {'username': 'vendeur', 'password': 'password123'}
        )
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])

    def _vendre(self):
        data = {
            "client": self.client_obj.id,
            "lignes": [{"produit_id": self.produit.id, "quantite": 2}],
        }
        return self.client.post(reverse('ventes-list'), data, format='json')

    def test_ligne_vente_retient_la_promotion_appliquee(self):
        response = self._vendre()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        vente = Vente.objects.latest('date_vente')
        ligne = LigneVente.objects.get(vente=vente)
        self.assertEqual(ligne.promotion, self.promo)
        self.assertEqual(ligne.remise, Decimal('4.00'))  # 2 × 10% de 20.00

    def test_vente_sans_promo_ne_lie_pas_de_promotion(self):
        produit_sans_promo = creer_produit_stock("Vin Blanc simple", 16)
        data = {
            "client": self.client_obj.id,
            "lignes": [{"produit_id": produit_sans_promo.id, "quantite": 1}],
        }
        response = self.client.post(reverse('ventes-list'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        vente = Vente.objects.latest('date_vente')
        ligne = LigneVente.objects.get(vente=vente)
        self.assertIsNone(ligne.promotion)
        self.assertEqual(ligne.remise, Decimal('0'))

    def test_impact_promotions_30_jours(self):
        response = self._vendre()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        impact = impact_promotions(jours=30)
        self.assertGreater(impact['remises_30j'], 0)
        self.assertGreaterEqual(impact['ventes_promo_30j'], 1)
        self.assertGreaterEqual(impact['nb_ventes_30j'], 1)
        self.assertGreater(impact['taux_promo_30j'], 0)
        top = top_promos_impact(limit=5, jours=30)
        self.assertTrue(any(p['promotion__nom'] == self.promo.nom for p in top))
        self.assertTrue(all(p['remise'] > 0 for p in top))


class DechetsAdminTests(APITestCase):
    """Endpoints d'aide à l'admin : chevauchements de promos et prix produits."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123'
        )
        self.vendeur = User.objects.create_user(
            username='vendeur', email='vendeur@test.com', password='password123',
            role=User.Role.VENDEUR,
        )
        self.produit = creer_produit_stock("Vin Rouge 2015", 20)

    def get_token(self, user):
        response = self.client.post(
            reverse('token_obtain_pair'),
            {'username': user.username, 'password': 'password123'}
        )
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])

    def test_chevauchement_detecte_pour_produit_commun(self):
        self.get_token(self.admin)
        promo_existante = Promotion.objects.create(
            nom="Promo 30%", type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=Decimal('30.00'),
            date_debut=dans_le_passe(), date_fin=dans_le_futur(), statut=True,
        )
        PromotionProduit.objects.create(promotion=promo_existante, produit=self.produit)
        url = reverse('promotions-chevauchements')
        # Nouvelle promo (pas encore créée) : 10% sur le même produit, période qui se chevauche
        response = self.client.get(url, {
            'produits': self.produit.id,
            'debut': '2026-01-01T00:00:00',
            'fin': '2026-12-31T23:59:59',
            'type': 'POURCENTAGE',
            'valeur': '10',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        conflits = response.data['conflits']
        self.assertEqual(len(conflits), 1)
        self.assertEqual(conflits[0]['nom'], 'Promo 30%')
        # 30% > 10% : la future promotion serait ignorée sur le produit
        self.assertEqual(conflits[0]['nb_ecrases'], 1)
        self.assertIn('Vin Rouge 2015', conflits[0]['produits_ecrases'])

    def test_chevauchement_respecte_exclusion(self):
        self.get_token(self.admin)
        promo_existante = Promotion.objects.create(
            nom="Promo 30%", type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=Decimal('30.00'),
            date_debut=dans_le_passe(), date_fin=dans_le_futur(), statut=True,
        )
        PromotionProduit.objects.create(promotion=promo_existante, produit=self.produit)
        url = reverse('promotions-chevauchements')
        response = self.client.get(url, {
            'produits': self.produit.id,
            'debut': dans_le_passe().strftime('%Y-%m-%dT%H:%M:%S'),
            'fin': dans_le_futur().strftime('%Y-%m-%dT%H:%M:%S'),
            'type': 'POURCENTAGE',
            'valeur': '10',
            'exclude': promo_existante.id,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['conflits']), 0)

    def test_chevauchement_interdit_aux_vendeurs(self):
        self.get_token(self.vendeur)
        url = reverse('promotions-chevauchements')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_prix_produits_disponible_pour_apercu(self):
        self.get_token(self.admin)
        url = reverse('promotions-prix-produits')
        response = self.client.get(url, {'ids': self.produit.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['produits'][0]['prix_vente'], Decimal('20.00'))
