from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status

from apps.accounts.models import User
from apps.clients.models import Client
from apps.produits.models import Produit
from apps.stocks.models import Stock
from apps.promotions.models import Promotion
from apps.ventes.models import Vente
from apps.ventes.services import VenteService


class DashboardTests(APITestCase):
    """
    Tests de l'endpoint GET /api/dashboard/ (statistiques globales).
    Permission attendue : tout utilisateur authentifié (IsAuthenticated).
    """

    def setUp(self):
        self.vendeur = User.objects.create_user(
            username='vendeur', email='vendeur@test.com', password='password123',
            role=User.Role.VENDEUR
        )
        self.client_obj = Client.objects.create(nom="Dupont", prenom="Jean", telephone="0102030405")

        # Produit A : stock normal
        self.produit_a = Produit.objects.create(
            nom="Vin Rouge A", type_vin="Rouge", marque="Domaine A",
            cout_revenir=Decimal('10.00'), prix_vente=Decimal('20.00'), statut=True
        )
        self.stock_a, _ = Stock.objects.update_or_create(produit=self.produit_a, defaults={'quantite': 20, 'seuil_alerte': 5})

        # Produit B : stock faible (quantite <= seuil_alerte et > 0)
        self.produit_b = Produit.objects.create(
            nom="Vin Blanc B", type_vin="Blanc", marque="Domaine B",
            cout_revenir=Decimal('8.00'), prix_vente=Decimal('16.00'), statut=True
        )
        self.stock_b, _ = Stock.objects.update_or_create(produit=self.produit_b, defaults={'quantite': 3, 'seuil_alerte': 5})

        # Produit C : rupture (quantite = 0)
        self.produit_c = Produit.objects.create(
            nom="Vin Rosé C", type_vin="Rosé", marque="Domaine C",
            cout_revenir=Decimal('6.00'), prix_vente=Decimal('12.00'), statut=True
        )
        self.stock_c, _ = Stock.objects.update_or_create(produit=self.produit_c, defaults={'quantite': 0, 'seuil_alerte': 5})

        self.dashboard_url = reverse('dashboard')

    def authenticate(self, user):
        response = self.client.post(
            reverse('token_obtain_pair'),
            {'username': user.username, 'password': 'password123'}
        )
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])

    def vendre(self, produit, quantite):
        """Crée une vente PAYEE via le service métier (décrémente le stock)."""
        return VenteService.creer_vente(
            client_id=self.client_obj.id,
            mode_paiement=Vente.ModePaiement.ESPECES,
            lignes_data=[{"produit_id": produit.id, "quantite": quantite}],
            utilisateur=self.vendeur,
        )

    # --- Accès ---

    def test_acces_sans_authentification(self):
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_acces_vendeur_authentifie(self):
        self.authenticate(self.vendeur)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # --- Structure de la réponse ---

    def test_structure_complete_de_la_reponse(self):
        self.authenticate(self.vendeur)
        response = self.client.get(self.dashboard_url)
        cles_attendues = {
            "total_produits", "total_clients",
            "total_ventes", "chiffre_affaires", "stock_faible",
            "produits_rupture", "promotions_actives", "ventes_recentes",
            "meilleures_ventes", "mouvements_recents",
        }
        self.assertEqual(cles_attendues, set(response.data.keys()))

    # --- Compteurs ---

    def test_compteurs_globaux_et_stocks(self):
        self.authenticate(self.vendeur)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.data["total_produits"], 3)
        self.assertEqual(response.data["total_clients"], 1)
        # B est en stock faible, C est en rupture, A est normal
        self.assertEqual(response.data["stock_faible"], 1)
        self.assertEqual(response.data["produits_rupture"], 1)

    # --- Ventes & chiffre d'affaires ---

    def test_ventes_et_chiffre_affaires(self):
        self.vendre(self.produit_a, 2)   # total 40.00
        self.vendre(self.produit_b, 1)   # total 16.00
        self.authenticate(self.vendeur)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.data["total_ventes"], 2)
        self.assertEqual(response.data["chiffre_affaires"], Decimal('56.00'))

    def test_vente_annulee_exclue_des_statistiques(self):
        vente = self.vendre(self.produit_a, 2)
        VenteService.annuler_vente(vente.id, utilisateur=self.vendeur)

        self.authenticate(self.vendeur)
        response = self.client.get(self.dashboard_url)
        # La vente annulée ne compte ni dans le nombre de ventes, ni dans le CA
        self.assertEqual(response.data["total_ventes"], 0)
        self.assertEqual(response.data["chiffre_affaires"], 0)

    # --- Meilleures ventes ---

    def test_meilleures_ventes_somme_et_classement(self):
        self.vendre(self.produit_a, 2)   # A : 2 unités
        self.vendre(self.produit_a, 1)   # A : 3 unités au total
        self.vendre(self.produit_b, 2)   # B : 2 unités

        self.authenticate(self.vendeur)
        response = self.client.get(self.dashboard_url)
        data = response.data["meilleures_ventes"]

        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["produit__nom"], "Vin Rouge A")
        self.assertEqual(data[0]["total_vendu"], 3)
        self.assertEqual(data[1]["produit__nom"], "Vin Blanc B")
        self.assertEqual(data[1]["total_vendu"], 2)

    def test_meilleures_ventes_ignore_ventes_annulees(self):
        vente = self.vendre(self.produit_a, 2)
        VenteService.annuler_vente(vente.id, utilisateur=self.vendeur)

        self.authenticate(self.vendeur)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.data["meilleures_ventes"], [])

    # --- Promotions actives ---

    def test_promotions_actives_compte_seulement_les_valides(self):
        now = timezone.now()
        # Active : statut + fenêtre en cours
        Promotion.objects.create(
            nom="Promo active", type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=Decimal('10.00'),
            date_debut=now - timedelta(days=1), date_fin=now + timedelta(days=5),
            statut=True
        )
        # Expirée : fenêtre terminée
        Promotion.objects.create(
            nom="Promo expirée", type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=Decimal('15.00'),
            date_debut=now - timedelta(days=30), date_fin=now - timedelta(days=10),
            statut=True
        )
        # Désactivée : statut à False même si les dates sont valides
        Promotion.objects.create(
            nom="Promo désactivée", type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=Decimal('20.00'),
            date_debut=now - timedelta(days=1), date_fin=now + timedelta(days=5),
            statut=False
        )

        self.authenticate(self.vendeur)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.data["promotions_actives"], 1)

    # --- Listes récentes ---

    def test_ventes_recentes_limite_a_5(self):
        for _ in range(6):
            self.vendre(self.produit_a, 1)

        self.authenticate(self.vendeur)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(len(response.data["ventes_recentes"]), 5)
        # Chaque entrée expose les champs utilisés par le frontend
        premiere = response.data["ventes_recentes"][0]
        for cle in ("reference", "client", "total", "date", "statut"):
            self.assertIn(cle, premiere)
        self.assertEqual(premiere["statut"], Vente.Statut.PAYEE)

    def test_mouvements_recents_reflete_les_sorties_de_stock(self):
        vente = self.vendre(self.produit_a, 3)

        self.authenticate(self.vendeur)
        response = self.client.get(self.dashboard_url)
        mouvements = response.data["mouvements_recents"]

        self.assertEqual(len(mouvements), 1)
        self.assertEqual(mouvements[0]["produit"], "Vin Rouge A")
        self.assertEqual(mouvements[0]["quantite"], -3)
        self.assertEqual(mouvements[0]["type"], "Sortie (Vente)")
        self.assertEqual(mouvements[0]["ref"], vente.reference)
