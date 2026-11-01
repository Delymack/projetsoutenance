import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import UserNotification
from apps.produits.models import Produit
from apps.stocks.models import Stock
from apps.ventes.models import MessageClient


class NotificationsPersistantesTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(
            username='notifications-admin',
            email='notifications-admin@test.com',
            password='password123',
        )
        self.produits = [
            Produit.objects.create(nom=f'Vin alerte {n}', volume='75 cl', prix_vente=15000)
            for n in (1, 2)
        ]
        for produit in self.produits:
            Stock.objects.update_or_create(
                produit=produit, defaults={'quantite': 0, 'seuil_alerte': 5},
            )
        self.url = reverse('notifications-action')

    def action(self, action, key=None):
        payload = {'action': action}
        if key is not None:
            payload['key'] = key
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_compteur_compte_les_alertes_non_lues_etat_persistant(self):
        self.client.force_login(self.user)
        page = self.client.get('/admin/')
        self.assertEqual(page.context['admin_notification_count'], 2)

        key = f'stock:rupture:{Stock.objects.get(produit=self.produits[0]).pk}'
        response = self.action('read', key)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 1)
        self.assertEqual(UserNotification.objects.get(user=self.user, key=key).etat, UserNotification.Etat.LUE)

        page = self.client.get('/admin/')
        self.assertEqual(page.context['admin_notification_count'], 1)
        self.assertContains(page, 'Marquer comme non lue')

    def test_masquer_supprime_de_la_liste_et_ne_reapparait_pas(self):
        self.client.force_login(self.user)
        masquee = f'stock:rupture:{Stock.objects.get(produit=self.produits[0]).pk}'
        restante = f'stock:rupture:{Stock.objects.get(produit=self.produits[1]).pk}'

        response = self.action('dismiss', masquee)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 1)
        self.assertEqual(
            UserNotification.objects.get(user=self.user, key=masquee).etat,
            UserNotification.Etat.MASQUEE,
        )
        page = self.client.get('/admin/')
        html = page.content.decode('utf-8')
        # La notification masquée a quitté la cloche : sa clé n'apparaît plus,
        # l'autre reste. (Le nom du produit peut, lui, être affiché ailleurs sur
        # le tableau de bord — d'où le contrôle par clé, et non par nom.)
        self.assertNotIn(f'data-notification-key="{masquee}"', html)
        self.assertIn(f'data-notification-key="{restante}"', html)
        self.assertEqual(page.context['admin_notification_count'], 1)

    def test_tout_marquer_comme_lu_met_le_compteur_a_zero(self):
        self.client.force_login(self.user)

        response = self.action('read_all')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 0)
        self.assertEqual(
            UserNotification.objects.filter(user=self.user, etat=UserNotification.Etat.LUE).count(),
            2,
        )

    def test_nouveau_message_affiche_une_action_directe_pour_repondre(self):
        message = MessageClient.objects.create(
            nom='Miora',
            email='miora@example.test',
            sujet='Disponibilité',
            message='Avez-vous ce vin en carton ?',
        )
        self.client.force_login(self.user)

        page = self.client.get('/admin/')

        self.assertContains(page, f'Nouveau message client : {message.sujet}')
        self.assertContains(page, 'wine-notification-reply')
        self.assertContains(
            page,
            reverse('admin:ventes_messageclient_change', args=[message.pk]),
        )
        self.assertEqual(page.context['admin_notification_count'], 3)

    def test_clic_sur_notification_ouvre_fiche_de_reponse_et_marque_comme_lue(self):
        message = MessageClient.objects.create(
            nom='Miora',
            email='miora@example.test',
            sujet='Disponibilité',
            message='Avez-vous ce vin en carton ?',
        )
        self.client.force_login(self.user)
        url = reverse('admin:ventes_messageclient_change', args=[message.pk])

        page = self.client.get(f'{url}?repondre=1')

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'wine-message-hero')
        self.assertContains(page, 'wine-message-original-text')
        self.assertContains(page, 'data-message-reply="true"')
        self.assertContains(page, 'Rédigez une réponse claire et personnalisée au client')
        self.assertContains(page, 'wine-message-send-button')
        self.assertContains(page, 'Envoyer la réponse')
        self.assertContains(page, 'field.scrollIntoView')
        self.assertNotContains(page, 'Coordonnées du client')
        self.assertNotContains(page, 'field-repondu_le')
        self.assertNotContains(page, 'field-statut')
        self.assertEqual(
            UserNotification.objects.get(
                user=self.user, key=f'message-client:{message.pk}',
            ).etat,
            UserNotification.Etat.LUE,
        )

    def test_actualisation_recupere_les_nouveaux_messages_et_leur_action(self):
        message = MessageClient.objects.create(
            nom='Miora',
            telephone='0340000000',
            sujet='Disponibilité',
            message='Avez-vous ce vin en carton ?',
        )
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['unread_count'], 3)
        notification = next(
            item for item in payload['items']
            if item['key'] == f'message-client:{message.pk}'
        )
        self.assertEqual(notification['action_label'], 'Répondre')
        self.assertIn(
            f"{reverse('admin:ventes_messageclient_change', args=[message.pk])}?repondre=1",
            notification['url'],
        )

    def test_action_refuse_un_utilisateur_non_staff(self):
        User = get_user_model()
        vendeur = User.objects.create_user(
            username='notifications-vendeur',
            email='notifications-vendeur@test.com',
            password='password123',
        )
        self.client.force_login(vendeur)

        response = self.action('read', 'stock:rupture:1')

        self.assertEqual(response.status_code, 403)

    def test_action_refuse_une_cle_inconnue(self):
        self.client.force_login(self.user)

        response = self.action('read', 'stock:rupture:999999')

        self.assertEqual(response.status_code, 404)

    def test_action_mal_formee_est_rejetee_sans_erreur_serveur(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            data=json.dumps({'action': ['read']}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'Action invalide.'})
