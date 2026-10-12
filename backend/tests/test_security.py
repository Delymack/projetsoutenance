"""Tests des fonctionnalités d'authentification avancées.

Inscription locale avec vérification d'e-mail (OTP), mot de passe oublié,
lien magique, double authentification (TOTP + codes de secours) et
verrouillage après échecs répétés — en API (JSON) et en pages (HTML).
"""
import re

from django.contrib.auth import authenticate
from django.contrib.sessions.models import Session
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import LoginEvent, User
from apps.accounts.services import (
    is_locked,
    totp_current_code,
)

EMAILS = {
    'MAILERS': {
        'default': {
            'BACKEND': 'django.core.mail.backends.locmem.EmailBackend',
        },
    },
}


def _otp_from_subject(subject):
    match = re.search(r'\b(\d{6})\b', subject)
    assert match, f'Aucun code à 6 chiffres dans le sujet : {subject!r}'
    return match.group(1)


def _link_from_body(body):
    match = re.search(r'http://testserver/admin/magic-link/(?P<token>[^/\s]+)/', body)
    assert match, f'Aucun lien magique dans le corps : {body!r}'
    return match.group('token')


@override_settings(**EMAILS)
class SignupWebTests(TestCase):
    PASSWORD = 'CabaneDuVerger!2024'

    def test_page_inscription_affichée(self):
        response = self.client.get('/admin/signup/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Créer un compte de vendeur')

    def test_inscription_puis_verification_email(self):
        response = self.client.post('/admin/signup/', {
            'username': 'newvendeur',
            'email': 'new@cave.tg',
            'first_name': 'Nina',
            'last_name': 'Dupont',
            'password1': self.PASSWORD,
            'password2': self.PASSWORD,
        })
        self.assertRedirects(response, '/admin/verify-email/?email=new@cave.tg')

        user = User.objects.get(email='new@cave.tg')
        self.assertFalse(user.is_active)
        # Sécurité : l'inscription ne délivre PAS l'accès admin (is_staff=False
        # par défaut). L'admin promeut manuellement les comptes.
        self.assertFalse(user.is_staff)
        self.assertEqual(user.role, User.Role.VENDEUR)
        self.assertEqual(len(mail.outbox), 1)

        code = _otp_from_subject(mail.outbox[0].subject)
        # NB: le code est à usage unique — on le soumet directement à la vue
        # qui le consomme, sans appeler verify_otp ici.
        response = self.client.post('/admin/verify-email/', {'email': 'new@cave.tg', 'code': code})
        target = response['Location']
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertIn('_auth_user_id', self.client.session)
        # Un compte non-staff est redirigé du back-office vers la page de connexion.
        self.assertEqual(target, '/admin/')
        follow = self.client.get(target)
        self.assertRedirects(follow, '/admin/login/?next=/admin/')

    def test_inscription_username_dupliqué_refusé(self):
        User.objects.create_user(username='garde', email='garde@cave.tg', password='x')
        response = self.client.post('/admin/signup/', {
            'username': 'garde', 'email': 'autre@cave.tg',
            'password1': self.PASSWORD, 'password2': self.PASSWORD,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'déjà pris')
        self.assertEqual(User.objects.count(), 1)

    def test_inscription_mots_de_passe_differents_refusé(self):
        response = self.client.post('/admin/signup/', {
            'username': 'xavier', 'email': 'x@cave.tg',
            'password1': self.PASSWORD, 'password2': 'AutreMotDePasse!42',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ne correspondent pas')

    @override_settings(SIGNUP_STAFF=True)
    def test_inscription_devient_staff_si_configuré(self):
        """Quand l'équipe active explicitement SIGNUP_STAFF, le compte est staff."""
        response = self.client.post('/admin/signup/', {
            'username': 'caissier', 'email': 'caissier@cave.tg',
            'first_name': 'Ida', 'last_name': 'Koffi',
            'password1': self.PASSWORD, 'password2': self.PASSWORD,
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email='caissier@cave.tg')
        self.assertEqual(user.is_staff, True)


@override_settings(**EMAILS)
class ForgotMagicTests(TestCase):
    PASSWORD = 'CabaneDuVerger!2024'

    def setUp(self):
        self.user = User.objects.create_user(
            username='aide', email='aide@cave.tg', password=self.PASSWORD,
            role=User.Role.VENDEUR, is_staff=True,
        )

    def test_mot_de_passe_oublie_et_reinitialisation(self):
        response = self.client.post('/admin/forgot-password/', {'email': 'aide@cave.tg'})
        self.assertRedirects(response, '/admin/reset-password/?email=aide@cave.tg')
        code = _otp_from_subject(mail.outbox[-1].subject)

        response = self.client.post('/admin/reset-password/', {
            'email': 'aide@cave.tg', 'code': code,
            'password1': 'NouveauMotDePasse!77', 'password2': 'NouveauMotDePasse!77',
        })
        self.assertRedirects(response, '/admin/message/?kind=password_ok')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NouveauMotDePasse!77'))

    def test_otp_non_consomme_par_code_erroné(self):
        """Un code erroné n'invalide pas le code légitime (ressaisie autorisée)."""
        from apps.accounts.services import verify_otp
        from django.core.cache import cache
        cache.delete('otp:sent:aide@cave.tg:reset')
        self.client.post('/admin/forgot-password/', {'email': 'aide@cave.tg'})
        code = _otp_from_subject(mail.outbox[-1].subject)

        self.assertFalse(verify_otp('aide@cave.tg', 'reset', '000000'))
        # Le même code reste valide après une seule erreur de saisie.
        self.assertTrue(verify_otp('aide@cave.tg', 'reset', code))

    def test_reinit_code_invalide_rejeté(self):
        response = self.client.post('/admin/reset-password/', {
            'email': 'aide@cave.tg', 'code': '000000',
            'password1': 'NouveauMotDePasse!77', 'password2': 'NouveauMotDePasse!77',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Code invalide')

    def test_lien_magique_connecte(self):
        response = self.client.post('/admin/magic-link/', {'email': 'aide@cave.tg'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Lien de connexion envoyé')

        token = _link_from_body(mail.outbox[-1].body)
        response = self.client.get(f'/admin/magic-link/{token}/')
        self.assertRedirects(response, '/admin/')
        self.assertIn('_auth_user_id', self.client.session)

    def test_lien_magique_usage_unique(self):
        self.client.post('/admin/magic-link/', {'email': 'aide@cave.tg'})
        token = _link_from_body(mail.outbox[-1].body)
        self.client.get(f'/admin/magic-link/{token}/')
        self.client.logout()
        response = self.client.get(f'/admin/magic-link/{token}/')
        self.assertContains(response, 'Lien invalide ou expiré')


@override_settings(**EMAILS)
class TwoFATests(TestCase):
    PASSWORD = 'CabaneDuVerger!2024'

    def setUp(self):
        self.user = User.objects.create_user(
            username='toto', email='toto@cave.tg', password=self.PASSWORD,
            role=User.Role.ADMIN, is_staff=True, is_superuser=True,
        )

    def _enable_2fa(self):
        self.client.force_login(self.user)
        response = self.client.get('/admin/2fa/enable/')
        self.assertEqual(response.status_code, 200)
        secret = self.client.session['totp_pending_secret']
        self.assertTrue(secret)
        code = totp_current_code(secret)
        response = self.client.post('/admin/2fa/enable/', {'code': code})
        self.user.refresh_from_db()
        self.assertTrue(self.user.totp_enabled)
        codes = self.client.session.get('recovery_codes_display') or []
        self.assertGreaterEqual(len(codes), 8)
        return codes

    def test_activation_2fa_et_login_exige_le_code(self):
        codes = self._enable_2fa()
        self.assertGreaterEqual(len(codes), 8)

        self.client.logout()
        response = self.client.post('/admin/login/', {
            'username': 'toto', 'password': self.PASSWORD,
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1][0], '/admin/2fa/verify/')
        self.assertContains(response, 'Code de double authentification')

        # Sans code, on reste bloqué sur la vérification.
        response = self.client.post('/admin/2fa/verify/', {'code': '000000'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Code invalide')

        # Avec le bon code TOTP, on accède enfin au back-office.
        secret = self.user.totp_secret
        from apps.accounts.services import unobfuscate_totp_secret
        code = totp_current_code(unobfuscate_totp_secret(secret))
        response = self.client.post('/admin/2fa/verify/', {'code': code}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.session.get('twofa_pending'))
        self.assertEqual(response.redirect_chain[-1][0], '/admin/')

    def test_code_de_secours_utilisable_une_fois(self):
        codes = self._enable_2fa()
        recovery = codes[0]

        self.client.logout()
        self.client.post('/admin/login/', {'username': 'toto', 'password': self.PASSWORD})
        response = self.client.post('/admin/2fa/verify/', {'action': 'recovery', 'code': recovery}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1][0], '/admin/')
        self.user.refresh_from_db()
        self.assertEqual(len([c for c in self.user.recovery_codes.split(',') if c]), len(codes) - 1)

        # Réutiliser le même code de secours doit échouer.
        self.client.logout()
        self.client.post('/admin/login/', {'username': 'toto', 'password': self.PASSWORD})
        response = self.client.post('/admin/2fa/verify/', {'action': 'recovery', 'code': recovery})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Code invalide')

    def test_desactivation_2fa_exige_le_mdp(self):
        self._enable_2fa()
        response = self.client.post('/admin/2fa/disable/', {'password': 'mauvais'})
        self.assertContains(response, 'Mot de passe incorrect')
        self.user.refresh_from_db()
        self.assertTrue(self.user.totp_enabled)

        response = self.client.post('/admin/2fa/disable/', {'password': self.PASSWORD})
        self.assertRedirects(response, '/admin/message/?kind=2fa_disabled')
        self.user.refresh_from_db()
        self.assertFalse(self.user.totp_enabled)

    def test_verification_2fa_verrouillé_après_echecs(self):
        """Anti brute-force : impossible de tester des codes sans fin sur la page 2FA."""
        from apps.accounts.services import totp_locked
        self._enable_2fa()
        self.client.logout()
        self.client.post('/admin/login/', {'username': 'toto', 'password': self.PASSWORD})

        for _ in range(5):
            response = self.client.post('/admin/2fa/verify/', {'code': '000000'})
        self.assertGreater(totp_locked(self.user.username), 0)

        # Même le bon code est refusé pendant le verrouillage.
        secret = self.user.totp_secret
        from apps.accounts.services import unobfuscate_totp_secret
        code = totp_current_code(unobfuscate_totp_secret(secret))
        response = self.client.post('/admin/2fa/verify/', {'code': code}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.client.session.get('twofa_pending'))


@override_settings(**EMAILS)
class LockoutTests(TestCase):

    def test_verrouillage_apres_echecs_repetes(self):
        User.objects.create_user(username='serge', email='serge@cave.tg', password='MotDePasse!42')
        for _ in range(5):
            self.assertIsNone(authenticate(username='serge', password='mauvais'))
        # Même le bon mot de passe est refusé pendant le verrouillage.
        self.assertIsNone(authenticate(username='serge', password='MotDePasse!42'))
        self.assertGreater(is_locked('serge'), 0)

    def test_compte_se_deverrouille_apres_succes(self):
        User.objects.create_user(username='mario', email='mario@cave.tg', password='MotDePasse!42')
        authenticate(username='mario', password='mauvais')
        user = authenticate(username='mario', password='MotDePasse!42')
        self.assertIsNotNone(user)
        self.assertEqual(is_locked('mario'), 0)

    def test_login_desactif_n_enregistre_pas_de_succes(self):
        user = User.objects.create_user(username='gaston', email='gaston@cave.tg', password='MotDePasse!42')
        user.is_active = False
        user.save()
        for _ in range(5):
            self.assertIsNone(authenticate(username='gaston', password='MotDePasse!42'))
        # Compte inactif : même le bon mot de passe est refusé et verrouillable.
        self.assertGreater(is_locked('gaston'), 0)

    def test_verrouillage_non_prolongé_pendant_le_blocage(self):
        """Anti-DoS : les tentatives pendant le verrouillage ne le repoussent pas."""
        from apps.accounts.services import record_failed_attempt
        User.objects.create_user(username='antidos', email='antidos@cave.tg', password='x')
        ok, _ = record_failed_attempt('antidos')   # 1ère tentative
        for _ in range(4):
            record_failed_attempt('antidos')
        locked, until = record_failed_attempt('antidos')
        self.assertTrue(locked)
        # Le verrouillage n'est plus prolongé par de nouvelles attaques.
        _, until2 = record_failed_attempt('antidos')
        self.assertEqual(until, until2)


@override_settings(**EMAILS)
class ApiAuthTests(APITestCase):
    PASSWORD = 'CabaneDuVerger!2024'

    def test_register_et_verify_api(self):
        response = self.client.post('/api/auth/register/', {
            'username': 'api_u', 'email': 'api@cave.tg', 'password': self.PASSWORD,
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)

        code = _otp_from_subject(mail.outbox[0].subject)
        response = self.client.post('/api/auth/register/verify/', {
            'email': 'api@cave.tg', 'code': code,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        user = User.objects.get(email='api@cave.tg')
        self.assertTrue(user.is_active)

    def test_register_verify_mauvais_code(self):
        self.client.post('/api/auth/register/', {
            'username': 'api_b', 'email': 'apib@cave.tg', 'password': self.PASSWORD,
        })
        response = self.client.post('/api/auth/register/verify/', {
            'email': 'apib@cave.tg', 'code': '123456',
        })
        self.assertEqual(response.status_code, 400)

    def test_forgot_reset_api(self):
        User.objects.create_user(username='clem', email='clem@cave.tg', password=self.PASSWORD)
        response = self.client.post('/api/auth/forgot/', {'email': 'clem@cave.tg'})
        self.assertEqual(response.status_code, 200)
        code = _otp_from_subject(mail.outbox[-1].subject)
        response = self.client.post('/api/auth/reset/', {
            'email': 'clem@cave.tg', 'code': code, 'password': 'NouveauPass!42',
        })
        self.assertEqual(response.status_code, 200)
        clem = User.objects.get(email='clem@cave.tg')
        self.assertTrue(clem.check_password('NouveauPass!42'))

    def test_login_jwt_exige_2fa_si_activee(self):
        User.objects.create_user(username='api2', email='api2@cave.tg', password=self.PASSWORD)
        response = self.client.post('/api/auth/login/', {
            'username': 'api2', 'password': self.PASSWORD,
        })
        self.assertEqual(response.status_code, 200)

        from apps.accounts.services import obfuscate_totp_secret
        user = User.objects.get(username='api2')
        secret = 'JBSWY3DPEHPK3PXP'
        user.totp_enabled = True
        user.totp_secret = obfuscate_totp_secret(secret)
        user.save()

        response = self.client.post('/api/auth/login/', {
            'username': 'api2', 'password': self.PASSWORD,
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'double authentification', status_code=400)

        response = self.client.post('/api/auth/login/', {
            'username': 'api2', 'password': self.PASSWORD, 'totp': totp_current_code(secret),
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)

    def test_totp_bruteforce_bloque_apres_5_echecs(self):
        from apps.accounts.services import obfuscate_totp_secret, totp_locked
        User.objects.create_user(username='api3', email='api3@cave.tg', password=self.PASSWORD)
        user = User.objects.get(username='api3')
        secret = 'JBSWY3DPEHPK3PXP'
        user.totp_enabled = True
        user.totp_secret = obfuscate_totp_secret(secret)
        user.save()

        for _ in range(5):
            response = self.client.post('/api/auth/login/', {
                'username': 'api3', 'password': self.PASSWORD, 'totp': '000000',
            })
            self.assertEqual(response.status_code, 400)

        self.assertGreater(totp_locked(user.username), 0)

        # Même avec le bon mot de passe ET le bon code TOTP, c'est bloqué.
        response = self.client.post('/api/auth/login/', {
            'username': 'api3', 'password': self.PASSWORD, 'totp': totp_current_code(secret),
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Trop de tentatives', status_code=400)

    def test_totp_verrouillage_reinitialise_apres_succes(self):
        from apps.accounts.services import obfuscate_totp_secret, totp_locked
        User.objects.create_user(username='api4', email='api4@cave.tg', password=self.PASSWORD)
        user = User.objects.get(username='api4')
        secret = 'JBSWY3DPEHPK3PXP'
        user.totp_enabled = True
        user.totp_secret = obfuscate_totp_secret(secret)
        user.save()

        for _ in range(4):
            self.client.post('/api/auth/login/', {
                'username': 'api4', 'password': self.PASSWORD, 'totp': '000000',
            })

        response = self.client.post('/api/auth/login/', {
            'username': 'api4', 'password': self.PASSWORD, 'totp': totp_current_code(secret),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(totp_locked(user.username), 0)


@override_settings(**EMAILS)
class AccountSecurityTests(TestCase):
    PASSWORD = 'CabaneDuVerger!2024'

    def setUp(self):
        self.user = User.objects.create_user(
            username='secur', email='secur@cave.tg', password=self.PASSWORD,
            role=User.Role.ADMIN, is_staff=True, is_superuser=True,
        )

    def test_connexion_enregistre_evenement(self):
        self.assertEqual(LoginEvent.objects.filter(user=self.user).count(), 0)
        self.client.post('/admin/login/', {'username': 'secur', 'password': self.PASSWORD})
        self.assertEqual(LoginEvent.objects.filter(user=self.user, statut='SUCCESS').count(), 1)

    def test_page_securite_sessions_actives(self):
        self.client.force_login(self.user)
        response = self.client.get('/admin/account/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sessions actives')

    def test_deconnexion_autres_sessions(self):
        self.client.post('/admin/login/', {'username': 'secur', 'password': self.PASSWORD})
        current = self.client.session.session_key
        self.client.post('/admin/account/logout-others/')
        remaining = Session.objects.filter(expire_date__gt=timezone.now())
        active = [s for s in remaining if str(s.get_decoded().get('_auth_user_id', '')) == str(self.user.pk)]
        self.assertTrue(any(s.session_key == current for s in active))
        self.assertLessEqual(len(active), 1)