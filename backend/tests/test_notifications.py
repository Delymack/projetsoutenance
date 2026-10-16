import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import UserNotification
from apps.produits.models import Produit
from apps.stocks.models import Stock


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
