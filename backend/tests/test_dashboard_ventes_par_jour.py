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


class VentesParJourTests(APITestCase):
    """
    Tests de GET /api/dashboard/ventes-par-jour/
    (série temporelle CA + nb ventes par jour, ventes PAYEE uniquement).
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
        self.stock, _ = Stock.objects.update_or_create(produit=self.produit, defaults={'quantite': 100, 'seuil_alerte': 5})
        self.url = reverse('dashboard-ventes-par-jour')

    def authenticate(self):
        response = self.client.post(
            reverse('token_obtain_pair'),
            {'username': 'vendeur', 'password': 'password123'}
        )
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])

    def vendre(self, quantite):
        return VenteService.creer_vente(
            client_id=self.client_obj.id,
            mode_paiement=Vente.ModePaiement.ESPECES,
            lignes_data=[{"produit_id": self.produit.id, "quantite": quantite}],
            utilisateur=self.vendeur,
        )

    # --- Accès ---

    def test_acces_sans_authentification(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- Comportement par défaut ---

    def test_defaut_30_jours_avec_remplissage_a_zero(self):
        self.authenticate()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        today = timezone.localdate()
        self.assertEqual(response.data['debut'], (today - timedelta(days=29)).isoformat())
        self.assertEqual(response.data['fin'], today.isoformat())
        # 30 points, un par jour, même sans vente
        self.assertEqual(len(response.data['donnees']), 30)

    # --- Agrégation ---

    def test_ca_et_nombre_de_ventes_du_jour(self):
        self.vendre(2)   # 40.00
        self.vendre(1)   # 20.00

        self.authenticate()
        response = self.client.get(self.url)

        today = timezone.localdate().isoformat()
        ligne_du_jour = [d for d in response.data['donnees'] if d['date'] == today]
        self.assertEqual(len(ligne_du_jour), 1)
        self.assertEqual(ligne_du_jour[0]['nb_ventes'], 2)
        self.assertEqual(ligne_du_jour[0]['chiffre_affaires'], Decimal('60.00'))
        self.assertEqual(response.data['total_chiffre_affaires'], Decimal('60.00'))

    def test_vente_annulee_exclue(self):
        vente = self.vendre(2)
        VenteService.annuler_vente(vente.id, utilisateur=self.vendeur)

        self.authenticate()
        response = self.client.get(self.url)
        self.assertEqual(response.data['total_chiffre_affaires'], Decimal('0.00'))
        today = timezone.localdate().isoformat()
        ligne_du_jour = [d for d in response.data['donnees'] if d['date'] == today]
        self.assertEqual(ligne_du_jour[0]['nb_ventes'], 0)

    def test_ca_moyen_journalier_calcule_sur_jours_avec_ventes(self):
        self.vendre(1)   # jour J : 20.00 (pas de vente sur J-1 -> 0)
        self.authenticate()
        response = self.client.get(self.url)
        # Un seul jour avec ventes : la moyenne porte sur ce jour uniquement
        self.assertEqual(response.data['ca_moyen_journalier'], Decimal('20.00'))

    # --- Paramètres ---

    def test_parametre_jours_personnalise(self):
        self.authenticate()
        response = self.client.get(f"{self.url}?jours=7")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['donnees']), 7)
        self.assertEqual(response.data['debut'], (timezone.localdate() - timedelta(days=6)).isoformat())

    def test_parametres_debut_fin_explicites(self):
        self.vendre(1)
        fin = timezone.localdate()
        debut = fin - timedelta(days=2)

        self.authenticate()
        response = self.client.get(f"{self.url}?debut={debut.isoformat()}&fin={fin.isoformat()}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['donnees']), 3)  # J-2, J-1, J
        self.assertEqual(response.data['total_chiffre_affaires'], Decimal('20.00'))

    def test_plage_excluant_les_ventes(self):
        self.vendre(1)
        fin = timezone.localdate() - timedelta(days=10)
        debut = fin - timedelta(days=4)

        self.authenticate()
        response = self.client.get(f"{self.url}?debut={debut.isoformat()}&fin={fin.isoformat()}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_chiffre_affaires'], Decimal('0.00'))
        self.assertTrue(all(d['nb_ventes'] == 0 for d in response.data['donnees']))

    # --- Validation des paramètres ---

    def test_jours_hors_limites_refuse(self):
        self.authenticate()
        response = self.client.get(f"{self.url}?jours=400")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_jours_non_entier_refuse(self):
        self.authenticate()
        response = self.client.get(f"{self.url}?jours=abc")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_plage_trop_longue_refusee(self):
        self.authenticate()
        fin = timezone.localdate()
        debut = fin - timedelta(days=400)
        response = self.client.get(f"{self.url}?debut={debut.isoformat()}&fin={fin.isoformat()}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_format_date_invalide_refuse(self):
        self.authenticate()
        response = self.client.get(f"{self.url}?debut=17/09/2026&fin={timezone.localdate().isoformat()}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_debut_apres_fin_refuse(self):
        self.authenticate()
        fin = timezone.localdate()
        debut = fin + timedelta(days=5)
        response = self.client.get(f"{self.url}?debut={debut.isoformat()}&fin={fin.isoformat()}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
