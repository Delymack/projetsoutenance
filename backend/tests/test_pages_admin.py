"""Tests des pages d'administration et de la caisse POS.

Couvre les pages HTML (non-API) : accès restreints, rendu du back-office
Django, calcul des KPIs du changelist des promotions et caisse enregistreuse
(POS). Le Z-Report a été retiré du back-office : la clôture de caisse
passe par les sessions, sans page dédiée.
"""
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib import admin as dj_admin
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.clients.models import Client
from apps.produits.models import Produit
from apps.promotions.models import Promotion
from apps.stocks.models import Stock
from apps.ventes.models import LigneVente, Vente

RACINE = Path(__file__).resolve().parent.parent


class AccesPagesTests(TestCase):
    """Accès aux pages admin : anonyme redirigé, staff autorisé."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123',
        )
        self.vendeur = User.objects.create_user(
            username='vendeur', email='vendeur@test.com', password='password123',
            role=User.Role.VENDEUR,
        )

    def test_index_admin_anonyme_redirige_vers_login(self):
        self.client.logout()
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_index_admin_staff_accessible(self):
        self.client.force_login(self.admin)
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="wine-brand"')
        self.assertContains(response, 'img/lazani-betsileo-mark.svg')
        self.assertNotContains(response, 'class="sidebar-brand"')
        self.assertNotContains(response, 'class="sb-user"')
        self.assertNotContains(response, 'ESPACE CAISSE')
        self.assertNotContains(response, 'RÉGLAGES')
        self.assertNotContains(response, "Le journal d'activité reste accessible")
        self.assertContains(response, '<span class="nav-section-label">Accès rapide</span>')
        self.assertContains(response, '<span class="nav-section-label">Réglages</span>')
        self.assertContains(response, 'id="wine-account-trigger"')
        self.assertContains(response, 'id="jazzy-usermenu"')
        self.assertContains(response, 'id="wine-notifications-trigger"')
        self.assertContains(response, 'id="wine-notifications-menu"')
        self.assertContains(response, 'wineadmin-notifications.css?v=2')
        self.assertContains(response, 'wineadmin-notifications.js?v=2')
        self.assertContains(response, 'aria-labelledby="wine-account-trigger"')
        self.assertContains(response, 'Sécurité')
        self.assertContains(response, 'Mot de passe')
        self.assertContains(response, 'data-lte-toggle="sidebar"')
        self.assertContains(response, 'wine-sidebar-toggle')
        self.assertNotContains(response, 'Membre depuis')
        self.assertNotContains(response, 'Dernière connexion')
        self.assertNotContains(response, 'wine-account-stat')
        self.assertNotContains(response, 'wine-theme-toggle')
        self.assertContains(response, 'id="wine-quick-create"')
        self.assertContains(response, 'wineadmin-quickcreate.css?v=8')
        self.assertContains(response, 'wineadmin-quickcreate.js?v=8')
        quick_create_js = (RACINE / 'static' / 'js' / 'wineadmin-quickcreate.js').read_text(encoding='utf-8')
        self.assertIn("'[name=\"_addanother\"], [name=\"_continue\"], [name=\"_saveasnew\"], a'", quick_create_js)
        self.assertNotIn('Enregistrer et ajouter', quick_create_js)
        self.assertIn('wine-quick-create-cancel', quick_create_js)
        quick_create_css = (RACINE / 'static' / 'css' / 'wineadmin-quickcreate.css').read_text(encoding='utf-8')
        self.assertIn('[name="_save"]', quick_create_css)
        self.assertIn("const label = editMode ? 'Modifier' : 'Enregistrer';", quick_create_js)
        self.assertIn("ligneChamps.after(ligneActions);", quick_create_js)
        self.assertIn("colonneChamps?.classList.add('wine-quick-create-fields');", quick_create_js)
        self.assertIn("'.submit-row, .card-body > .d-flex.flex-wrap'", quick_create_js)
        self.assertIn("content.querySelector('#content-main form')", quick_create_js)
        self.assertIn("Boolean(lien.closest('tr')) && pageModification", quick_create_js)
        self.assertIn("lien.matches('.databtn-edit')", quick_create_js)
        self.assertIn("pageModification", quick_create_js)
        self.assertIn('wine-quick-create-actions', quick_create_css)
        self.assertIn('justify-content: flex-end;', quick_create_css)
        self.assertIn('min-width: 132px;', quick_create_css)
        self.assertIn("'[name=\"_addanother\"], [name=\"_continue\"], [name=\"_saveasnew\"], a'", quick_create_js)
        self.assertNotIn('position: sticky;', quick_create_css)
        self.assertContains(response, 'data-quick-create="wide"')

        html = response.content.decode()
        self.assertEqual(html.count('wineadmin.js?v=12'), 1)
        js = (RACINE / 'static' / 'js' / 'wineadmin.js').read_text(encoding='utf-8')
        self.assertIn("nav.querySelector('.wine-theme-toggle')", js)

    def test_cloche_admin_affiche_les_alertes_de_stock_avec_un_lien_actionnable(self):
        produit = Produit.objects.create(
            nom='Vin stock bas', volume='75 cl', prix_vente=15000,
        )
        Stock.objects.update_or_create(
            produit=produit, defaults={'quantite': 2, 'seuil_alerte': 5},
        )
        self.client.force_login(self.admin)

        response = self.client.get('/admin/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['admin_notification_count'], 1)
        self.assertContains(response, 'Stock faible : Vin stock bas')
        self.assertContains(response, reverse('admin:stocks_stock_changelist'))

    def test_navigation_complete_reste_visible_sur_les_pages_admin_personnalisees(self):
        self.client.force_login(self.admin)
        pages = (
            reverse('rapports'),
            reverse('caisse-enregistreuse'),
            reverse('parametres:index'),
        )

        for url in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['available_apps'])
                self.assertContains(response, reverse('admin:produits_produit_changelist'))
                self.assertContains(response, reverse('admin:clients_client_changelist'))
                self.assertContains(response, 'Rapports')
                self.assertContains(response, 'Réglages')

    def test_formulaire_ajout_est_encadre_par_la_fenetre_rapide(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse('admin:produits_produit_add'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="wine-quick-create"')
        self.assertContains(response, 'id="wine-quick-create-content"')
        self.assertNotContains(response, '<iframe')
        self.assertContains(response, 'nom')
        self.assertContains(response, 'name="_save"')
        self.assertContains(response, 'name="_addanother"')

    def test_formulaire_modification_peut_etre_charge_dans_la_fenetre(self):
        produit = Produit.objects.create(
            nom='Vin à modifier', volume='75 cl', cout_revenir=8000, prix_vente=15000,
        )
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse('admin:produits_produit_change', args=[produit.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="wine-quick-create-content"')
        self.assertContains(response, 'name="_save"')
        self.assertContains(response, 'Vin à modifier')

    def test_l_action_modifier_des_lignes_est_compatible_avec_la_fenetre(self):
        produit = Produit.objects.create(
            nom='Vin dans la liste', volume='75 cl', cout_revenir=8000, prix_vente=15000,
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse('admin:produits_produit_changelist'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="databtn databtn-edit"')
        self.assertContains(
            response,
            reverse('admin:produits_produit_change', args=[produit.pk]),
        )


class PromotionAdminTests(TestCase):
    """Le changelist des promotions calcule ses KPIs (fenêtre « active »)."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123',
        )
        maintenant = timezone.now()
        demain = maintenant + timedelta(days=1)
        hier = maintenant - timedelta(days=1)
        dans_2_jours = maintenant + timedelta(days=2)

        Promotion.objects.create(
            nom='Promo active', type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=10, date_debut=hier, date_fin=demain, statut=True,
        )
        Promotion.objects.create(
            nom='Promo passée', type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=15, date_debut=maintenant - timedelta(days=10),
            date_fin=hier, statut=True,
        )
        Promotion.objects.create(
            nom='Promo à échéance', type_promotion=Promotion.TypePromotion.MONTANT_FIXE,
            valeur=50, date_debut=maintenant - timedelta(days=1),
            date_fin=dans_2_jours, statut=True,
        )
        Promotion.objects.create(
            nom='Promo sans produit', type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=20, date_debut=maintenant - timedelta(days=1),
            date_fin=maintenant + timedelta(days=10), statut=True,
        )

    def test_changelist_promotions_accessible_avec_kpis(self):
        self.client.force_login(self.admin)
        response = self.client.get('/admin/promotions/promotion/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Promo active')
        kpis = response.context.get('promotions_kpis')
        self.assertIsNotNone(kpis)
        self.assertEqual(kpis['total'], 4)
        self.assertEqual(kpis['actives'], 3)
        self.assertEqual(kpis['bientot_expirees'], 2)
        self.assertEqual(kpis['sans_produit'], 4)
        self.assertNotEqual(kpis['expirees'], 0)
        self.assertIn('Promo à échéance', response.content.decode())
        self.assertIsNotNone(response.context.get('promotions_alerts'))

    def test_impact_promotions_utilise_le_champ_total_des_ventes(self):
        produit = Produit.objects.create(
            nom='Vin promotionné', type_vin='Rouge', marque='Domaine',
            cout_revenir=Decimal('5000.00'), prix_vente=Decimal('10000.00'),
            statut=True,
        )
        Stock.objects.update_or_create(
            produit=produit, defaults={'quantite': 5, 'seuil_alerte': 1},
        )
        promotion = Promotion.objects.get(nom='Promo active')
        promotion.produits.add(produit)
        vente = Vente.objects.create(
            utilisateur=self.admin,
            mode_paiement=Vente.ModePaiement.ESPECES,
            statut=Vente.Statut.PAYEE,
            total=Decimal('9000.00'),
        )
        LigneVente.objects.create(
            vente=vente,
            produit=produit,
            quantite=1,
            prix_unitaire=Decimal('10000.00'),
            remise=Decimal('1000.00'),
            sous_total=Decimal('9000.00'),
            promotion=promotion,
        )
        self.client.force_login(self.admin)

        response = self.client.get('/admin/promotions/promotion/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ventes promo')
        self.assertContains(response, 'Remise accordée')
        self.assertContains(response, 'CA généré')
        self.assertContains(response, 'Désactiver')
        kpis = response.context['promotions_kpis']
        self.assertEqual(kpis['ca_total_30j'], Decimal('9000.00'))
        self.assertEqual(kpis['ca_promo_30j'], Decimal('9000.00'))


class ChangelistsVentesProduitsTests(TestCase):
    """Changelists dont les agrégats ont déjà cassé (non couverts par l'API)."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123',
        )
        self.produit = Produit.objects.create(
            nom='Antsirabe Rouge', type_vin='Rouge', marque="LAZAN'I BETSILEO",
            cout_revenir=Decimal('18000.00'), prix_vente=Decimal('38000.00'), statut=True,
        )
        # Sans code-barres : la colonne doit afficher « À générer » sans lever.
        self.assertFalse(self.produit.code_barre)
        Stock.objects.update_or_create(
            produit=self.produit, defaults={'quantite': 12, 'seuil_alerte': 5},
        )

    def test_changelist_produits_sans_code_barre(self):
        """RRegression : format_html() sans argument levait une TypeError."""
        self.client.force_login(self.admin)
        response = self.client.get('/admin/produits/produit/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'À générer')
        html = response.content.decode()
        self.assertContains(response, '<h1><i class="fas fa-wine-bottle lb-hero-icon"></i>Produits</h1>')
        for precision in (
            'Le catalogue de vos cuvées',
            'Référentiel',
            'potentiel Ar',
        ):
            self.assertNotIn(precision, html)

    def test_changelist_ventes_avec_remise_manuelle(self):
        """La fiche vente affiche la remise manuelle, y compris après allègement
        de la liste : le champ est porté par la vente, pas par la ligne."""
        vente = Vente.objects.create(
            client=Client.objects.create(nom='Dupont', prenom='Jean', telephone='0102030405'),
            utilisateur=self.admin, mode_paiement=Vente.ModePaiement.ESPECES,
            statut=Vente.Statut.PAYEE, total=Decimal('38000.00'),
            remise_manuelle_totale=Decimal('2000.00'),
        )
        LigneVente.objects.create(
            vente=vente, produit=self.produit, quantite=1,
            prix_unitaire=Decimal('38000.00'), sous_total=Decimal('38000.00'),
            remise_manuelle=Decimal('2000.00'),
        )
        self.client.force_login(self.admin)
        liste = self.client.get('/admin/ventes/vente/')
        self.assertEqual(liste.status_code, 200)
        self.assertNotIn(
            'lb-kpis', liste.content.decode(),
            'la page Ventes ne doit plus doubler le tableau de bord',
        )
        fiche = self.client.get(f'/admin/ventes/vente/{vente.pk}/change/')
        self.assertEqual(fiche.status_code, 200)
        self.assertContains(fiche, 'remise_manuelle_totale')

    def test_page_ventes_reste_une_recherche_simple(self):
        """Allègement : 7 colonnes, recherche par référence/client, 3 filtres.

        `date_echeance` prolonge l'allègement au service des impayés : la
        créance arrive sur la liste sans y ajouter le mode de paiement ni le
        nombre d'articles.
        """
        admin_ventes = dj_admin.site._registry[Vente]
        # `client_affiche` et non la clé étrangère `client` : une vente encaissée
        # sans identité laisse le FK vide, et la colonne doit quand même dire
        # « Client de passage » au vendeur.
        self.assertEqual(
            admin_ventes.list_display,
            ('reference', 'client_affiche', 'total_badge', 'statut_badge',
             'date_vente', 'date_echeance', 'imprimer_facture'),
        )
        self.assertEqual(admin_ventes.list_filter, ('statut', 'date_vente', 'date_echeance'))
        # `client_libelle` complète la recherche : le nom saisi au comptoir pour
        # un client de passage se retrouve au même endroit qu'un client enregistré.
        self.assertEqual(
            admin_ventes.search_fields,
            ('reference', 'client__nom', 'client__prenom', 'client_libelle'),
        )
        self.client.force_login(self.admin)
        html = self.client.get('/admin/ventes/vente/').content.decode()
        # Les raccourcis utiles restent à portée de main.
        for url in (reverse('caisse-enregistreuse'),
                    reverse('admin:ventes_reservation_changelist')):
            self.assertIn(url, html)
        # Les sessions de caisse ont quitté le menu, l'archive reste accessible.
        menu = self.client.get(reverse('admin:index')).content.decode()
        menu = menu[menu.index('<aside'):menu.index('</aside>')]
        self.assertNotIn('Sessions de caisse', menu)
        self.assertEqual(self.client.get('/admin/ventes/sessioncaisse/').status_code, 200)

    def test_la_caisse_ne_garde_que_les_raccourcis_essentiels(self):
        """Rejouer / suspendre une vente a disparu ; payer, remettre, retourner
        et clôturer restent."""
        self.client.force_login(self.admin)
        pos = self.client.get(reverse('caisse-enregistreuse')).content.decode()
        for attendu in ('checkout-btn', 'open-remise', 'open-retour', 'session-open'):
            self.assertIn(f'id="{attendu}"', pos)
        for retire in ('id="repeat-sale"', 'id="suspend-sale"', 'id="resume-sale"', 'id="pending-bar"'):
            self.assertNotIn(retire, pos)
        js = (RACINE / 'static' / 'js' / 'wineadmin-pos.js').read_text(encoding='utf-8')
        for fonction in ('rejouerDerniere', 'suspendre', 'reprendre', 'majBarreAttente'):
            self.assertNotIn(fonction, js, f'{fonction} a été retiré de la caisse')
        self.assertIn("case 'F9'", js)


class POSTests(TestCase):
    """Caisse enregistreuse (POS) : réservée aux utilisateurs connectés."""

    def setUp(self):
        self.vendeur = User.objects.create_user(
            username='caissier', email='caissier@test.com', password='password123',
            role=User.Role.VENDEUR,
        )

    def test_pos_anonyme_redirige_vers_login(self):
        self.client.logout()
        response = self.client.get('/admin/caisse/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_pos_vendeur_accede_a_la_caisse(self):
        self.client.force_login(self.vendeur)
        response = self.client.get('/admin/caisse/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nouvelle vente')
