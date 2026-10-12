"""Flux OTP e-mail / SMS : normalisation du contact, profil renvoyé, rôle client.

Le bug historique : l'envoi stocke `contact` normalisé (`+261…` / e-mail en
minuscules) alors que la vérification cherchait le contact brut saisi — le code
juste était rejeté. Ces tests verrouillent la forme canonique des trois
endpoints (send-code, verify, resend-code).
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User, VerificationCode


class OtpSignupTests(APITestCase):
    """Inscription par code SMS puis par code e-mail."""

    def setUp(self):
        self.send_url = reverse('signup-send-code')
        self.verify_url = reverse('signup-verify')

    def _demander_code(self, **kwargs):
        payload = {'nom': 'Rakoto Jean', 'password': 'MotDePasse123', 'contact_type': 'sms'}
        payload.update(kwargs)
        reponse = self.client.post(self.send_url, payload)
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        vc = VerificationCode.objects.get(
            purpose=VerificationCode.PURPOSE_SIGNUP, is_used=False
        )
        vc.set_code('123456')
        return vc

    def test_signup_verify_accepte_toutes_formes_du_contact(self):
        """Le contact saisi peut prendre n'importe quelle forme : code trouvé."""
        vc = self._demander_code(telephone='341234567')
        self.assertEqual(vc.contact, '+261341234567')
        vc = self._demander_code(telephone='341234567')
        for forme in ('341234567', '261341234567', '+261341234567'):
            vc.is_used = False
            vc.attempts = 0
            vc.save(update_fields=['is_used', 'attempts'])
            vc.set_code('123456')

            reponse = self.client.post(
                self.verify_url, {'contact': forme, 'code': '123456'}
            )
            self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
            # Nettoie le compte créé pour itérer proprement.
            User.objects.all().delete()
            VerificationCode.objects.all().delete()
            vc = self._demander_code(telephone='341234567')

    def test_signup_verify_renvoie_profil_et_role_client(self):
        self._demander_code(telephone='341234567')
        reponse = self.client.post(
            self.verify_url, {'contact': '261341234567', 'code': '123456'}
        )
        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        self.assertIn('access', reponse.data)
        self.assertIn('refresh', reponse.data)

        profil = reponse.data.get('user')
        self.assertIsNotNone(profil, 'La vérification doit renvoyer le profil utilisateur.')
        self.assertEqual(profil['role'], User.Role.CLIENT)
        self.assertEqual(profil['telephone'], '+261341234567')
        self.assertEqual(profil['first_name'], 'Rakoto')
        self.assertEqual(profil['last_name'], 'Jean')

        compte = User.objects.get(username='+261341234567')
        self.assertEqual(compte.role, User.Role.CLIENT)

    def test_signup_verify_code_faux(self):
        self._demander_code(telephone='341234567')
        reponse = self.client.post(
            self.verify_url, {'contact': '341234567', 'code': '000000'}
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('tentatives', reponse.data['error'])

    def test_signup_email_normalise(self):
        self._demander_code(
            email='Client@Example.com', contact_type='email', telephone=''
        )
        vc = VerificationCode.objects.get(purpose=VerificationCode.PURPOSE_SIGNUP)
        self.assertEqual(vc.contact, 'client@example.com')

        reponse = self.client.post(
            self.verify_url,
            {'contact': 'CLIENT@example.com', 'code': '123456'},
        )
        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        self.assertEqual(reponse.data['user']['email'], 'client@example.com')

    def test_signup_sms_sans_email_comptes_multiples(self):
        """Deux inscriptions SMS sans e-mail coexistent (email NULL, unique).

        Bug historique : l'e-mail était stocké en chaîne vide et la contrainte
        UNIQUE n'autorisait qu'un seul compte sans e-mail — la 2e inscription
        plantait en 500.
        """
        for numero in ('341000001', '341000002'):
            self._demander_code(telephone=numero)
            reponse = self.client.post(self.verify_url, {'contact': numero, 'code': '123456'})
            self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)

        self.assertEqual(User.objects.filter(email__isnull=True).count(), 2)

    def test_signup_send_code_anti_spam_reutilise_le_code(self):
        """Un 2e envoi dans la minute ne change pas le code (pas de spam)."""
        vc = self._demander_code(telephone='341111111')
        hash_initial = vc.code_hash

        reponse = self.client.post(self.send_url, {
            'nom': 'Rakoto Jean', 'password': 'MotDePasse123',
            'contact_type': 'sms', 'telephone': '341111111',
        })
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        # Un seul code en attente et toujours le même.
        self.assertEqual(
            VerificationCode.objects.filter(
                purpose=VerificationCode.PURPOSE_SIGNUP, is_used=False
            ).count(),
            1,
        )
        vc.refresh_from_db()
        self.assertEqual(vc.code_hash, hash_initial)

    def test_signup_mot_de_passe_faible_refuse(self):
        """La validation Django s'applique aussi au flux inscription par code."""
        reponse = self.client.post(self.send_url, {
            'nom': 'Rakoto Jean', 'password': '12345678',
            'contact_type': 'sms', 'telephone': '341222222',
        })
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST, reponse.data)


class OtpLoginTests(APITestCase):
    """Connexion par code e-mail et par code SMS."""

    def setUp(self):
        self.send_url = reverse('login-send-code')
        self.verify_url = reverse('login-verify')
        self.user = User.objects.create_user(
            username='+261341234567',
            email='client@test.com',
            telephone='+261341234567',
            password='x',
            role=User.Role.CLIENT,
        )

    def _demander_code(self, contact, contact_type='sms'):
        reponse = self.client.post(
            self.send_url, {'contact': contact, 'contact_type': contact_type}
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        vc = VerificationCode.objects.get(
            purpose=VerificationCode.PURPOSE_LOGIN, is_used=False
        )
        vc.set_code('654321')
        return vc

    def test_login_sms_contact_non_normalise(self):
        vc = self._demander_code('341234567')
        self.assertEqual(vc.contact, '+261341234567')

        reponse = self.client.post(
            self.verify_url, {'contact': '261341234567', 'code': '654321'}
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        profil = reponse.data['user']
        self.assertEqual(profil['id'], self.user.id)
        self.assertEqual(profil['role'], User.Role.CLIENT)
        self.assertEqual(profil['email'], 'client@test.com')

    def test_login_email_case_insensitive(self):
        self._demander_code('Client@Test.com', contact_type='email')
        reponse = self.client.post(
            self.verify_url,
            {'contact': 'CLIENT@test.com', 'code': '654321'},
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        self.assertEqual(reponse.data['user']['id'], self.user.id)

    def test_login_send_code_compte_inconnu(self):
        reponse = self.client.post(
            self.send_url, {'contact': '349999999', 'contact_type': 'sms'}
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_verify_code_faux_puis_bon(self):
        self._demander_code('341234567')
        mauvais = self.client.post(
            self.verify_url, {'contact': '341234567', 'code': '000000'}
        )
        self.assertEqual(mauvais.status_code, status.HTTP_400_BAD_REQUEST)
        bon = self.client.post(
            self.verify_url, {'contact': '341234567', 'code': '654321'}
        )
        self.assertEqual(bon.status_code, status.HTTP_200_OK, bon.data)


class OtpResendTests(APITestCase):
    """Renvoi du code : même normalisation que l'envoi initial."""

    def setUp(self):
        self.send_url = reverse('login-send-code')
        self.resend_url = reverse('resend-code')
        User.objects.create_user(
            username='+261341234567',
            email='client@test.com',
            telephone='+261341234567',
            password='x',
            role=User.Role.CLIENT,
        )

    def test_resend_contact_non_normalise(self):
        reponse = self.client.post(
            self.send_url, {'contact': '341234567', 'contact_type': 'sms'}
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)

        vc = VerificationCode.objects.get(purpose=VerificationCode.PURPOSE_LOGIN)
        # Anti-spam du renvoi : le code initial date d'il y a plus de 60 s.
        vc.last_sent_at = timezone.now() - timedelta(seconds=120)
        vc.save(update_fields=['last_sent_at'])

        renvoi = self.client.post(self.resend_url, {'contact': '261341234567'})
        self.assertEqual(renvoi.status_code, status.HTTP_200_OK, renvoi.data)
        vc.refresh_from_db()
        self.assertFalse(vc.is_used)
        # Un nouveau code a bien été haché sur l'enregistrement existant.
        self.assertNotEqual(vc.code_hash, '')

    def test_resend_trop_tot_refuse(self):
        self.client.post(
            self.send_url, {'contact': '341234567', 'contact_type': 'sms'}
        )
        renvoi = self.client.post(self.resend_url, {'contact': '341234567'})
        self.assertEqual(renvoi.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('attendre', renvoi.data['error'])

    def test_resend_sans_code_en_attente(self):
        renvoi = self.client.post(self.resend_url, {'contact': '341234567'})
        self.assertEqual(renvoi.status_code, status.HTTP_400_BAD_REQUEST)
