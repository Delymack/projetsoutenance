from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.clients.models import Client
from apps.produits.models import Produit
from apps.promotions.models import Promotion
from apps.ventes.models import Reservation

User = get_user_model()


class ConfirmationSuppressionTests(TestCase):
    """Le bouton « Supprimer » ouvre une petite fenêtre de confirmation.

    La fenêtre vit dans ``templates/admin/base.html`` et le script
    ``static/js/wineadmin-confirm.js`` intercepte tout lien portant la classe
    ``databtn-delete`` : le bouton de la barre d'une fiche comme celui de la
    colonne « Actions » d'une liste. Sans JavaScript, le lien redevient un lien
    ordinaire et Django affiche sa propre page de confirmation.
    """

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='MotDePasse123!',
        )
        self.client.force_login(self.admin)
        self.client_fiche = Client.objects.create(nom='Rakoto', prenom='Jean')
        self.commande = Reservation.objects.create(client=self.client_fiche)

    def test_la_fenetre_et_son_script_sont_charges_dans_l_admin(self):
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="wine-confirm"')
        self.assertContains(response, 'id="wine-confirm-form"')
        self.assertContains(response, 'id="wine-confirm-message"')
        self.assertContains(response, 'wineadmin-confirm.js')
        # Sans ce champ, Django renverrait la page de confirmation au lieu de
        # supprimer : le POST doit être non vide.
        self.assertContains(response, 'name="post" value="yes"')

    def test_bouton_supprimer_de_la_fiche_commande_ouvre_la_fenetre(self):
        response = self.client.get(f'/admin/ventes/reservation/{self.commande.pk}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.count(b'id="jazzy-actions"'), 1)
        self.assertEqual(response.content.count(b'databtn-delete'), 1)
        for champ in (
            'client', 'montant_total', 'montant_acompte', 'mode_reception',
            'adresse_livraison', 'date_expiration', 'note',
        ):
            with self.subTest(champ=champ):
                self.assertContains(response, f'name="{champ}"')
        # Le lien garde sa destination Django : le script ne fait que
        # l'intercepter pour demander confirmation avant l'envoi du POST.
        self.assertContains(
            response,
            f'/admin/ventes/reservation/{self.commande.pk}/delete/',
        )
        self.assertContains(response, 'databtn-delete')
        self.assertContains(response, f'data-confirm-name="Commande {self.commande.reference}"')

    def test_bouton_supprimer_de_la_liste_commandes_ouvre_la_fenetre(self):
        response = self.client.get('/admin/ventes/reservation/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<a class="databtn databtn-delete"')
        self.assertContains(response, f'data-confirm-name="Commande {self.commande.reference}"')

    def test_la_suppression_par_post_reste_possible(self):
        """La fenêtre envoie un POST : le circuit de suppression doit marcher.

        On envoie exactement ce que le formulaire produit — le jeton CSRF et
        ``post=yes`` —, car Django n'exécute la suppression que si le POST
        n'est pas vide.
        """
        response = self.client.post(
            f'/admin/ventes/reservation/{self.commande.pk}/delete/',
            {'post': 'yes'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Reservation.objects.filter(pk=self.commande.pk).exists())

    # ------------------------------------------------------------------
    # Couverture : toutes les tables de la console, pas seulement la commande
    # ------------------------------------------------------------------

    def test_aucune_table_de_la_console_ne_reste_sans_bouton(self):
        """Contrôle sur l'enregistrement des admin, pas sur une seule page.

        Un nouvel admin qui oublierait ``ActionsColonneMixin`` — et perdrait
        donc son bouton Supprimer — fait échouer ce test.
        """
        from django.contrib import admin as django_admin

        from config.admin_mixins import ActionsColonneMixin

        # Modèles techniques de Django, d'allauth et des sites : hors périmètre.
        hors_perimetre = {'auth', 'contenttypes', 'sessions', 'sites', 'socialaccount'}
        sans_bouton = [
            f'{modele._meta.label} ({type(modeladmin).__name__})'
            for modele, modeladmin in django_admin.site._registry.items()
            if modele._meta.app_label not in hors_perimetre
            and not isinstance(modeladmin, ActionsColonneMixin)
        ]
        self.assertEqual(sans_bouton, [], f'Tables sans bouton Supprimer : {sans_bouton}')

    def test_les_pages_citees_affichent_le_bouton(self):
        """Commandes, produits, stocks, utilisateurs : le bouton est là."""
        # Chaque liste n'affiche sa colonne « Actions » que si elle a au moins
        # une ligne : on peuple donc une ligne par table testée. Le signal de
        # création d'un produit ouvre aussi sa ligne de stock.
        Produit.objects.create(
            nom='Côtes de test', volume='75 cl', prix_vente=Decimal('10000.00'),
        )
        Promotion.objects.create(
            nom='Promo de test',
            valeur=Decimal('10.00'),
            date_debut=timezone.now() - timedelta(days=1),
            date_fin=timezone.now() + timedelta(days=1),
        )
        # Un second compte est nécessaire : Django interdit de supprimer le
        # sien, la ligne de l'administrateur connecté n'a donc pas de bouton.
        User.objects.create_user(
            username='vendeur', email='vendeur@test.com', password='MotDePasse123!',
        )
        pages = {
            'commandes': '/admin/ventes/reservation/',
            'produits': '/admin/produits/produit/',
            'stocks': '/admin/stocks/stock/',
            'utilisateurs': '/admin/accounts/user/',
            'promotions': '/admin/promotions/promotion/',
            'clients': '/admin/clients/client/',
        }
        for nom, url in pages.items():
            with self.subTest(page=nom):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<a class="databtn databtn-delete"')

    def test_bouton_supprimer_de_la_fiche_produit_ouvre_la_fenetre(self):
        produit = Produit.objects.create(
            nom='Côtes de test', volume='75 cl', prix_vente=Decimal('10000.00'),
        )
        response = self.client.get(f'/admin/produits/produit/{produit.pk}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'databtn-delete')
        self.assertContains(response, f'/admin/produits/produit/{produit.pk}/delete/')