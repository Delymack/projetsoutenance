from django.contrib import admin
from django.test import RequestFactory, TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.ventes.admin import MessageClientAdmin
from apps.ventes.models import MessageClient


class ReservationSiteApiTests(TestCase):
    def test_public_reservation_endpoint_validates_anonymous_payload(self):
        response = APIClient().post(
            '/api/reservations/site/',
            {'lignes': []},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data['success'])
        self.assertIn('nom', response.data['errors'])


class ContactMessageApiTests(TestCase):
    def test_public_message_is_saved_and_acknowledged(self):
        response = APIClient().post(
            '/api/contact/messages/',
            {
                'nom': '  Mila  ',
                'email': 'mila@example.test',
                'sujet': '  Une question  ',
                'message': '  Bonjour, pouvez-vous me conseiller ?  ',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['message'], 'Votre message a bien été reçu.')
        message = MessageClient.objects.get()
        self.assertEqual(message.nom, 'Mila')
        self.assertEqual(message.sujet, 'Une question')
        self.assertEqual(message.statut, MessageClient.Statut.NOUVEAU)

    def test_public_message_requires_a_reply_contact(self):
        response = APIClient().post(
            '/api/contact/messages/',
            {
                'nom': 'Mila',
                'sujet': 'Une question',
                'message': 'Bonjour, pouvez-vous me conseiller ?',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data['success'])
        self.assertIn('contact', response.data['errors'])
        self.assertFalse(MessageClient.objects.exists())

    def test_client_can_read_only_own_messages_and_send_account_message(self):
        client_account = User.objects.create_user(
            username='client-message',
            password='test-password',
            role=User.Role.CLIENT,
            email='client@example.test',
        )
        other_account = User.objects.create_user(
            username='other-message',
            password='test-password',
            role=User.Role.CLIENT,
            email='other@example.test',
        )
        own_message = MessageClient.objects.create(
            nom='Client',
            email='client@example.test',
            sujet='Question',
            message='Question envoyée',
            compte_client=client_account,
            reponse='Réponse du vendeur',
        )
        MessageClient.objects.create(
            nom='Autre',
            email='other@example.test',
            sujet='Privé',
            message='Message privé',
            compte_client=other_account,
        )
        api = APIClient()
        api.force_authenticate(user=client_account)

        response = api.get('/api/contact/messages/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['id'] for item in response.data['data']], [own_message.pk])
        self.assertEqual(response.data['data'][0]['reponse'], 'Réponse du vendeur')

        sent = api.post(
            '/api/contact/messages/',
            {
                'nom': 'Client',
                'email': 'client@example.test',
                'sujet': 'Nouvelle question',
                'message': 'Mon message depuis mon compte',
            },
            format='json',
        )
        self.assertEqual(sent.status_code, 201)
        self.assertEqual(
            MessageClient.objects.get(pk=sent.data['data']['id']).compte_client,
            client_account,
        )

    def test_anonymous_client_cannot_read_inbox(self):
        response = APIClient().get('/api/contact/messages/')
        self.assertEqual(response.status_code, 401)

    def test_backoffice_reply_marks_message_as_handled(self):
        message = MessageClient.objects.create(
            nom='Client',
            email='client@example.test',
            sujet='Question',
            message='Question envoyée',
        )
        message.reponse = 'Voici notre réponse.'
        admin_view = MessageClientAdmin(MessageClient, admin.site)

        admin_view.save_model(
            RequestFactory().post('/admin/'),
            message,
            type('Formulaire', (), {'changed_data': ['reponse']})(),
            change=True,
        )

        message.refresh_from_db()
        self.assertEqual(message.statut, MessageClient.Statut.TRAITE)
        self.assertIsNotNone(message.repondu_le)
