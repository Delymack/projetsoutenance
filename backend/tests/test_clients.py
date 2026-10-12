from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from apps.accounts.models import User
from apps.clients.models import Client


class ClientTests(APITestCase):
    """
    Tests CRUD + permissions de l'API clients.
    Permission attendue : CanManageClients (admin et vendeur),
    refus pour utilisateur anonyme.
    """

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123'
        )
        self.vendeur = User.objects.create_user(
            username='vendeur', email='vendeur@test.com', password='password123',
            role=User.Role.VENDEUR
        )
        self.clients_url = reverse('clients-list')
        self.client_obj = Client.objects.create(
            nom="Dupont", prenom="Jean", telephone="0102030405",
            email="jean.dupont@example.com"
        )

    def authenticate(self, user):
        response = self.client.post(
            reverse('token_obtain_pair'),
            {'username': user.username, 'password': 'password123'}
        )
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])

    # --- Lecture ---

    def test_liste_clients_vendeur(self):
        self.authenticate(self.vendeur)
        response = self.client.get(self.clients_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['nom'], "Dupont")

    def test_acces_sans_authentification(self):
        response = self.client.get(self.clients_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- Création ---

    def test_creation_client_par_vendeur(self):
        self.authenticate(self.vendeur)
        data = {"nom": "Martin", "prenom": "Marie", "telephone": "0607080910"}
        response = self.client.post(self.clients_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Client.objects.count(), 2)
        self.assertEqual(Client.objects.filter(nom="Martin").count(), 1)

    def test_creation_client_champs_requis(self):
        self.authenticate(self.vendeur)
        response = self.client.post(self.clients_url, {"nom": "Martin"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- Modification / Suppression ---

    def test_modification_client_par_vendeur(self):
        self.authenticate(self.vendeur)
        url = reverse('clients-detail', args=[self.client_obj.id])
        response = self.client.patch(url, {"telephone": "0999888777"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.telephone, "0999888777")

    def test_suppression_client_par_admin(self):
        self.authenticate(self.admin)
        url = reverse('clients-detail', args=[self.client_obj.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Client.objects.count(), 0)

    def test_suppression_client_par_vendeur(self):
        # CanManageClients autorise aussi le vendeur en écriture
        self.authenticate(self.vendeur)
        url = reverse('clients-detail', args=[self.client_obj.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
