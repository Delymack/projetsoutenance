"""Colonne « Origine » de la liste des commandes clients.

`source_badge` (apps/ventes/admin.py) décore la colonne « Origine ». Elle est
appelée une fois par ligne affichée : une liste vide ne la déclenche jamais,
ce qui explique que le test d'accès générique passe alors que la page plante
dès qu'une commande existe. Ce test crée donc explicitement une commande de
chaque origine pour couvrir les deux branches.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.clients.models import Client
from apps.ventes.models import Reservation


class OrigineCommandeAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='MotDePasse123',
        )
        self.client_obj = Client.objects.create(
            nom='Rakoto', prenom='Hanta', telephone='0340000001',
        )

    def _commande(self, source):
        return Reservation.objects.create(
            client=self.client_obj,
            source=source,
            montant_total=Decimal('20000.00'),
        )

    def test_la_liste_affiche_les_deux_origines(self):
        self._commande(Reservation.Source.SITE)
        self._commande(Reservation.Source.INTERNE)

        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin:ventes_reservation_changelist'))

        self.assertEqual(response.status_code, 200, response.content)
        self.assertContains(response, 'Site web')
        self.assertContains(response, 'Saisie interne')