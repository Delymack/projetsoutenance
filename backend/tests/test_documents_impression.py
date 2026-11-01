"""
Rendu des documents imprimés : facture A4, reçu court, ticket 80 mm et Z-Report.

Ces tests ne vérifient pas la mise en page (aucun moteur CSS en test) mais
l'exactitude des montants annoncés au client. Une facture qui affiche un
mauvais net est un défaut comptable, pas un défaut cosmétique.
"""
from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse
from apps.clients.models import Client
from apps.produits.models import Produit
from apps.parametres.services import invalidate, save_config
from apps.stocks.models import Stock
from apps.ventes.models import Vente
from django.utils import timezone
from apps.ventes.services import CaisseService, ReservationService, RetourService, VenteService

User = get_user_model()


class DocumentImpressionTests(TestCase):
    """Un ticket doit refléter l'intégralité de l'opération de caisse."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username='admin', email='admin@cave.mg', password='x',
        )
        cls.vendeur = User.objects.create_user(
            username='sacha', email='sacha@cave.mg', password='x', role=User.Role.VENDEUR,
        )
        cls.fiche = Client.objects.create(nom='Rakoto', prenom='Hanta', telephone='034 00 000 00')
        cls.vin = Produit.objects.create(
            nom='Syrah Grand Cru', type_vin='Rouge', marque='Domaine Andrian', cout_revenir=Decimal('5000'),
            prix_vente=Decimal('10000'), statut=True,
        )
        Stock.objects.update_or_create(produit=cls.vin, defaults={'quantite': 60, 'seuil_alerte': 2})

    def _vente(self, **kwargs):
        lignes = kwargs.pop('lignes', [{'produit_id': self.vin.id, 'quantite': 2}])
        vente = VenteService.creer_vente(
            client_id=self.fiche.id,
            mode_paiement=kwargs.pop('mode_paiement', Vente.ModePaiement.ESPECES),
            lignes_data=lignes,
            utilisateur=self.vendeur,
            **kwargs,
        )
        return vente

    def _html(self, vente, format_impression=None):
        self.client.force_login(self.admin)
        url = reverse('admin:vente-facture', args=[vente.id])
        reponse = self.client.get(url, {'format': format_impression} if format_impression else {})
        self.assertEqual(reponse.status_code, 200)
        return reponse.content.decode()

    def tearDown(self):
        invalidate()
        super().tearDown()

    # ----------------------------------------------------------------- facture
    def test_facture_a4_annonce_le_total(self):
        html = self._html(self._vente())
        self.assertIn('FAC-', html)
        self.assertIn('Rakoto Hanta', html)
        self.assertIn('20', html)  # 2 × 10 000
        self.assertIn('color:#000 !important', html)
        self.assertIn('.inv-brand .logo, .qr-box', html)

    def test_facture_fige_tva_incluse_et_echeance(self):
        save_config({
            'ventes_tva': '20',
            'ventes_tva_incluse': '1',
            'ventes_delai_paiement_jours': '60',
        })
        vente = self._vente()

        self.assertEqual(vente.total, Decimal('20000.00'))
        self.assertEqual(vente.details_tva['ht'], Decimal('16666.67'))
        self.assertEqual(vente.details_tva['tva'], Decimal('3333.33'))
        self.assertEqual(
            vente.date_echeance,
            timezone.localdate() + timedelta(days=60),
        )
        html = self._html(vente)
        self.assertIn('Échéance', html)
        # La facture formatte les montants à la française (séparateur décimal
        # virgule), comme le reste des prix imprimés.
        self.assertIn('16666,67', html)
        self.assertIn('3333,33', html)

    def test_prix_ht_est_taxe_et_reservation_garde_le_montant(self):
        save_config({
            'ventes_tva': '20',
            'ventes_tva_incluse': '0',
            'ventes_delai_paiement_jours': '60',
        })
        vente = self._vente(lignes=[{'produit_id': self.vin.id, 'quantite': 1}])

        self.assertEqual(vente.total, Decimal('12000.00'))
        self.assertEqual(vente.lignes.get().prix_unitaire, Decimal('12000.00'))
        self.assertEqual(vente.details_tva['ht'], Decimal('10000.00'))
        self.assertEqual(vente.details_tva['tva'], Decimal('2000.00'))

        reservation = ReservationService.creer(
            client_id=self.fiche.id,
            lignes_data=[{'produit_id': self.vin.id, 'quantite': 1}],
            utilisateur=self.vendeur,
        )
        self.assertEqual(reservation.montant_total, Decimal('12000.00'))
        self.assertEqual(
            reservation.lignes.get().prix_unitaire, Decimal('12000.00'),
        )
        vente_reservee, _ = ReservationService.encaisser(
            reservation.id,
            mode_paiement=Vente.ModePaiement.ESPECES,
            utilisateur=self.vendeur,
        )
        self.assertEqual(vente_reservee.total, Decimal('12000.00'))

    def test_facture_reste_au_montant_du_total_apres_retour(self):
        vente = self._vente()
        RetourService.enregistrer(
            vente.id, [{'ligne_id': vente.lignes.first().id, 'quantite': 1}],
            motif='Bouteille cassée', utilisateur=self.vendeur,
        )
        html = self._html(vente)
        # Le brut de 20 000 reste affiché : un retour ne réécrit pas l'historique.
        self.assertIn('Retours remboursés', html)
        self.assertIn('Bouteille cassée', html)
        self.assertIn('10', html)  # le net

    def test_facture_detaille_un_paiement_mixte(self):
        vente = self._vente(paiements=[
            {'mode': Vente.ModePaiement.ESPECES, 'montant': Decimal('10000')},
            {'mode': Vente.ModePaiement.MOBILE_MONEY, 'montant': Decimal('10000')},
        ])
        self.assertTrue(vente.est_paiement_mixte)
        html = self._html(vente)
        self.assertIn('paiement mixte', html)
        self.assertIn('Mobile Money', html)
        self.assertIn('Espèces', html)

    def test_facture_rappelle_le_motif_de_remise_manuelle(self):
        vente = self._vente(
            lignes=[{'produit_id': self.vin.id, 'quantite': 1, 'remise_manuelle': Decimal('500')}],
            motif_remise='Client fidèle',
        )
        html = self._html(vente)
        self.assertIn('Client fidèle', html)
        self.assertIn('Remise manuelle', html)

    def test_facture_deduit_un_acompte_de_reservation(self):
        reservation = ReservationService.creer(
            client_id=self.fiche.id,
            lignes_data=[{'produit_id': self.vin.id, 'quantite': 1}],
            utilisateur=self.vendeur,
            acompte=Decimal('4000'), mode_acompte=Vente.ModePaiement.ESPECES,
        )
        vente, _ = ReservationService.encaisser(
            reservation.id, mode_paiement=Vente.ModePaiement.ESPECES, utilisateur=self.vendeur,
        )
        html = self._html(vente)
        self.assertIn('Acompte déjà versé', html)
        self.assertIn('4000', html)

    # ---------------------------------------------------------------- formats
    def test_ticket_80mm_utilise_la_largeur_du_papier(self):
        html = self._html(self._vente(), 'ticket80')
        self.assertIn('body class="ticket80"', html)
        self.assertIn('size:80mm auto', html)
        # Le QR et les pièces ne tiennent pas sur un rouleau de 80 mm.
        self.assertNotIn('qr-box">\n                    <img', html)

    def test_recu_court_ne_touche_pas_a_la_facture(self):
        html = self._html(self._vente(), 'compact')
        self.assertIn('body class="compact"', html)
        self.assertNotIn('body class="ticket80"', html)

    def test_facture_mixte_propose_les_trois_formats(self):
        html = self._html(self._vente())
        self.assertIn('format=ticket80', html)
        self.assertIn('format=compact', html)


class RapportCaisseTests(TestCase):
    """Le rapport de caisse est la pièce que le comptable contrôle.

    La page Z-Report a été retirée du back-office : ces contrôles restent sur
    le service lui-même, qui alimente la clôture de session et les exports.
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(username='admin', email='a@cave.mg', password='x')
        cls.vendeur = User.objects.create_user(
            username='sacha', email='s@cave.mg', password='x', role=User.Role.VENDEUR,
        )
        # max_credit > 0 : ce client peut régler une partie sur compte client.
        cls.fiche = Client.objects.create(
            nom='Rasoa', prenom='M', telephone='032 11 222 33', max_credit=Decimal('100000'),
        )
        cls.vin = Produit.objects.create(
            nom='Merlot', type_vin='Rouge', marque='Cave', cout_revenir=Decimal('4000'),
            prix_vente=Decimal('9000'), statut=True,
        )
        Stock.objects.update_or_create(produit=cls.vin, defaults={'quantite': 40, 'seuil_alerte': 2})

    def _vendre(self, quantite=1, mode=Vente.ModePaiement.ESPECES, **kwargs):
        return VenteService.creer_vente(
            client_id=self.fiche.id, mode_paiement=mode,
            lignes_data=[{'produit_id': self.vin.id, 'quantite': quantite}],
            utilisateur=self.vendeur, **kwargs,
        )

    def test_le_rapport_annonce_le_ca_net_apres_retour(self):
        vente = self._vendre(quantite=2)
        RetourService.enregistrer(
            vente.id, [{'ligne_id': vente.lignes.first().id, 'quantite': 1}],
            motif='Casse', utilisateur=self.vendeur,
        )
        rapport = CaisseService.rapport_du_jour(timezone.localdate())
        self.assertEqual(rapport['ca_total'], Decimal('18000.00'))
        self.assertEqual(rapport['ca_rembourse'], Decimal('9000.00'))
        self.assertEqual(rapport['ca_net'], Decimal('9000.00'))
        self.assertEqual(rapport['nb_retours'], 1)
        self.assertEqual(rapport['net_especes'], Decimal('9000.00'))

    def test_le_rapport_separe_le_credit_du_guichet(self):
        self._vendre(quantite=1, mode=Vente.ModePaiement.ESPECES)
        self._vendre(quantite=1, mode=Vente.ModePaiement.CREDIT)
        rapport = CaisseService.rapport_du_jour(timezone.localdate())
        self.assertEqual(rapport['ca_especes'], Decimal('9000.00'))
        self.assertEqual(rapport['ca_credit'], Decimal('9000.00'))
        self.assertEqual(rapport['net_credit'], Decimal('9000.00'))

    def test_le_rapport_suit_les_acomptes_de_reservation(self):
        ReservationService.creer(
            client_id=self.fiche.id,
            lignes_data=[{'produit_id': self.vin.id, 'quantite': 1}],
            utilisateur=self.vendeur,
            acompte=Decimal('3000'), mode_acompte=Vente.ModePaiement.ESPECES,
        )
        rapport = CaisseService.rapport_du_jour(timezone.localdate())
        self.assertEqual(rapport['acompte_caisses'], Decimal('3000.00'))
