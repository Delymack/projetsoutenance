from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from apps.accounts.models import User

class AuthTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vendeur1', email='vendeur@test.com', password='password123', role=User.Role.VENDEUR)
        self.login_url = reverse('token_obtain_pair')
        self.me_url = reverse('auth_me')

    def test_login_valide(self):
        response = self.client.post(self.login_url, {'username': 'vendeur1', 'password': 'password123'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_login_invalide(self):
        response = self.client.post(self.login_url, {'username': 'vendeur1', 'password': 'wrongpassword'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_acces_sans_token(self):
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
