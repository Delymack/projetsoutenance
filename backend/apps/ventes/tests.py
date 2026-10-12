from django.test import TestCase
from rest_framework.test import APIClient


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
