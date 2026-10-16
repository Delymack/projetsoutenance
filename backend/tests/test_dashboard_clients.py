"""Suivi des clients : meilleurs contributeurs et créances.

Le tableau de bord met en avant les meilleurs clients (30 j) dans un panneau
dédié, en plus de l'indicateur « Clients » et de son raccourci vers la liste.
Les créances, elles, restent calculées par `stats_completes` et consommées par
la page Clients et ses segments. Le contrat ci-dessous verrouille les deux
moitiés.
"""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.clients.models import Client
from apps.dashboard.stats import stats_completes
from apps.produits.models import Produit
from apps.stocks.models import Stock
from apps.ventes.models import Vente
from apps.ventes.services import VenteService


class PanelClientsDashboardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123',
        )
        self.client.force_login(self.admin)
        self.produit = Produit.objects.create(
            nom='Vin test', type_vin='Rouge', cout_revenir=1000, prix_vente=10000,
        )
        self.grand = Client.objects.create(
            nom='Grand Client', prenom='', telephone='0102030405',
            max_credit=Decimal('100000'), solde_du=Decimal('40000'),
        )
        self.petit = Client.objects.create(
            nom='Petit Client', prenom='', telephone='0102030406',
        )
        self.crediteur = Client.objects.create(
            nom='Client À Plat', prenom='', telephone='0102030407',
            max_credit=Decimal('50000'), solde_du=Decimal('0'),
        )
        self._vendre(self.grand, 3)
        self._vendre(self.petit, 1)

    def _vendre(self, client, quantite):
        # La première vente crée le stock du produit : on l'alimente d'abord,
        # sinon la vente est refusée (« Stock insuffisant »).
        Stock.objects.update_or_create(
            produit=self.produit, defaults={'quantite': 1000, 'seuil_alerte': 10},
        )
        # Le prix unitaire vient du produit (10 000 Ar), le CA suit la quantité.
        return VenteService.creer_vente(
            client_id=client.id,
            mode_paiement=Vente.ModePaiement.ESPECES,
            lignes_data=[{'produit_id': self.produit.id, 'quantite': quantite}],
            utilisateur=self.admin,
        )

    def test_les_meilleurs_clients_sont_classes_par_ca_decroissant(self):
        stats = stats_completes()
        noms = [c['client__nom'] for c in stats['top_clients']]
        self.assertEqual(noms, ['Grand Client', 'Petit Client'])
        self.assertEqual(stats['top_clients'][0]['ca'], Decimal('30000'))
        # Répartition en % du CA des clients affichés (30 000 / 40 000).
        parts = [c['part'] for c in stats['top_clients']]
        self.assertEqual(parts, [75, 25])

    def test_les_creances_ressortent_avec_le_credit_restant(self):
        stats = stats_completes()
        createurs = stats['createurs']
        self.assertEqual([c['nom'] for c in createurs], ['Grand Client'])
        # 100 000 de plafond − 40 000 d'encours.
        self.assertEqual(createurs[0]['restant'], Decimal('60000'))
        self.assertEqual(stats['encours_total'], Decimal('40000'))
        self.assertEqual(stats['nb_createurs'], 1)

    def test_un_client_sans_plafond_n_a_pas_de_credit_restant(self):
        Client.objects.create(
            nom='Sans Plafond', prenom='', telephone='0102030408', solde_du=Decimal('10000'),
        )
        stats = stats_completes()
        ligne = next(c for c in stats['createurs'] if c['nom'] == 'Sans Plafond')
        self.assertIsNone(ligne['restant'])

    def test_le_dashboard_signale_les_ruptures_et_renvoie_vers_les_stocks(self):
        """L'accueil met l'alerte stock en avant et renvoie vers la liste."""
        reponse = self.client.get(reverse('admin:index'))
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode()
        self.assertIn('dash-kpi__label">Ruptures de stock<', html)
        self.assertIn(reverse('admin:stocks_stock_changelist'), html)
        # Les créances ne sont pas dupliquées sur l'accueil : elles vivent
        # dans le segment dédié de la page Clients.
        self.assertNotIn('Créances clients', html)

    def test_la_liste_des_clients_expose_le_segment_des_creances(self):
        """Les créances ont migré vers la page Clients, qui reste segmentée."""
        url = reverse('admin:clients_client_changelist') + '?solde_due=1'
        reponse = self.client.get(url)
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode()
        self.assertIn('<input type="hidden" name="solde_due" value="1">', html)
        self.assertIn('Grand Client', html)
        self.assertNotIn('Petit Client', html)
        self.assertContains(
            reponse, f'/admin/clients/client/{self.grand.pk}/change/'
        )

    def test_sans_donnees_le_dashboard_ne_crashe_pas(self):
        # Les ventes protègent leur client (PROTECT) : on les supprime d'abord.
        Vente.objects.all().delete()
        Client.objects.all().delete()
        stats = stats_completes()
        self.assertEqual(stats['top_clients'], [])
        self.assertEqual(stats['createurs'], [])
        self.assertEqual(stats['encours_total'], 0)
        self.assertEqual(self.client.get(reverse('admin:index')).status_code, 200)
