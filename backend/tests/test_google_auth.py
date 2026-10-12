"""Tests de l'authentification « Continuer avec Google ».

Couvre :
  * la liste blanche d'emails / domaines (adapter + API JWT) ;
  * le provisionnement des comptes créés via Google (vendeur, avatar, non-staff) ;
  * l'accès admin réservé (GOOGLE_STAFF, désactivé par défaut) ;
  * la liaison au compte existant par adresse email ;
  * le bouton Google sur la page de connexion ;
  * le flux OAuth (redirection vers Google) et l'endpoint /api/auth/google/.
"""
from unittest.mock import patch

from django.conf import settings
from django.test import Client, TestCase, override_settings

from apps.accounts.adapters import _email_of, GoogleSocialAdapter
from apps.accounts.models import User
from apps.accounts.views_google import google_user_from_claims

PROVIDERS = {
    'google': {
        'APP': {
            'client_id': 'fake-id-456.apps.googleusercontent.com',
            'secret': 'fake-secret',
            'key': '',
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    }
}

CLAIMS = {
    'aud': 'fake-id-456.apps.googleusercontent.com',
    'iss': 'accounts.google.com',
    'sub': 'google-uid-123',
    'email': 'caissier@cave.tg',
    'email_verified': True,
    'given_name': 'Océane',
    'family_name': 'Martin',
    'picture': 'https://lh3.googleusercontent.com/a/photo',
}


def _override_google(**kw):
    kw.setdefault('SOCIALACCOUNT_PROVIDERS', PROVIDERS)
    kw.setdefault('SOCIALACCOUNT_LOGIN_ON_GET', True)
    bezout = dict(kw)
    return override_settings(**bezout)


class GoogleAdapterTests(TestCase):
    def setUp(self):
        User.objects.create_user(
            username='vendeur',
            email='vendeur@cave.tg',
            password='Secret123!',
            role=User.Role.VENDEUR,
        )

    @override_settings(GOOGLE_ALLOWED_DOMAINS=['cave.tg'], GOOGLE_ALLOWED_EMAILS=['ceo@autre.tg'])
    def test_allowed_email_suivant_restrictions(self):
        adapter = GoogleSocialAdapter()
        self.assertTrue(adapter.has_restrictions())
        self.assertTrue(adapter.is_allowed_email('caissier@cave.tg'))
        self.assertTrue(adapter.is_allowed_email('CEO@autre.tg'))
        self.assertFalse(adapter.is_allowed_email('pirate@gmail.com'))
        self.assertFalse(adapter.is_allowed_email(''))

    @override_settings(GOOGLE_ALLOWED_DOMAINS=[], GOOGLE_ALLOWED_EMAILS=[])
    def test_sans_restriction_toute_adresse_valide(self):
        adapter = GoogleSocialAdapter()
        self.assertFalse(adapter.has_restrictions())
        self.assertTrue(adapter.is_allowed_email('nimporte.qui@gmail.com'))

    @override_settings(GOOGLE_ALLOWED_DOMAINS=['cave.tg'])
    def test_pas_de_creation_pour_adresse_inconnue(self):
        from allauth.socialaccount.models import SocialLogin, SocialAccount
        fake = {'email': 'pirate@gmail.com', 'email_verified': True}
        account = SocialAccount(provider='google', extra_data=fake)
        login = SocialLogin(account=account)

        adapter = GoogleSocialAdapter()
        self.assertFalse(adapter.is_open_for_signup(None, login))
        self.assertEqual(_email_of(login), 'pirate@gmail.com')

    @override_settings(GOOGLE_ALLOWED_DOMAINS=['cave.tg'])
    def test_existant_lié_sans_creation(self):
        from allauth.socialaccount.models import SocialLogin, SocialAccount
        fake = {'email': 'vendeur@cave.tg', 'email_verified': True}
        account = SocialAccount(provider='google', extra_data=fake)
        login = SocialLogin(account=account)

        adapter = GoogleSocialAdapter()
        self.assertTrue(adapter.is_open_for_signup(None, login))
        adapter.pre_social_login(None, login)
        self.assertEqual(login.user.email, 'vendeur@cave.tg')


class GoogleAdminLoginTests(TestCase):
    def setUp(self):
        settings.ALLOWED_HOSTS.append('testserver')

    def _login_page(self):
        return self.client.get('/admin/login/')

    def test_bouton_masqué_sans_client_id(self):
        with override_settings(GOOGLE_OAUTH2_CLIENT_ID=''):
            response = self._login_page()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Continuer avec Google')

    def test_bouton_google_absent_du_formulaire_de_connexion_minimal(self):
        with _override_google(GOOGLE_OAUTH2_CLIENT_ID='fake-id-456.apps.googleusercontent.com'):
            response = self._login_page()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'btn-google')
        self.assertNotContains(response, 'Continuer avec Google')

    def test_inscription_locale_désactivée(self):
        response = self.client.get('/accounts/signup/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/admin/login/')


class GoogleOAuthFlowTests(TestCase):
    def setUp(self):
        settings.ALLOWED_HOSTS.append('testserver')

    def test_redirection_vers_compte_google(self):
        with _override_google():
            response = self.client.get('/accounts/google/login/?process=login&next=/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('https://accounts.google.com/o/oauth2'))


class GoogleAuthApiTests(TestCase):
    def setUp(self):
        self.url = '/api/auth/google/'
        self.client = Client()
        settings.ALLOWED_HOSTS.append('testserver')

    def _post(self, id_token=None):
        return self.client.post(self.url, {'id_token': id_token or 'fake-token'}, content_type='application/json')

    @override_settings(GOOGLE_OAUTH2_CLIENT_ID='')
    def test_non_configuré_renvoie_503(self):
        response = self._post()
        self.assertEqual(response.status_code, 503)
        self.assertIn('detail', response.json())

    @override_settings(GOOGLE_OAUTH2_CLIENT_ID='fake-id-456.apps.googleusercontent.com')
    def test_jeton_invalide_renvoie_401(self):
        with patch('apps.accounts.views_google.verify_google_id_token', return_value=None):
            response = self._post()
        self.assertEqual(response.status_code, 401)

    @override_settings(
        GOOGLE_OAUTH2_CLIENT_ID='fake-id-456.apps.googleusercontent.com',
        GOOGLE_ALLOWED_DOMAINS=['cave.tg'],
    )
    def test_creation_premier_login(self):
        with patch('apps.accounts.views_google.verify_google_id_token', return_value=CLAIMS):
            response = self._post()
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('access', payload)
        self.assertIn('refresh', payload)
        user = User.objects.get(email='caissier@cave.tg')
        # Sécurité : les comptes Google ne reçoivent AUCUN accès admin par défaut.
        self.assertFalse(user.is_staff)
        self.assertEqual(user.role, User.Role.VENDEUR)
        self.assertEqual(user.avatar_url, CLAIMS['picture'])
        self.assertEqual(user.google_uid, 'google-uid-123')
        self.assertEqual(payload['user']['email'], 'caissier@cave.tg')

    @override_settings(
        GOOGLE_OAUTH2_CLIENT_ID='fake-id-456.apps.googleusercontent.com',
        GOOGLE_ALLOWED_DOMAINS=['cave.tg'],
    )
    def test_second_login_lie_au_meme_compte(self):
        with patch('apps.accounts.views_google.verify_google_id_token', return_value=CLAIMS):
            self._post()
            response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(email='caissier@cave.tg').count(), 1)

    @override_settings(
        GOOGLE_OAUTH2_CLIENT_ID='fake-id-456.apps.googleusercontent.com',
        GOOGLE_ALLOWED_DOMAINS=['cave.tg'],
        GOOGLE_STAFF=True,
    )
    def test_google_staff_quand_explicitement_configuré(self):
        with patch('apps.accounts.views_google.verify_google_id_token', return_value=CLAIMS):
            response = self._post()
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email='caissier@cave.tg')
        self.assertTrue(user.is_staff)

    @override_settings(
        GOOGLE_OAUTH2_CLIENT_ID='fake-id-456.apps.googleusercontent.com',
        GOOGLE_ALLOWED_DOMAINS=['cave.tg'],
    )
    def test_email_deja_connu_conserve_son_role(self):
        User.objects.create_user(
            username='vendeur',
            email='vendeur@cave.tg',
            password='Secret123!',
            role=User.Role.VENDEUR,
        )
        claims = dict(CLAIMS, email='vendeur@cave.tg', sub='google-uid-999')
        with patch('apps.accounts.views_google.verify_google_id_token', return_value=claims):
            response = self._post()
        self.assertEqual(response.status_code, 200)
        vendeur = User.objects.get(email='vendeur@cave.tg')
        self.assertEqual(vendeur.google_uid, 'google-uid-999')
        # Un compte existant déjà non-staff le reste (aucune élévation).
        self.assertFalse(vendeur.is_staff)

    @override_settings(
        GOOGLE_OAUTH2_CLIENT_ID='fake-id-456.apps.googleusercontent.com',
        GOOGLE_ALLOWED_DOMAINS=['cave.tg'],
    )
    def test_email_non_autorise_refuse_la_creation(self):
        hostile = dict(CLAIMS, email='pirate@gmail.com')
        with patch('apps.accounts.views_google.verify_google_id_token', return_value=hostile):
            response = self._post()
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email='pirate@gmail.com').exists())

    @override_settings(
        GOOGLE_OAUTH2_CLIENT_ID='fake-id-456.apps.googleusercontent.com',
        GOOGLE_ALLOWED_DOMAINS=['cave.tg'],
    )
    def test_email_deja_connu_accepte_hors_liste(self):
        User.objects.create_user(
            username='vendeur',
            email='vendeur@cave.tg',
            password='Secret123!',
            role=User.Role.VENDEUR,
            is_staff=True,
        )
        claims = dict(CLAIMS, email='vendeur@cave.tg', sub='google-uid-999')
        with patch('apps.accounts.views_google.verify_google_id_token', return_value=claims):
            response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(email='vendeur@cave.tg').count(), 1)
        vendeur = User.objects.get(email='vendeur@cave.tg')
        self.assertEqual(vendeur.google_uid, 'google-uid-999')
        self.assertTrue(vendeur.is_staff)


class GoogleUserFromClaimsTests(TestCase):
    @override_settings(GOOGLE_ALLOWED_DOMAINS=['cave.tg'])
    def test_username_unique_généré(self):
        User.objects.create_user(username='ocane', email='autre@cave.tg', password='x')
        claims = dict(CLAIMS, email='océane@cave.tg', sub='s1')
        user = google_user_from_claims(claims)
        self.assertTrue(user.username)
        self.assertNotEqual(user.username, 'ocane')
        self.assertEqual(User.objects.filter(username=user.username).count(), 1)