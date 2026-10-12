"""Colonne « Code-barres » de la liste des produits.

`code_barre_display` (apps/produits/admin.py) préfixe le code d'un pictogramme
d'alerte lorsque les 13 chiffres portent une clé EAN-13 invalide. Cette branche
n'est atteinte que par un produit réellement mal codé : sans un tel produit, la
liste ne l'exerce jamais et le plantage passe inaperçu.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.produits.barcode import cle_ean13_valide
from apps.produits.models import Produit


class CodeBarreAdminTests(TestCase):
    # 13 chiffres dont la clé de contrôle est fausse : pour le corps
    # « 123456789012 », la clé attendue est 8, pas 0.
    CODE_INVALIDE = '1234567890120'

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='MotDePasse123',
        )
        self.produit = Produit.objects.create(
            nom='Cuvée 2018', type_vin='Rouge', marque='Domaine',
            cout_revenir=Decimal('5000.00'), prix_vente=Decimal('10000.00'),
            code_barre=self.CODE_INVALIDE, statut=True,
        )

    def test_la_liste_signale_un_code_ean13_invalide(self):
        # Prémisse : ce code doit bien être rejeté par la clé EAN-13. Sans cette
        # assertion, un code valide ferait passer le test sans exercer la
        # branche fautive, donc sans rien prouver.
        self.assertFalse(cle_ean13_valide(self.CODE_INVALIDE))

        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin:produits_produit_changelist'))

        self.assertEqual(response.status_code, 200, response.content)
        self.assertContains(response, 'fa-triangle-exclamation')