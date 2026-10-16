from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.produits.models import Produit
from apps.promotions.models import Promotion
from apps.stocks.models import Stock
from apps.ventes.models import LigneVente, Vente


class GestionnaireEtRapportsTests(APITestCase):
    def setUp(self):
        self.gestionnaire = User.objects.create_user(
            username='gestionnaire',
            email='gestionnaire@example.test',
            password='SecurePass!2026',
            role=User.Role.GESTIONNAIRE,
        )
        self.produit = Produit.objects.create(
            nom='Cuvée de test',
            type_vin=Produit.TypeVin.ROUGE,
            volume='750 ml',
            cout_revenir=Decimal('5000.00'),
            prix_vente=Decimal('10000.00'),
        )
        # Le signal post_save crée déjà la ligne de stock à 0 : on l'initialise
        # plutôt que de la créer (contrainte d'unicité sur produit).
        Stock.objects.update_or_create(
            produit=self.produit, defaults={'quantite': 4, 'seuil_alerte': 2},
        )
        self.date_vente = timezone.now() - timedelta(days=1)
        self.vente = Vente.objects.create(
            utilisateur=self.gestionnaire,
            mode_paiement=Vente.ModePaiement.ESPECES,
            total=Decimal('10000.00'),
        )
        Vente.objects.filter(pk=self.vente.pk).update(date_vente=self.date_vente)
        self.ligne_vente = LigneVente.objects.create(
            vente=self.vente,
            produit=self.produit,
            quantite=1,
            prix_unitaire=Decimal('10000.00'),
            sous_total=Decimal('10000.00'),
        )
        self.client.force_authenticate(self.gestionnaire)

    def test_gestionnaire_peut_acceder_a_l_admin_et_gerer_le_catalogue(self):
        self.assertTrue(self.gestionnaire.is_staff)
        self.assertTrue(self.gestionnaire.has_perm('produits.change_produit'))
        self.client.force_login(self.gestionnaire)
        self.assertEqual(self.client.get('/admin/').status_code, status.HTTP_200_OK)

        response = self.client.patch(
            reverse('produits-detail', args=[self.produit.pk]),
            {'prix_vente': '12000.00'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.prix_vente, Decimal('12000.00'))

    def test_rapport_ventes_par_jour_et_export_csv(self):
        debut = self.date_vente.date().isoformat()
        response = self.client.get(
            reverse('rapport-ventes'),
            {'debut': debut, 'fin': debut, 'par': 'jour'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['ventes'], 1)
        self.assertEqual(response.data['chiffre_affaires'], '10000.00')
        self.assertEqual(response.data['valeur_stock'], '20000.00')
        self.assertEqual(response.data['donnees'][0]['ventes'], 1)
        self.assertEqual(response.data['promotions']['ventes'], 0)

        # L'export passe par les renderers DRF (`?format=`), pas par un paramètre
        # maison : le même code sert alors le CSV et l'Excel.
        response = self.client.get(
            reverse('rapport-ventes'),
            {'debut': debut, 'fin': debut, 'par': 'vin', 'format': 'csv'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn(f'rapport-ventes-vin-{debut}', response['Content-Disposition'])
        csv_lu = response.content.decode('utf-8-sig')
        self.assertIn('Cuvée de test', csv_lu)
        # En-têtes en français : le tableur est lu par le comptable.
        self.assertIn('Cuvée;Ventes;Quantité;Chiffre d\'affaires', csv_lu)

        response = self.client.get(
            reverse('rapport-ventes'),
            {'debut': debut, 'fin': debut, 'par': 'vin', 'format': 'xlsx'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('spreadsheetml', response['Content-Type'])
        classeur = load_workbook(BytesIO(response.content), read_only=True)
        lignes = list(classeur['Ventes'].values)
        self.assertEqual(list(lignes[0]), ['Cuvée', 'Ventes', 'Quantité', "Chiffre d'affaires"])
        self.assertEqual(lignes[1][0], 'Cuvée de test')
        self.assertIn('Promotions', classeur.sheetnames)
        self.assertIn('Synthèse', classeur.sheetnames)

    def test_rapport_efficacite_promotion_et_export_pdf(self):
        maintenant = timezone.now()
        promotion = Promotion.objects.create(
            nom='Offre découverte',
            type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=Decimal('10.00'),
            date_debut=maintenant - timedelta(days=2),
            date_fin=maintenant + timedelta(days=2),
        )
        self.ligne_vente.promotion = promotion
        self.ligne_vente.remise = Decimal('1000.00')
        self.ligne_vente.sous_total = Decimal('9000.00')
        self.ligne_vente.save(update_fields=['promotion', 'remise', 'sous_total'])

        debut = self.date_vente.date().isoformat()
        response = self.client.get(
            reverse('rapport-ventes'),
            {'debut': debut, 'fin': debut, 'par': 'jour'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['promotions']['ventes'], 1)
        self.assertEqual(response.data['promotions']['remise_accordee'], '1000.00')
        self.assertEqual(response.data['promotions']['chiffre_affaires_net'], '9000.00')
        self.assertEqual(response.data['promotions']['donnees'][0]['promotion'], 'Offre découverte')

        response = self.client.get(
            reverse('rapport-ventes'),
            {'debut': debut, 'fin': debut, 'par': 'jour', 'format': 'pdf'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF-'))

    def test_page_rapports_est_accessible_au_gestionnaire(self):
        self.client.force_login(self.gestionnaire)
        response = self.client.get(reverse('rapports'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'id="promotions-title"')
        self.assertContains(response, 'report-print')
        self.assertContains(response, 'statistiques-256.png')
        self.assertNotContains(response, '/admin/zreport/')

        response = self.client.get('/admin/zreport/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_rapport_refuse_les_periodes_invalides(self):
        response = self.client.get(
            reverse('rapport-ventes'),
            {'debut': '2026-02-02', 'fin': '2026-02-01'},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_tous_les_regroupements_de_rapport_sont_disponibles(self):
        debut = self.date_vente.date().isoformat()
        for regroupement in ('jour', 'semaine', 'mois', 'annee', 'vin', 'categorie', 'vendeur'):
            with self.subTest(regroupement=regroupement):
                response = self.client.get(
                    reverse('rapport-ventes'),
                    {'debut': debut, 'fin': debut, 'par': regroupement},
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data['par'], regroupement)
                self.assertEqual(len(response.data['donnees']), 1)

    def test_rapport_refuse_un_compte_vendeur(self):
        vendeur = User.objects.create_user(
            username='vendeur',
            email='vendeur@example.test',
            password='SecurePass!2026',
            role=User.Role.VENDEUR,
        )
        self.client.force_authenticate(vendeur)
        response = self.client.get(reverse('rapport-ventes'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
