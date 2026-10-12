from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from apps.accounts.models import User

class TestSMSAdminViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin-sms', email='admin-sms@test.com', password='MotDePasse123',
        )
        self.client.force_login(self.admin)
        self.url = reverse('admin:test-envoi-sms')

    def test_get_page_ok(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Tester l'envoi de SMS")

    def test_post_numero_local_se_reveille_sans_500(self):
        # Numéro local 10 chiffres -> converti en E.164 par le service.
        r = self.client.post(self.url, {'telephone': '0340000001', 'purpose': 'signup'})
        self.assertEqual(r.status_code, 200, r.content[:500])

    def test_admin_requis(self):
        self.client.logout()
        r = self.client.get(self.url)
        self.assertIn(r.status_code, (302, 403))

    def test_prefill_telephone_via_query_string(self):
        r = self.client.get(self.url, {'telephone': '0340000099'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '0340000099')

    def test_action_user_redirige_vers_test_sms_prefill(self):
        u = User.objects.create_user(
            username='client-action', password='x', role=User.Role.CLIENT,
            telephone='0340000099',
        )
        resp = self.client.post(
            reverse('admin:accounts_user_changelist'),
            {'action': 'envoyer_sms_test', '_selected_action': [str(u.pk)]},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn('test-sms', resp.url)
        self.assertIn('telephone=0340000099', resp.url)

    def test_action_user_sans_telephone_affiche_erreur(self):
        u = User.objects.create_user(
            username='client-sans-tel', password='x', role=User.Role.CLIENT,
        )
        resp = self.client.post(
            reverse('admin:accounts_user_changelist'),
            {'action': 'envoyer_sms_test', '_selected_action': [str(u.pk)]},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        messages = [str(m) for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any('téléphone' in m for m in messages), messages)
