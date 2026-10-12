"""
Circuit de validation d'une commande du site dans le back-office.

Ces tests verrouillent les trois gestes du vendeur — Valider, Refuser,
Encaisser — et la règle métier qui les relie : une commande du site ne peut
être encaissée qu'après validation. Ils couvrent les vues admin réelles
(`reservation-valider` / `-refuser` / `-encaisser`) ainsi que le service, pour
qu'une régression du workflow casse la CI et non la soutenance.
"""
from decimal import Decimal

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.clients.models import Client
from apps.produits.models import Produit
from apps.stocks.models import Stock
from apps.ventes.models import Reservation, Vente
from apps.ventes.services import ReservationService


class WorkflowValidationAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin-wf', email='admin-wf@test.com', password='MotDePasse123',
        )
        self.produit = Produit.objects.create(
            nom='Cuvée workflow', type_vin='Rouge', marque='Domaine',
            cout_revenir=Decimal('5000.00'), prix_vente=Decimal('10000.00'),
            statut=True,
        )
        Stock.objects.update_or_create(
            produit=self.produit, defaults={'quantite': 20, 'seuil_alerte': 2},
        )
        self.client_obj = Client.objects.create(
            nom='Rakoto', prenom='Hanta', telephone='0340000001',
        )
        self.client.force_login(self.admin)

    def _commande_site(self):
        return ReservationService.creer(
            client_id=self.client_obj.id,
            lignes_data=[{'produit_id': self.produit.id, 'quantite': 2, 'unite': 'BOUTEILLE'}],
            utilisateur=self.admin,
            source=Reservation.Source.SITE,
        )

    # -- Règle métier (service) ------------------------------------------------

    def test_encaisser_une_commande_non_validee_est_refuse(self):
        """Le service refuse l'encaissement tant que la commande n'est pas validée."""
        reservation = self._commande_site()
        self.assertEqual(reservation.validation_statut, Reservation.ValidationStatut.A_VALIDER)

        with self.assertRaises(ValidationError) as ctx:
            ReservationService.encaisser(
                reservation.id, mode_paiement=Vente.ModePaiement.ESPECES, utilisateur=self.admin,
            )
        self.assertIn('validation_statut', ctx.exception.detail)

    def test_cycle_complet_valider_puis_encaisser(self):
        """Valider puis encaisser : le stock bouge et une vente est créée."""
        reservation = self._commande_site()

        ReservationService.valider(reservation.id, self.admin)
        reservation.refresh_from_db()
        self.assertEqual(reservation.validation_statut, Reservation.ValidationStatut.VALIDEE)
        self.assertIsNone(reservation.vente)  # valider ne crée pas de vente

        vente, _ = ReservationService.encaisser(
            reservation.id, mode_paiement=Vente.ModePaiement.ESPECES, utilisateur=self.admin,
        )
        reservation.refresh_from_db()
        self.assertEqual(reservation.statut, Reservation.Statut.SOLDEE)
        self.assertEqual(reservation.vente, vente)
        # 2 bouteilles déduites du stock de départ (20 → 18).
        self.assertEqual(Stock.objects.get(produit=self.produit).quantite, 18)

    def test_refus_exige_un_motif(self):
        """Le service refuse un motif trop court ou vide."""
        reservation = self._commande_site()

        with self.assertRaises(ValidationError) as ctx:
            ReservationService.refuser(reservation.id, self.admin, 'ok')
        self.assertIn('motif', ctx.exception.detail)

    def test_refus_annule_et_trace_le_motif(self):
        reservation = self._commande_site()

        ReservationService.refuser(reservation.id, self.admin, 'Rupture de stock')
        reservation.refresh_from_db()
        self.assertEqual(reservation.validation_statut, Reservation.ValidationStatut.REFUSEE)
        self.assertEqual(reservation.statut, Reservation.Statut.ANNULEE)
        self.assertEqual(reservation.motif_refus, 'Rupture de stock')
        self.assertEqual(reservation.validation_par, self.admin)

    # -- Vues admin (boutons réels) -------------------------------------------

    def test_vue_valider_depuis_l_admin(self):
        reservation = self._commande_site()

        response = self.client.post(reverse('admin:reservation-valider', args=[reservation.pk]))

        self.assertEqual(response.status_code, 302)
        reservation.refresh_from_db()
        self.assertEqual(reservation.validation_statut, Reservation.ValidationStatut.VALIDEE)

    def test_vue_refuser_get_puis_post(self):
        """Le GET affiche le formulaire motif ; le POST applique le refus."""
        reservation = self._commande_site()

        get = self.client.get(reverse('admin:reservation-refuser', args=[reservation.pk]))
        self.assertEqual(get.status_code, 200)
        self.assertContains(get, 'name="motif"')

        post = self.client.post(
            reverse('admin:reservation-refuser', args=[reservation.pk]),
            {'motif': 'Délai trop long'},
        )
        self.assertEqual(post.status_code, 302)
        reservation.refresh_from_db()
        self.assertEqual(reservation.validation_statut, Reservation.ValidationStatut.REFUSEE)

    def test_vue_refuser_motif_vide_affiche_erreur_lisible(self):
        """Un motif vide renvoie un message d'erreur, pas une exception serveur."""
        reservation = self._commande_site()

        response = self.client.post(
            reverse('admin:reservation-refuser', args=[reservation.pk]),
            {'motif': ''},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('motif' in m for m in messages), messages)
        reservation.refresh_from_db()
        self.assertEqual(reservation.validation_statut, Reservation.ValidationStatut.A_VALIDER)

    def test_vue_encaisser_sur_commande_non_validee_affiche_erreur_lisible(self):
        """
        Même en forçant l'URL, l'encaissement d'une commande non validée affiche
        un message clair (« validation_statut : … ») et non le dict brut.
        """
        reservation = self._commande_site()

        response = self.client.post(
            reverse('admin:reservation-encaisser', args=[reservation.pk]),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('valider' in m.lower() for m in messages), messages)
        reservation.refresh_from_db()
        self.assertIsNone(reservation.vente)

    def test_vue_encaisser_apres_validation_cree_la_vente(self):
        reservation = self._commande_site()
        ReservationService.valider(reservation.id, self.admin)

        response = self.client.post(
            reverse('admin:reservation-encaisser', args=[reservation.pk]),
        )
        self.assertEqual(response.status_code, 302)
        reservation.refresh_from_db()
        self.assertIsNotNone(reservation.vente)

    # -- Boutons de la liste ---------------------------------------------------

    def test_boutons_valider_et_refuser_presents_sur_commande_a_valider(self):
        from apps.ventes.admin import ReservationAdmin

        reservation = self._commande_site()
        boutons = str(ReservationAdmin(Reservation, None).actions_reservation(reservation))
        self.assertIn('Valider', boutons)
        self.assertIn('Refuser', boutons)
        self.assertNotIn('Encaisser', boutons)

    def test_bouton_encaisser_present_uniquement_apres_validation(self):
        from apps.ventes.admin import ReservationAdmin

        reservation = self._commande_site()
        ReservationService.valider(reservation.id, self.admin)
        reservation.refresh_from_db()

        boutons = str(ReservationAdmin(Reservation, None).actions_reservation(reservation))
        self.assertIn('Encaisser', boutons)
        self.assertNotIn('Valider', boutons)

