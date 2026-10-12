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
from apps.ventes.models import Vente
from apps.ventes.services import VenteService


class DashboardApercuTests(APITestCase):
    """
    Tests de l'endpoint GET /api/dashboard/apercu/ (rafraîchissement live).
    Seules les ventes PAYEES sont comptabilisées.
    """

    def setUp(self):
        self.vendeur = User.objects.create_user(
            username='vendeur', email='vendeur@test.com', password='password123',
            role=User.Role.VENDEUR
        )
        self.client_obj = Client.objects.create(nom="Dupont", prenom="Jean", telephone="0102030405")
        self.produit = Produit.objects.create(
            nom="Vin Rouge A", type_vin="Rouge", marque="Domaine A",
            cout_revenir=Decimal('10.00'), prix_vente=Decimal('20.00'), statut=True
        )
        Stock.objects.update_or_create(produit=self.produit, defaults={'quantite': 50, 'seuil_alerte': 5})
        self.apercu_url = reverse('dashboard-apercu')

    def authenticate(self, user):
        response = self.client.post(
            reverse('token_obtain_pair'),
            {'username': user.username, 'password': 'password123'}
        )
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])

    def vendre(self, produit, quantite):
        return VenteService.creer_vente(
            client_id=self.client_obj.id,
            mode_paiement=Vente.ModePaiement.ESPECES,
            lignes_data=[{"produit_id": produit.id, "quantite": quantite}],
            utilisateur=self.vendeur,
        )

    # --- Accès ---

    def test_acces_sans_authentification(self):
        response = self.client.get(self.apercu_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_acces_vendeur_authentifie(self):
        self.authenticate(self.vendeur)
        response = self.client.get(self.apercu_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # --- Structure ---

    def test_structure_complete_de_la_reponse(self):
        self.authenticate(self.vendeur)
        response = self.client.get(self.apercu_url)
        cles_attendues = {
            "ca_du_jour", "ca_hier", "tendance_ca", "ventes_du_jour",
            "ventes_hier", "tendance_ventes", "panier_moyen", "ruptures",
            "ca_mois", "objectif_mensuel", "objectif_auto",
            "objectif_progression", "jours_restants", "projection_mois",
            "paiements_30j",
        }
        self.assertEqual(cles_attendues, set(response.data.keys()))

    # --- KPI du jour ---

    def test_ca_et_ventes_du_jour(self):
        vente_hier = self.vendre(self.produit, 1)  # 20.00 hier (réaffectée plus bas)
        hier = timezone.localtime() - timedelta(days=1)
        Vente.objects.filter(id=vente_hier.id).update(date_vente=hier)
        self.vendre(self.produit, 2)  # 40.00 aujourd'hui
        self.vendre(self.produit, 1)  # 20.00 aujourd'hui
        self.authenticate(self.vendeur)
        response = self.client.get(self.apercu_url)
        self.assertEqual(response.data["ca_du_jour"], Decimal('60.00'))
        self.assertEqual(response.data["ventes_du_jour"], 2)
        self.assertEqual(response.data["panier_moyen"], Decimal('30.00'))
        # 60 vs 20 hier -> tendance CA positive
        self.assertEqual(response.data["tendance_ca"], 200)

    def test_vente_annulee_exclue_du_jour(self):
        vente = self.vendre(self.produit, 2)
        self.authenticate(self.vendeur)
        VenteService.annuler_vente(vente.id, utilisateur=self.vendeur)
        response = self.client.get(self.apercu_url)
        self.assertEqual(response.data["ca_du_jour"], 0)
        self.assertEqual(response.data["ventes_du_jour"], 0)

    # --- Moyens de paiement ---

    def test_paiements_30j_regroupes_par_mode(self):
        self.vendre(self.produit, 1)  # 20.00 espèces
        vente = self.vendre(self.produit, 1)
        Vente.objects.filter(id=vente.id).update(mode_paiement=Vente.ModePaiement.CARTE)

        self.authenticate(self.vendeur)
        response = self.client.get(self.apercu_url)
        paiements = response.data["paiements_30j"]
        by_code = {p["code"]: p for p in paiements}
        self.assertIn("ESPECES", by_code)
        self.assertIn("CARTE", by_code)
        self.assertEqual(by_code["ESPECES"]["montant"], 20.0)
        self.assertEqual(by_code["ESPECES"]["part"], 50.0)
        self.assertEqual(by_code["CARTE"]["montant"], 20.0)

    # --- Objectif mensuel ---

    def test_objectif_auto_double_du_ca_mois_precedent(self):
        vente = self.vendre(self.produit, 1)  # 20.00 ce mois-ci
        now = timezone.localtime()
        # Premier jour du mois d'avant : le retirer de 40 jours ne tombe pas
        # forcément sur le mois précédent (les 21 premiers jours du mois, si).
        mois_precedent = (now.replace(day=1) - timedelta(days=1))
        Vente.objects.filter(id=vente.id).update(date_vente=mois_precedent)

        self.authenticate(self.vendeur)
        response = self.client.get(self.apercu_url)
        # Objectif auto = 2 x CA du mois précédent (20.00)
        self.assertEqual(response.data["objectif_mensuel"], Decimal('40.00'))
        self.assertTrue(response.data["objectif_auto"])
        # CA du mois en cours = 0 -> progression affichée à zéro
        self.assertEqual(response.data["ca_mois"], Decimal('0.00'))
        self.assertEqual(response.data["objectif_progression"], 0)

    def test_objectif_fixe_depuis_les_reglages(self):
        from django.test import override_settings
        self.vendre(self.produit, 1)  # 20.00 ce mois-ci

        with override_settings(SOCIETE={"objectif_mensuel": 100}):
            self.authenticate(self.vendeur)
            response = self.client.get(self.apercu_url)

        self.assertEqual(response.data["objectif_mensuel"], Decimal('100.00'))
        self.assertFalse(response.data["objectif_auto"])
        self.assertEqual(response.data["objectif_progression"], 20)