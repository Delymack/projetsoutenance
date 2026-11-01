"""
Commande passée depuis le site Angular, sans compte.

Le client du site n'a aucun jeton : la commande part par
`POST /api/reservations/site/` (anonyme, limité en débit) puis se suit par
référence via `GET /api/reservations/suivi/<reference>/`. Ces deux ports
sont les seuls ouverts sans authentification — la liste des réservations
reste réservée à la caisse.
"""
from decimal import Decimal
from unittest import mock
from urllib.parse import urlparse

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.produits.models import Produit
from apps.stocks.models import Stock
from apps.ventes.factures import facture_url
from apps.ventes.models import Reservation
from apps.ventes.services import ReservationService


class ReservationSiteTests(TestCase):
    def setUp(self):
        self.produit = Produit.objects.create(
            nom="Cuvée 2018", type_vin="Rouge", marque="Domaine",
            cout_revenir=Decimal('5000.00'), prix_vente=Decimal('10000.00'),
            statut=True,
        )
        Stock.objects.update_or_create(
            produit=self.produit, defaults={'quantite': 20, 'seuil_alerte': 2},
        )
        self.corps = {
            'nom': 'Rakoto',
            'prenom': 'Hanta',
            'telephone': '0340000001',
            'email': 'client@test.com',
            'mode_reception': 'RETRAIT',
            'adresse_livraison': '',
            'note': '',
            'lignes': [{'produit_id': self.produit.id, 'quantite': 2, 'unite': 'BOUTEILLE'}],
        }

    def _publier(self):
        return self.client.post(
            reverse('reservations-site'), self.corps, content_type='application/json',
        )

    def test_le_site_enregistre_une_commande_en_attente(self):
        response = self._publier()

        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.json()['success'])
        reservation = Reservation.objects.get()
        self.assertEqual(reservation.statut, Reservation.Statut.EN_ATTENTE)
        self.assertEqual(reservation.source, Reservation.Source.SITE)
        self.assertEqual(reservation.validation_statut, Reservation.ValidationStatut.A_VALIDER)
        self.assertEqual(str(reservation.montant_total), '20000.00')
        # Rien n'est encaissé ni déstocké avant le passage en caisse.
        self.assertEqual(reservation.vente, None)
        self.assertEqual(Stock.objects.get(produit=self.produit).quantite, 20)

    def test_le_suivi_retrouve_la_commande_avec_sa_reference(self):
        self._publier()
        reference = Reservation.objects.get().reference

        response = self.client.get(
            reverse('reservations-suivi', kwargs={'reference': reference}),
        )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['data']['reference'], reference)
        self.assertEqual(payload['data']['statut'], 'EN_ATTENTE')
        self.assertEqual(payload['data']['lignes'][0]['produit_id'], self.produit.id)

    def test_le_suivi_d_une_reference_inconnue_renvoie_404(self):
        response = self.client.get(
            reverse('reservations-suivi', kwargs={'reference': 'RES-DEADBEEF'}),
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()['success'])

    def test_la_liste_des_reservations_reste_privee(self):
        """Sans jeton, la file d'attente de la caisse n'est pas lisible."""
        response = self.client.get(reverse('reservations-list'))
        self.assertIn(response.status_code, (401, 403))

    def test_les_champs_manquants_renvoient_une_erreur_detaillee(self):
        """Un champ obligatoire manquant produit une 400 avec le détail par champ."""
        corps_incomplet = {**self.corps}
        del corps_incomplet['telephone']
        response = self.client.post(
            reverse('reservations-site'), corps_incomplet, content_type='application/json',
        )

        self.assertEqual(response.status_code, 400, response.content)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertIn('telephone', payload['errors'])
        self.assertFalse(Reservation.objects.exists())


class MesCommandesTests(TestCase):
    """`GET /api/reservations/mes-commandes/` : l'espace client connecté."""

    def setUp(self):
        from apps.accounts.models import User

        self.produit = Produit.objects.create(
            nom="Cuvée 2018", type_vin="Rouge", marque="Domaine",
            cout_revenir=Decimal('5000.00'), prix_vente=Decimal('10000.00'),
            statut=True,
        )
        Stock.objects.update_or_create(
            produit=self.produit, defaults={'quantite': 20, 'seuil_alerte': 2},
        )
        self.user = User.objects.create_user(
            username='miora', email='client@test.com', password='x',
            role=User.Role.CLIENT,
        )
        self.url = reverse('reservations-mes-commandes')

    def _publier(self, telephone='0340000001', email='client@test.com'):
        self.client.logout()
        return self.client.post(
            reverse('reservations-site'),
            {
                'nom': 'Rakoto', 'prenom': 'Hanta',
                'telephone': telephone, 'email': email,
                'mode_reception': 'RETRAIT', 'adresse_livraison': '', 'note': '',
                'lignes': [{'produit_id': self.produit.id, 'quantite': 2,
                            'unite': 'BOUTEILLE'}],
            },
            content_type='application/json',
        )

    def test_client_connecte_retrouve_sa_commande(self):
        self._publier()
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(len(payload['data']), 1)
        reservation = payload['data'][0]
        self.assertEqual(reservation['statut'], 'EN_ATTENTE')
        self.assertEqual(reservation['client']['email'], 'client@test.com')
        # Le frontend affiche des libellés : la ligne porte le nom du produit.
        self.assertEqual(reservation['lignes'][0]['produit_nom'], self.produit.nom)

    def test_commande_d_un_autre_client_absente(self):
        self._publier(email='autre@test.com', telephone='0340009999')
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data'], [])

    def test_anonyme_refuse(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (401, 403))


class ValidationCommandeTests(APITestCase):
    def setUp(self):
        self.produit = Produit.objects.create(
            nom='Cuvée validation', type_vin='Rouge', marque='Domaine',
            cout_revenir=Decimal('5000.00'), prix_vente=Decimal('10000.00'),
            statut=True,
        )
        Stock.objects.update_or_create(
            produit=self.produit, defaults={'quantite': 20, 'seuil_alerte': 2},
        )
        self.vendeur = User.objects.create_user(
            username='vendeur-validation', password='password123', role=User.Role.VENDEUR,
        )
        self.client_user = User.objects.create_user(
            username='client-validation', email='client-validation@test.com',
            password='password123', role=User.Role.CLIENT,
        )
        self.payload = {
            'nom': 'Rakoto', 'prenom': 'Hanta', 'telephone': '0340000002',
            'email': 'client-validation@test.com', 'mode_reception': 'RETRAIT',
            'lignes': [{'produit_id': self.produit.pk, 'quantite': 2}],
        }

    def _creer_commande(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse('reservations-site'), self.payload, format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        return Reservation.objects.get(reference=response.data['data']['reference'])

    def test_commande_connectee_est_liee_au_compte(self):
        reservation = self._creer_commande()

        self.assertEqual(reservation.compte_client, self.client_user)
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(reverse('reservations-mes-commandes'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['data']), 1)

    def test_vendeur_valide_sans_encaisser_ni_deduir_le_stock(self):
        reservation = self._creer_commande()
        self.client.force_authenticate(user=self.vendeur)

        response = self.client.post(
            reverse('reservations-valider', kwargs={'pk': reservation.pk}),
            {}, format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        reservation.refresh_from_db()
        self.assertEqual(reservation.validation_statut, Reservation.ValidationStatut.VALIDEE)
        self.assertEqual(reservation.validation_par, self.vendeur)
        self.assertIsNotNone(reservation.validation_le)
        self.assertEqual(reservation.statut, Reservation.Statut.EN_ATTENTE)
        self.assertIsNone(reservation.vente)
        self.assertEqual(Stock.objects.get(produit=self.produit).quantite, 20)

    def test_refus_annule_la_commande_et_laisse_une_trace(self):
        reservation = self._creer_commande()
        self.client.force_authenticate(user=self.vendeur)

        response = self.client.post(
            reverse('reservations-refuser', kwargs={'pk': reservation.pk}),
            {'motif': 'Stock indisponible'}, format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        reservation.refresh_from_db()
        self.assertEqual(reservation.validation_statut, Reservation.ValidationStatut.REFUSEE)
        self.assertEqual(reservation.statut, Reservation.Statut.ANNULEE)
        self.assertEqual(reservation.motif_refus, 'Stock indisponible')
        self.assertEqual(reservation.validation_par, self.vendeur)

    def test_client_ne_peut_pas_valider_et_commande_en_attente_ne_peut_pas_etre_encaissee(self):
        reservation = self._creer_commande()
        self.client.force_authenticate(user=self.client_user)

        response = self.client.post(
            reverse('reservations-valider', kwargs={'pk': reservation.pk}),
            {}, format='json',
        )

        self.assertIn(response.status_code, (401, 403))

    def test_commande_non_validee_ne_peut_pas_etre_encaissee(self):
        reservation = self._creer_commande()

        with self.assertRaises(ValidationError) as erreur:
            ReservationService.encaisser(
                reservation.pk,
                mode_paiement='ESPECES',
                utilisateur=self.vendeur,
            )

        self.assertIn('validation_statut', erreur.exception.detail)


@override_settings(MAILERS={
    'default': {'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'},
})
class FactureCommandeTests(APITestCase):
    """Facture d'une commande validée : lien signé, document HTML, e-mail client."""

    def setUp(self):
        self.produit = Produit.objects.create(
            nom='Cuvée facture', type_vin='Rouge', marque='Domaine',
            cout_revenir=Decimal('5000.00'), prix_vente=Decimal('10000.00'),
            statut=True,
        )
        Stock.objects.update_or_create(
            produit=self.produit, defaults={'quantite': 20, 'seuil_alerte': 2},
        )
        self.vendeur = User.objects.create_user(
            username='vendeur-facture', password='password123', role=User.Role.VENDEUR,
        )
        self.client_user = User.objects.create_user(
            username='client-facture', email='client-facture@test.com',
            password='password123', role=User.Role.CLIENT,
        )
        self.payload = {
            'nom': 'Rakoto', 'prenom': 'Hanta', 'telephone': '0340000007',
            'email': 'client-facture@test.com', 'mode_reception': 'RETRAIT',
            'lignes': [{'produit_id': self.produit.pk, 'quantite': 2}],
        }

    def _valider(self, reservation):
        self.client.force_authenticate(user=self.vendeur)
        return self.client.post(
            reverse('reservations-valider', kwargs={'pk': reservation.pk}),
            {}, format='json',
        )

    def test_facture_url_vide_tant_que_la_commande_est_a_valider(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse('reservations-site'), self.payload, format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['data']['facture_url'], '')

    def test_facture_url_presente_apres_validation(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse('reservations-site'), self.payload, format='json',
        )
        reservation = Reservation.objects.get(reference=response.data['data']['reference'])

        reponse = self._valider(reservation)

        self.assertEqual(reponse.status_code, 200, reponse.data)
        url = reponse.data['data']['facture_url']
        self.assertTrue(url.startswith('http://testserver/'), url)
        self.assertIn(f'/api/reservations/{reservation.pk}/facture/?t=', url)

    def test_mes_commandes_porte_le_lien_facture(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse('reservations-site'), self.payload, format='json',
        )
        reservation = Reservation.objects.get(reference=response.data['data']['reference'])
        self._valider(reservation)

        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(reverse('reservations-mes-commandes'))

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['data'][0]['facture_url'])

    def test_le_document_facture_se_rend_sans_authentification(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse('reservations-site'), self.payload, format='json',
        )
        reservation = Reservation.objects.get(reference=response.data['data']['reference'])
        self._valider(reservation)

        document = self.client.get(facture_url(None, reservation))

        self.assertEqual(document.status_code, 200)
        html = document.content.decode()
        self.assertIn(reservation.reference, html)
        self.assertIn('Hanta', html)
        self.assertIn('Imprimer', html)
        self.assertIn('color:#000 !important', html)
        self.assertIn('.inv-brand .logo { display:none !important; }', html)

    def test_commande_non_validee_sans_facture(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse('reservations-site'), self.payload, format='json',
        )
        reservation = Reservation.objects.get(reference=response.data['data']['reference'])

        document = self.client.get(facture_url(None, reservation))

        self.assertEqual(document.status_code, 403)

    def test_jeton_absent_ou_d_une_autre_commande_rejete(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse('reservations-site'), self.payload, format='json',
        )
        reservation = Reservation.objects.get(reference=response.data['data']['reference'])
        self._valider(reservation)

        sans_jeton = self.client.get(f"/api/reservations/{reservation.pk}/facture/")
        self.assertEqual(sans_jeton.status_code, 403)

        autre = self.client.post(
            reverse('reservations-site'), {**self.payload, 'telephone': '0340000099'},
            format='json',
        )
        autre_reservation = Reservation.objects.get(reference=autre.data['data']['reference'])
        self._valider(autre_reservation)
        jeton_autre = urlparse(facture_url(None, autre_reservation)).query

        document = self.client.get(f"/api/reservations/{reservation.pk}/facture/?{jeton_autre}")
        self.assertEqual(document.status_code, 403)

    def test_validation_envoie_l_email_de_facture(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse('reservations-site'), self.payload, format='json',
        )
        reservation = Reservation.objects.get(reference=response.data['data']['reference'])

        with (
            mock.patch('apps.accounts.services.email_service._envoi_reel_autorise', return_value=True),
            mock.patch('apps.accounts.services.email_service._canaux_email', return_value=['smtp']),
        ):
            reponse = self._valider(reservation)

        self.assertEqual(reponse.status_code, 200, reponse.data)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['client-facture@test.com'])
        self.assertIn(reservation.reference, message.subject)
        self.assertIn(f'/api/reservations/{reservation.pk}/facture/?t=', message.body)
        contenus_html = [alt[1] for alt in message.alternatives]
        self.assertIn('text/html', contenus_html)

    def test_validation_sans_email_du_client_reste_valide(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            reverse('reservations-site'), self.payload, format='json',
        )
        reservation = Reservation.objects.get(reference=response.data['data']['reference'])
        reservation.client.email = ''
        reservation.client.save(update_fields=['email'])

        reponse = self._valider(reservation)

        self.assertEqual(reponse.status_code, 200, reponse.data)
        reservation.refresh_from_db()
        self.assertEqual(reservation.validation_statut, Reservation.ValidationStatut.VALIDEE)
