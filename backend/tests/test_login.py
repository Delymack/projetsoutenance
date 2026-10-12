from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase

from apps.accounts.backends import EmailOrUsernameBackend
from apps.accounts.services import is_locked
from apps.produits.models import Produit
from apps.stocks.models import Stock


class EmailOrUsernameBackendTests(TestCase):
    """
    Tests du backend de login « email ou identifiant ».
    """

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='vendeur', email='Vendeur@Test.com', password='password123',
            role=User.Role.VENDEUR,
        )

    def test_connexion_par_identifiant(self):
        user = authenticate(username='vendeur', password='password123')
        self.assertIsNotNone(user)
        self.assertEqual(user, self.user)

    def test_vendeur_autorise_peut_ouvrir_le_back_office(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])

        response = self.client.post('/admin/login/', {
            'username': 'vendeur', 'password': 'password123',
        })

        self.assertRedirects(response, '/admin/')

    def test_connexion_par_email(self):
        user = authenticate(username='vendeur@test.com', password='password123')
        self.assertEqual(user, self.user)

    def test_connexion_par_email_insensible_a_la_casse(self):
        user = authenticate(username='VENDEUR@TEST.COM', password='password123')
        self.assertEqual(user, self.user)

    def test_mot_de_passe_incorrect(self):
        user = authenticate(username='vendeur', password='mauvais')
        self.assertIsNone(user)
        self.assertEqual(is_locked('vendeur'), 0)

    def test_identifiant_inconnu(self):
        user = authenticate(username='nobody@test.com', password='password123')
        self.assertIsNone(user)

    def test_utilisateur_desactive_refuse(self):
        self.user.is_active = False
        self.user.save()
        user = authenticate(username='vendeur@test.com', password='password123')
        self.assertIsNone(user)

    def test_champ_username_absent(self):
        user = authenticate(password='password123')
        self.assertIsNone(user)

    def test_backend_enregistre_dans_authenticate(self):
        # Vérifie que le backend est bien le premier de la chaîne configurée.
        from django.contrib.auth import get_backends
        backends = get_backends()
        self.assertIsInstance(backends[0], EmailOrUsernameBackend)


class LoginBackgroundTests(TestCase):
    def test_page_connexion_utilise_la_photo_comme_fond_transparent(self):
        response = self.client.get('/admin/login/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/static/img/login-cellar.jpg')
        self.assertContains(response, 'background: transparent !important;')
        self.assertContains(response, 'background: rgba(12, 7, 9, .72);')
        self.assertContains(response, 'justify-content: flex-start;')
        self.assertContains(response, 'placeholder="Identifiant ou e-mail"')
        self.assertContains(response, 'placeholder="Mot de passe"')
        self.assertContains(response, 'Mot de passe oublié ?')
        self.assertContains(response, 'Créer un compte')
        self.assertNotContains(response, 'remember_me')
        self.assertNotContains(response, 'Continuer avec Google')
        self.assertNotContains(response, 'Se connecter sans mot de passe')
        self.assertNotContains(response, 'Accès réservé.')

    def test_connexion_affiche_seulement_le_compteur_de_notifications(self):
        produit = Produit.objects.create(
            nom='Vin sans stock', volume='75 cl', prix_vente=15000,
        )
        Stock.objects.update_or_create(
            produit=produit, defaults={'quantite': 0, 'seuil_alerte': 5},
        )

        response = self.client.get('/admin/login/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="wine-login-notification"')
        self.assertEqual(response.context['admin_notification_count'], 1)
        self.assertIn('      1\n    </span>', response.content.decode())
        self.assertNotContains(response, 'id="wine-notifications-menu"')
        self.assertNotContains(response, 'id="wine-notifications-trigger"')
