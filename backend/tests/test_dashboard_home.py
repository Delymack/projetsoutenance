from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.dashboard.stats import stats_completes
from apps.produits.models import Produit
from apps.promotions.models import Promotion
from apps.ventes.models import LigneVente, Vente


class DashboardHomeTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='dashboard-admin',
            email='dashboard-admin@example.com',
            password='test-password-123',
        )
        self.client.force_login(self.admin_user)

    def test_admin_home_displays_the_reference_dashboard_sections(self):
        response = self.client.get(reverse('admin:index'))

        self.assertEqual(response.status_code, 200)
        for label in (
            'Chiffre d’affaires du mois',
            'Unités vendues du mois',
            'Produits en rupture',
            'Promotions actives',
            'Chiffre d’affaires · 6 derniers mois',
            'Ventes par appellation',
            'Meilleures ventes',
            'Ventes récentes',
        ):
            self.assertContains(response, label)
        self.assertContains(response, reverse('admin:stocks_stock_changelist'))
        self.assertNotContains(response, 'Bonjour,')

        for removed_section in (
            'Moyens de paiement',
            'Meilleurs clients',
            'Créances clients',
            'Cuvées à surveiller',
        ):
            self.assertNotContains(response, removed_section)

    def test_admin_home_uses_real_sales_and_active_promotion_data(self):
        product = Produit.objects.create(
            nom='Cuvée de démonstration',
            appellation='Haute Matsiatra',
            prix_vente=Decimal('50.00'),
            volume='750 ml',
        )
        sale = Vente.objects.create(
            utilisateur=self.admin_user,
            total=Decimal('100.00'),
            statut=Vente.Statut.PAYEE,
        )
        LigneVente.objects.create(
            vente=sale,
            produit=product,
            quantite=2,
            prix_unitaire=Decimal('50.00'),
            sous_total=Decimal('100.00'),
        )
        now = timezone.now()
        Promotion.objects.create(
            nom='Offre de démonstration',
            type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=Decimal('10.00'),
            date_debut=now - timedelta(days=1),
            date_fin=now + timedelta(days=1),
            statut=True,
        )

        response = self.client.get(reverse('admin:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cuvée de démonstration')
        self.assertContains(response, 'Haute Matsiatra')
        self.assertContains(response, 'Offre de démonstration')
        stats = stats_completes()
        self.assertEqual(stats['produits_vendus_mois'], 2)
        self.assertEqual(stats['meilleures_ventes'][0]['produit__nom'], product.nom)
        self.assertEqual(stats['ventes_par_appellation'][0]['label'], product.appellation)
