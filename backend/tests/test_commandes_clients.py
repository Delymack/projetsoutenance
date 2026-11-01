import json
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.notifications import notifications_pour_utilisateur
from apps.clients.models import Client
from apps.produits.models import Produit
from apps.stocks.models import Stock
from apps.ventes.models import MessageClient, Reservation, Vente
from apps.ventes.services import CaisseService, ReservationService


class CommandesClientsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='orders-admin', email='orders-admin@test.com', password='password123',
        )
        self.client.force_login(self.admin)
        self.produit = Produit.objects.create(
            nom='Rouge de la vallée', type_vin='Rouge', marque='Domaine Local',
            cout_revenir='4000.00', prix_vente='9000.00', statut=True,
        )
        Stock.objects.update_or_create(
            produit=self.produit, defaults={'quantite': 12, 'seuil_alerte': 2},
        )

    def _commande_site(self, **overrides):
        self.client.logout()
        data = {
            'nom': 'Rakoto',
            'prenom': 'Miora',
            'telephone': '0340001234',
            'email': 'miora@example.com',
            'adresse': '',
            'mode_reception': Reservation.ModeReception.RETRAIT,
            'date_expiration': (timezone.localdate() + timedelta(days=4)).isoformat(),
            'note': 'Appeler avant le retrait',
            'lignes': json.dumps([{'produit_id': self.produit.pk, 'quantite': 2}]),
        }
        data.update(overrides)
        return self.client.post(reverse('commande-client'), data)

    def test_client_envoie_une_commande_de_retrait(self):
        response = self._commande_site()

        self.assertEqual(response.status_code, 302)
        reservation = Reservation.objects.get(source=Reservation.Source.SITE)
        self.assertEqual(reservation.utilisateur, None)
        self.assertEqual(reservation.client.telephone, '0340001234')
        self.assertEqual(reservation.mode_reception, Reservation.ModeReception.RETRAIT)
        self.assertEqual(reservation.montant_total, 18000)
        self.assertEqual(reservation.lignes.get().quantite, 2)
        self.assertContains(self.client.get(reverse('commande-client')), reservation.reference)

    def test_livraison_refusee_sans_adresse(self):
        response = self._commande_site(mode_reception=Reservation.ModeReception.LIVRAISON)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Reservation.objects.exists())

    def test_livraison_enregistre_l_adresse(self):
        response = self._commande_site(
            mode_reception=Reservation.ModeReception.LIVRAISON,
            adresse='12 rue des Vignes, Fianarantsoa',
        )

        self.assertRedirects(response, reverse('commande-client'))
        reservation = Reservation.objects.get(source=Reservation.Source.SITE)
        self.assertEqual(reservation.mode_reception, Reservation.ModeReception.LIVRAISON)
        self.assertEqual(reservation.adresse_livraison, '12 rue des Vignes, Fianarantsoa')

    def test_stock_deja_reserve_ne_peut_pas_etre_commande_deux_fois(self):
        premier = self._commande_site(
            telephone='0340001001',
            lignes=json.dumps([{'produit_id': self.produit.pk, 'quantite': 9}]),
        )
        self.assertEqual(premier.status_code, 302)

        second = self._commande_site(
            telephone='0340001002',
            lignes=json.dumps([{'produit_id': self.produit.pk, 'quantite': 4}]),
        )

        self.assertEqual(second.status_code, 400)
        self.assertEqual(Reservation.objects.count(), 1)

    def test_commande_manuelle_creee_depuis_l_admin(self):
        client = Client.objects.create(nom='Ando', prenom='Lala', telephone='0340004321')
        response = self.client.post(
            reverse('admin:commande-manuelle'),
            {
                'client': client.pk,
                'mode_reception': Reservation.ModeReception.RETRAIT,
                'adresse_livraison': '',
                'date_expiration': (timezone.localdate() + timedelta(days=2)).isoformat(),
                'note': 'Saisie au téléphone',
                'lignes': json.dumps([{'produit_id': self.produit.pk, 'quantite': 1}]),
            },
        )

        reservation = Reservation.objects.get(source=Reservation.Source.INTERNE)
        self.assertRedirects(
            response,
            reverse('admin:ventes_reservation_change', args=[reservation.pk]),
        )
        fiche = self.client.get(response.url)
        self.assertContains(
            fiche,
            f'{reverse("caisse-enregistreuse")}?reservation={reservation.pk}',
        )
        self.assertContains(fiche, 'Encaisser à la caisse')
        self.assertEqual(reservation.utilisateur, self.admin)
        self.assertEqual(reservation.montant_total, 9000)

    def test_commande_manuelle_est_encaissee_depuis_le_flux_caisse(self):
        client = Client.objects.create(nom='Ando', prenom='Lala', telephone='0340004321')
        reservation = ReservationService.creer(
            client_id=client.pk,
            lignes_data=[{'produit_id': self.produit.pk, 'quantite': 2}],
            utilisateur=self.admin,
            acompte=Decimal('3000.00'),
            mode_acompte=Vente.ModePaiement.ESPECES,
        )
        endpoint = reverse('reservations-detail', args=[reservation.pk])
        detail = self.client.get(endpoint)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['solde_du'], '15000.00')

        response = self.client.post(
            reverse('reservations-encaisser', args=[reservation.pk]),
            data=json.dumps({
                'mode_paiement': Vente.ModePaiement.ESPECES,
                'montant': str(reservation.solde_du),
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        reservation.refresh_from_db()
        self.assertEqual(reservation.statut, Reservation.Statut.SOLDEE)
        self.assertEqual(reservation.vente.total, reservation.montant_total)
        self.assertEqual(reservation.vente.acompte_anticipe, Decimal('3000.00'))
        self.assertEqual(reservation.vente.paiements.get().montant, Decimal('15000.00'))

    def test_file_caisse_affiche_commandes_manuelles_et_site_a_traiter(self):
        client_interne = Client.objects.create(nom='Client', prenom='Interne')
        commande_interne = ReservationService.creer(
            client_id=client_interne.pk,
            lignes_data=[{'produit_id': self.produit.pk, 'quantite': 1}],
            utilisateur=self.admin,
        )
        client_site = Client.objects.create(nom='Client', prenom='Site')
        commande_site = ReservationService.creer(
            client_id=client_site.pk,
            lignes_data=[{'produit_id': self.produit.pk, 'quantite': 1}],
            utilisateur=self.admin,
            source=Reservation.Source.SITE,
        )

        response = self.client.get('/api/reservations/?a_retirer=1')

        self.assertEqual(response.status_code, 200)
        commandes = response.data['results']
        par_id = {commande['id']: commande for commande in commandes}
        self.assertEqual(par_id[commande_interne.pk]['source'], Reservation.Source.INTERNE)
        self.assertEqual(par_id[commande_site.pk]['source'], Reservation.Source.SITE)
        self.assertEqual(
            par_id[commande_site.pk]['validation_statut'],
            Reservation.ValidationStatut.A_VALIDER,
        )

    def test_reservation_revendeur_conserve_son_tarif_jusqua_encaissement(self):
        client = Client.objects.create(
            nom='Commerce', prenom='Partenaire', telephone='0340000099',
            type_client=Client.TypeClient.REVENDEUR,
        )
        self.produit.prix_revendeur = 7000
        self.produit.save(update_fields=['prix_revendeur'])

        reservation = ReservationService.creer(
            client_id=client.pk,
            lignes_data=[{'produit_id': self.produit.pk, 'quantite': 2}],
            utilisateur=self.admin,
        )
        self.assertEqual(reservation.montant_total, 14000)

        self.produit.prix_revendeur = 8000
        self.produit.save(update_fields=['prix_revendeur'])
        vente, _ = ReservationService.encaisser(
            reservation.pk, mode_paiement=Vente.ModePaiement.ESPECES,
            utilisateur=self.admin,
        )

        self.assertEqual(vente.total, 14000)
        self.assertEqual(vente.lignes.get().prix_unitaire, 7000)

    def test_nouvelle_commande_et_message_declenchent_des_notifications(self):
        self.client.logout()
        self._commande_site()
        self.client.post(
            reverse('contact-client'),
            {
                'nom': 'Miora', 'telephone': '0340001234', 'email': 'miora@example.com',
                'sujet': 'Disponibilité', 'message': 'Avez-vous ce vin en carton ?',
            },
        )

        notifications = notifications_pour_utilisateur(self.admin)
        titres = [item['title'] for item in notifications]
        self.assertTrue(any('Nouvelle commande client' in titre for titre in titres))
        self.assertIn('Nouveau message client : Disponibilité', titres)
        self.assertEqual(MessageClient.objects.count(), 1)

    def test_message_client_refuse_sans_telephone_ni_email(self):
        response = self.client.post(
            reverse('contact-client'),
            {'nom': 'Miora', 'sujet': 'Question', 'message': 'Rappelez-moi.'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(MessageClient.objects.exists())