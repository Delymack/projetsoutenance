"""Cohérence des formulaires d'administration.

Ces tests ne visent pas l'apparence mais la **correction** des formulaires :
Django ne signale pas (dans `manage.py check`) un champ non éditable placé dans
un `fieldset`, ce qui provoque une erreur 500 à l'ouverture. On vérifie donc
directement que chaque formulaire se construit, et qu'il expose les éléments
attendus (champs, aides, unités, filtres, recherche).
"""
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin as dj_admin
from django import forms
import django
import django.apps

APPS_DU_PROJET = {
    'accounts', 'categories', 'clients', 'dashboard',
    'parametres', 'produits', 'promotions', 'stocks', 'ventes',
}

# Champs repris tels quels de django.contrib.auth : ce ne sont pas des textes
# écrits pour ce projet, on ne les réécrit pas ici.
CHAMPS_HERITES_CONTRIB = {
    'username', 'first_name', 'last_name', 'email', 'password', 'last_login',
    'date_joined', 'is_staff', 'is_active', 'is_superuser',
    'groups', 'user_permissions',
}
from django.core.files.base import ContentFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.categories.models import Categorie
from apps.clients.models import Client, ReglementClient
from apps.produits.images import ImageDistanteInvalide
from apps.produits.models import Produit
from apps.promotions.models import Promotion, PromotionProduit
from apps.ventes.models import Vente

# Gabarits d'admin fournis par des tiers : hors de notre périmètre.
TIERS = {
    'account.EmailAddress', 'socialaccount.SocialAccount', 'socialaccount.SocialApp',
    'socialaccount.SocialToken', 'sites.Site', 'auth.Group', 'auth.Permission',
}


def admins_metier():
    return [
        (model, ma) for model, ma in dj_admin.site._registry.items()
        if model._meta.label not in TIERS and model is not User
    ]


class FormulairesAdminTests(TestCase):
    """Chaque ModelAdmin métier doit produire un formulaire exploitable."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123',
        )
        self.client.force_login(self.admin)
        self.factory = RequestFactory()

    def get_request(self, path='/admin/'):
        request = self.factory.get(path)
        request.user = self.admin
        return request

    def test_les_champsets_ne_contiennent_que_des_champs_edisables_ou_lectures_seules(self):
        """Régression du 500 sur la fiche Stock (`date_mise_a_jour` auto_now)."""
        problemes = []
        for model, ma in admins_metier():
            ro = ma.readonly_fields if not isinstance(ma.readonly_fields, str) else ()
            ro = set(ro)
            for _, opts in (ma.fieldsets or ()):
                for nom in opts.get('fields', ()):
                    try:
                        champ = model._meta.get_field(nom)
                    except Exception:
                        continue  # champ calculé : c'est un readonly de fait
                    if champ.name in ro or champ.editable or champ.auto_created:
                        continue
                    problemes.append(f'{model._meta.label}.{nom}')
        self.assertEqual(problemes, [], f'champs non éditables dans un fieldset : {problemes}')

    def test_tous_les_fieldsets_se_construisent(self):
        """Django lève `FieldError` si un fieldset est incohérent."""
        erreurs = []
        for model, ma in admins_metier():
            request = self.get_request()
            try:
                ma.get_form(request, None, fields=None, change=False)
            except Exception as exc:
                erreurs.append(f'{model._meta.label}: {exc}')
        self.assertEqual(erreurs, [], '\n'.join(erreurs))

    def test_page_ajout_s_affiche_pour_les_modeles_autorises(self):
        for model, ma in admins_metier():
            opts = model._meta
            url = reverse(f'admin:{opts.app_label}_{opts.model_name}_add')
            with self.subTest(model=opts.label):
                if not ma.has_add_permission(self.get_request()):
                    continue
                reponse = self.client.get(url)
                self.assertEqual(reponse.status_code, 200)
                self.assertContains(reponse, '<form')
                self.assertEqual(reponse.content.count(b'id="jazzy-actions"'), 1)
                self.assertEqual(
                    reponse.content.count(b'class="btn wa-action wa-action--primary"'),
                    1,
                    f'{opts.label} doit afficher une seule action principale',
                )

    def test_formulaire_client_signale_les_champs_obligatoires(self):
        reponse = self.client.get(reverse('admin:clients_client_add'))
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode('utf-8')
        # Django n'applique pas de préfixe aux formulaires de l'admin.
        for champ in ('nom', 'prenom', 'telephone'):
            self.assertIn(f'name="{champ}"', html, f'champ « {champ} » absent du formulaire')
        # Le type de client n'est plus saisi : segments et KPI s'en passent.
        self.assertNotIn('name="type_client"', html)

    def test_le_plafond_de_credit_figure_sur_le_formulaire_unique(self):
        """Un seul formulaire client : le crédit se saisit dès la création."""
        ajout = self.client.get(reverse('admin:clients_client_add')).content.decode('utf-8')
        self.assertIn('name="max_credit"', ajout)

        client = Client.objects.create(
            nom='Rakoto', prenom='Fetra', telephone='0340000001',
        )
        fiche = self.client.get(
            reverse('admin:clients_client_change', args=[client.pk]),
        ).content.decode('utf-8')
        self.assertIn('name="max_credit"', fiche)

    def test_aucune_aide_sur_le_formulaire_reglement(self):
        """La politique est « mots-clés » : aucune phrase sous les champs."""
        reponse = self.client.get(reverse('admin:clients_reglementclient_add'))
        self.assertEqual(reponse.status_code, 200)
        self.assertNotContains(reponse, 'Ne peut pas dépasser le solde dû')
        form = reponse.context['adminform'].form
        self.assertTrue(all(not champ.help_text for champ in form.fields.values()))

    def test_ajout_promotion_est_un_formulaire_unique_et_essentiel(self):
        reponse = self.client.get(reverse('admin:promotions_promotion_add'))

        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode('utf-8')
        self.assertIn('id="promotion_form"', html)
        form = reponse.context['adminform'].form
        champs = set(form.fields)
        self.assertEqual(
            champs,
            {
                'nom', 'type_promotion', 'valeur', 'date_debut', 'date_fin',
                'produits_cibles', 'statut',
            },
        )
        self.assertEqual(
            form.fields['type_promotion'].choices,
            [(Promotion.TypePromotion.POURCENTAGE, 'Pourcentage')],
        )
        self.assertIsInstance(form.fields['type_promotion'].widget, forms.Select)
        self.assertIn('id_type_promotion', html)
        self.assertEqual(form.initial['type_promotion'], Promotion.TypePromotion.POURCENTAGE)
        self.assertEqual(form.fields['valeur'].label, 'Pourcentage de remise (%)')
        self.assertEqual(form.fields['valeur'].max_value, Decimal('100'))
        self.assertEqual(form.fields['valeur'].widget.attrs['max'], '100')
        self.assertIn('0,01–100 %', html)
        self.assertIn('body.wine-quick-create-open.model-promotion.change-form', html)
        self.assertIn('id_date_debut', html)
        self.assertIn('id_date_fin', html)
        self.assertIn('pr-create-actions', html)
        self.assertIn('Enregistrer', html)
        self.assertIn('Annuler', html)
        self.assertEqual(html.count('name="_save"'), 1)
        self.assertNotIn('name="_addanother"', html)
        self.assertNotIn('name="_continue"', html)
        self.assertNotIn('name="type_cible"', html)
        self.assertIn('name="produits_cibles"', html)
        self.assertIsNotNone(form.initial['date_debut'])
        self.assertEqual(
            form.initial['date_fin'] - form.initial['date_debut'],
            timedelta(days=30),
        )

    def test_le_bandeau_promotion_est_le_meme_a_l_ajout_et_a_la_modification(self):
        """Création et modification portent le même en-tête (habillage unifié)."""
        debut = timezone.localtime().replace(second=0, microsecond=0)
        promo = Promotion.objects.create(
            nom='Promo Isaha', type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=Decimal('10.00'), date_debut=debut, date_fin=debut + timedelta(days=10),
        )

        ajout = self.client.get(reverse('admin:promotions_promotion_add')).content.decode()
        fiche = self.client.get(
            reverse('admin:promotions_promotion_change', args=[promo.pk]),
        ).content.decode()

        for html in (ajout, fiche):
            self.assertIn('<section class="pr-create-hero"', html)
            self.assertIn('pr-create-pill', html)
        # Le bandeau nomme la promotion en modification, l'action en création.
        self.assertIn('Nouvelle promotion', ajout)
        self.assertIn('Promo Isaha', fiche)

    def test_le_bandeau_stock_est_le_meme_a_l_ajout_et_a_la_modification(self):
        """Création et modification portent le même en-tête (habillage unifié)."""
        produit = Produit.objects.create(
            nom='Vin Rouge Isaha', volume='75 cl', cout_revenir=8000, prix_vente=15000,
        )
        # Un stock est créé automatiquement à la naissance du produit (signal).
        stock = produit.stock
        stock.quantite = 42
        stock.save(update_fields=['quantite'])

        ajout = self.client.get(reverse('admin:stocks_stock_add')).content.decode()
        fiche = self.client.get(
            reverse('admin:stocks_stock_change', args=[stock.pk]),
        ).content.decode()

        for html in (ajout, fiche):
            self.assertIn('<section class="st-hero"', html)
            self.assertIn('st-hero-pill', html)
        # Le bandeau nomme le vin en modification, l'action en création.
        self.assertIn('Nouveau stock', ajout)
        self.assertIn('Vin Rouge Isaha', fiche)

    def test_ajout_promotion_enregistre_les_champs_essentiels(self):
        debut = timezone.localtime().replace(second=0, microsecond=0)
        fin = debut + timedelta(days=12)
        produit = Produit.objects.create(
            nom='Vin de la promotion', type_vin='Rouge', marque='Domaine',
            cout_revenir=Decimal('5000.00'), prix_vente=Decimal('10000.00'),
            statut=True,
        )

        reponse = self.client.post(
            reverse('admin:promotions_promotion_add'),
            {
                'nom': 'Promotion test',
                'type_promotion': Promotion.TypePromotion.POURCENTAGE,
                'valeur': '10.00',
                'date_debut': debut.strftime('%Y-%m-%dT%H:%M'),
                'date_fin': fin.strftime('%Y-%m-%dT%H:%M'),
                'produits_cibles': [str(produit.pk)],
                'statut': 'on',
                '_save': '1',
            },
        )

        self.assertEqual(
            reponse.status_code,
            302,
            getattr(reponse.context.get('adminform'), 'form', None).errors
            if reponse.context and reponse.context.get('adminform') else reponse.content[:2000],
        )
        promotion = Promotion.objects.get(nom='Promotion test')
        self.assertEqual(promotion.type_promotion, Promotion.TypePromotion.POURCENTAGE)
        self.assertEqual(promotion.valeur, Decimal('10.00'))
        self.assertQuerySetEqual(promotion.produits.all(), [produit], transform=lambda vin: vin)
        self.assertTrue(promotion.statut)
        self.assertEqual(promotion.date_debut, debut)
        self.assertEqual(promotion.date_fin, fin)

    def test_ajout_promotion_refuse_type_fixe_et_pourcentage_superieur_a_100(self):
        debut = timezone.localtime().replace(second=0, microsecond=0)
        donnees = {
            'nom': 'Promotion refusée',
            'valeur': '10.00',
            'date_debut': debut.strftime('%Y-%m-%dT%H:%M'),
            'date_fin': (debut + timedelta(days=5)).strftime('%Y-%m-%dT%H:%M'),
            'statut': 'on',
            '_save': '1',
        }

        for type_promotion, valeur in (
            (Promotion.TypePromotion.MONTANT_FIXE, '10.00'),
            (Promotion.TypePromotion.POURCENTAGE, '100.01'),
        ):
            with self.subTest(type_promotion=type_promotion, valeur=valeur):
                reponse = self.client.post(
                    reverse('admin:promotions_promotion_add'),
                    {**donnees, 'type_promotion': type_promotion, 'valeur': valeur},
                )
                self.assertEqual(reponse.status_code, 200)
                self.assertFalse(Promotion.objects.filter(nom='Promotion refusée').exists())

    def test_aucun_help_text_dans_toute_les_applications(self):
        """Les aides de formulaire ont été retirées partout.

        Le libellé du champ doit se suffire à lui-même : c'est la règle
        adoptée pour l'ensemble du back-office, pas une décision par écran.
        """
        avec_aide = []
        for model in django.apps.apps.get_models():
            # Les apps tierces gardent leurs propres libellés : on ne juge que
            # les modèles écrits pour ce projet.
            if model._meta.app_label not in APPS_DU_PROJET:
                continue
            for champ in model._meta.get_fields():
                if champ.name in CHAMPS_HERITES_CONTRIB:
                    continue
                aide = getattr(champ, 'help_text', '')
                if aide:
                    avec_aide.append(f'{model._meta.label}.{champ.name} → {aide}')
        self.assertEqual(avec_aide, [], f'champs encore aidés : {avec_aide}')

    def test_formulaire_produit_ne_montre_que_les_libelles(self):
        response = self.client.get(reverse('admin:produits_produit_add'))

        self.assertEqual(response.status_code, 200)
        form = response.context['adminform'].form
        self.assertTrue(all(not field.help_text for field in form.fields.values()))
        html = response.content.decode()
        for precision in (
            'Unité vendue en caisse',
            'Saisissez le code du fabricant',
            'Ces informations alimentent la fiche produit',
            'EAN, UPC ou code interne',
            'Prix public par bouteille',
        ):
            self.assertNotIn(precision, html)
        for label in ('Nom', 'Volume', 'Prix de vente', 'Description', 'URL de l’image'):
            self.assertIn(label, html)

    def test_ajout_produit_ne_demande_que_les_champs_de_vente(self):
        """Mettre une bouteille en rayon doit tenir en une seule saisie.

        Les neuf autres onglets (code-barres, fiche de cave, conditionnement)
        sont des attributs de cave : les saisir au moment d'enregistrer une
        vente coûte plus de temps qu'il n'en faut. La catégorie en fait partie :
        on la cherche dans un référentiel déjà rempli, ce n'est pas une
        information que l'on a en tête à cet instant. Le coût de revient non
        plus : il ne sert qu'à la marge, un calcul de gestion qui se fait à
        froid, sur la fiche.
        Tout reste accessible sur la fiche du produit, une fois en rayon.
        """
        ajout = self.client.get(reverse('admin:produits_produit_add'))

        self.assertEqual(ajout.status_code, 200)
        form = ajout.context['adminform'].form
        self.assertEqual(
            set(form.fields),
            {
                'nom', 'type_vin', 'volume', 'prix_vente',
                'image', 'image_url', 'description',
            },
            'la création doit se limiter aux champs de vente',
        )
        html = ajout.content.decode()
        self.assertIn('pd-create-hero', html)
        for absent in (
            'name="cepage"', 'name="code_barre"', 'name="millesime"',
            'name="categorie"', 'name="cout_revenir"',
        ):
            self.assertNotIn(
                absent, html, f'{absent} ne doit pas être demandé à la création'
            )

    def test_le_type_de_vin_propose_les_six_familles_du_domaine(self):
        """La liste de choix est fermée : six familles, pas cinq.

        Trois vins (Rouge, Rose, Blanche) et trois produits dérivés du domaine
        (Apéritif, Eau-de-vie, Liqueur) ; Pétillant et Doux ont disparu du
        référentiel, les cuvées concernées sont reclassées par la migration
        `0011`, puis les familles dérivées par `0012`.
        """
        ajout = self.client.get(reverse('admin:produits_produit_add'))

        self.assertEqual(ajout.status_code, 200)
        familles = ajout.context['adminform'].form.fields['type_vin'].choices
        self.assertEqual(
            [libelle for _, libelle in familles],
            ['Rouge', 'Rose', 'Blanche', 'Apéritif', 'Eau-de-vie', 'Liqueur'],
        )

    def test_les_autres_champs_produit_restent_sur_la_fiche(self):
        """Ce qui est retiré à la création doit rester saisissable après."""
        produit = Produit.objects.create(
            nom='Vin Rouge Isaha', volume='75 cl', cout_revenir=8000, prix_vente=15000,
        )

        fiche = self.client.get(
            reverse('admin:produits_produit_change', args=[produit.pk]),
        )

        self.assertEqual(fiche.status_code, 200)
        html = fiche.content.decode()
        for attendu in (
            'name="code_barre"', 'name="cepage"', 'name="millesime"',
            'name="categorie"', 'name="image"',
        ):
            self.assertIn(attendu, html, f'{attendu} absent de la fiche')
        for label in ('Produit', 'Tarification', 'Code-barres', 'Cave'):
            self.assertIn(label, html)

    def test_le_bandeau_produit_est_le_meme_a_l_ajout_et_a_la_modification(self):
        """Création et modification portent le même en-tête (habillage unifié)."""
        produit = Produit.objects.create(
            nom='Vin Rouge Isaha', volume='75 cl', cout_revenir=8000, prix_vente=15000,
        )

        ajout = self.client.get(reverse('admin:produits_produit_add')).content.decode()
        fiche = self.client.get(
            reverse('admin:produits_produit_change', args=[produit.pk]),
        ).content.decode()

        for html in (ajout, fiche):
            self.assertIn('pd-create-hero', html)
            self.assertIn('pd-create-pill', html)
        # Le bandeau nomme le produit en modification, l'action en création.
        self.assertIn('Nouveau produit', ajout)
        self.assertIn('Vin Rouge Isaha', fiche)

    def test_ajout_produit_enregistre_avec_les_champs_de_vente(self):
        with tempfile.TemporaryDirectory() as dossier:
            with override_settings(MEDIA_ROOT=dossier), patch(
                'apps.produits.admin.telecharger_image',
                return_value=('photo.png', ContentFile(b'image')),
            ):
                reponse = self.client.post(
                    reverse('admin:produits_produit_add'),
                    {
                        'nom': 'Vin Blanc Sec',
                        'type_vin': 'Blanche',
                        'volume': '75 cl',
                        'prix_vente': '15000.00',
                        'description': 'Cuvée du domaine, notes de fruits blancs.',
                        'image_url': 'https://exemple.com/photo.png',
                        '_save': 'Enregistrer',
                    },
                )

        self.assertEqual(reponse.status_code, 302)
        produit = Produit.objects.get(nom='Vin Blanc Sec')
        self.assertEqual(produit.volume, '75 cl')
        self.assertEqual(produit.prix_vente, Decimal('15000.00'))
        self.assertEqual(
            produit.description, 'Cuvée du domaine, notes de fruits blancs.'
        )
        # Le coût de revient n'est plus demandé à la création : la fiche part
        # de zéro et la marge se règle plus tard, à froid.
        self.assertEqual(produit.cout_revenir, Decimal('0.00'))
        # Le signal `post_save` doit avoir ouvert la ligne de stock à zéro.
        self.assertEqual(produit.stock.quantite, 0)

    def test_la_photo_est_obligatoire_a_la_creation(self):
        """Sans fichier ni URL, la création est refusée et rien n'est enregistré."""
        reponse = self.client.post(
            reverse('admin:produits_produit_add'),
            {
                'nom': 'Vin sans photo',
                'type_vin': 'Rouge',
                'volume': '75 cl',
                'prix_vente': '15000.00',
                '_save': 'Enregistrer',
            },
        )

        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'Ajoutez une photo')
        self.assertFalse(Produit.objects.filter(nom='Vin sans photo').exists())

    def test_la_creation_propose_un_apercu_de_la_photo(self):
        """Le formulaire de création met en place l'aperçu de la photo."""
        ajout = self.client.get(reverse('admin:produits_produit_add'))

        self.assertEqual(ajout.status_code, 200)
        html = ajout.content.decode()
        self.assertIn('pd-image-preview', html)
        self.assertIn('Aperçu de la photo', html)

    def test_l_image_peut_etre_importee_depuis_une_adresse(self):
        """Le lien fourni est rapatrié dans le champ image.

        Le catalogue n'a ainsi qu'une seule source de photo : la fiche, la
        caisse et le site lisent le même fichier, et la vignette survit à la
        disparition du lien d'origine.
        """
        with tempfile.TemporaryDirectory() as dossier:
            with override_settings(MEDIA_ROOT=dossier), patch(
                'apps.produits.admin.telecharger_image',
                return_value=('photo.png', ContentFile(b'image')),
            ):
                reponse = self.client.post(
                    reverse('admin:produits_produit_add'),
                    {
                        'nom': 'Vin avec photo',
                        'type_vin': 'Rouge',
                        'volume': '75 cl',
                        'prix_vente': '15000.00',
                        'image_url': 'https://exemple.com/photo.png',
                        '_save': 'Enregistrer',
                    },
                )

                self.assertEqual(reponse.status_code, 302)
                produit = Produit.objects.get(nom='Vin avec photo')
                self.assertTrue(produit.image.name.startswith('produits/'))
                self.assertTrue(os.path.exists(produit.image.path))

    def test_une_adresse_d_image_injoignable_est_signalee_sur_le_champ(self):
        """Un lien mort se dit sous le champ, il ne fait pas échouer la page."""
        with patch(
            'apps.produits.admin.telecharger_image',
            side_effect=ImageDistanteInvalide(
                "Le lien est injoignable. Vérifiez l'adresse."
            ),
        ):
            reponse = self.client.post(
                reverse('admin:produits_produit_add'),
                {
                    'nom': 'Vin sans photo',
                    'type_vin': 'Rouge',
                    'volume': '75 cl',
                    'prix_vente': '15000.00',
                    'image_url': 'https://exemple.com/photo.png',
                    '_save': 'Enregistrer',
                },
            )

        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'injoignable')
        self.assertFalse(Produit.objects.filter(nom='Vin sans photo').exists())

    def test_ajout_produit_dans_la_fenetre_rapide_renvoie_la_confirmation_popup(self):
        with tempfile.TemporaryDirectory() as dossier:
            with override_settings(MEDIA_ROOT=dossier), patch(
                'apps.produits.admin.telecharger_image',
                return_value=('photo.png', ContentFile(b'image')),
            ):
                reponse = self.client.post(
                    reverse('admin:produits_produit_add'),
                    {
                        'nom': 'Vin rapide',
                        'type_vin': 'Rose',
                        'volume': '75 cl',
                        'prix_vente': '15000.00',
                        'image_url': 'https://exemple.com/photo.png',
                        '_save': 'Enregistrer',
                        '_popup': '1',
                    },
                )

        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'django-admin-popup-response-constants')
        self.assertTrue(Produit.objects.filter(nom='Vin rapide').exists())

    def test_enregistrer_et_ajouter_un_autre_reste_sur_la_creation(self):
        with tempfile.TemporaryDirectory() as dossier:
            with override_settings(MEDIA_ROOT=dossier), patch(
                'apps.produits.admin.telecharger_image',
                return_value=('photo.png', ContentFile(b'image')),
            ):
                reponse = self.client.post(
                    reverse('admin:produits_produit_add'),
                    {
                        'nom': 'Vin série',
                        'type_vin': 'Rouge',
                        'volume': '75 cl',
                        'prix_vente': '15000.00',
                        'image_url': 'https://exemple.com/photo.png',
                        '_addanother': '',
                    },
                )

        self.assertRedirects(
            reponse,
            reverse('admin:produits_produit_add'),
            fetch_redirect_response=False,
        )
        self.assertTrue(Produit.objects.filter(nom='Vin série').exists())

    def test_clients_ont_recherche_filtres_et_tris(self):
        ma = dj_admin.site._registry[Client]
        for attr in ('search_fields', 'list_filter', 'ordering'):
            with self.subTest(attribut=attr):
                self.assertTrue(getattr(ma, attr, None), f'Client.{attr} est vide')

    def test_la_liste_clients_n_a_plus_de_bandeau_de_selection(self):
        """Les segments et KPI remplacent le bandeau : plus de `date_hierarchy`
        et plus de menu déroulant de critères dans la barre de recherche."""
        ma = dj_admin.site._registry[Client]
        self.assertIsNone(ma.date_hierarchy, 'le drill-down par date doit être retiré')
        gabarit = (
            Path(__file__).resolve().parent.parent / 'templates' / ma.change_list_template
        ).read_text(encoding='utf-8')
        self.assertIn('{% block filters %}{% endblock %}', gabarit)
        self.assertIn('{% block date_hierarchy %}{% endblock %}', gabarit)
        # Les critères restent déclarés : sans eux, les URL des segments
        # seraient vidées par Django (redirection 302).
        parametres = {
            f if isinstance(f, str) else f.parameter_name for f in ma.list_filter
        }
        self.assertLessEqual(
            {'fidelite', 'credit_ouvert', 'inactif_90j', 'solde_due'}, parametres
        )

    def test_les_listes_utilisent_des_composants_de_la_charte(self):
        """Chaque liste métier doit exposer au moins un composant partagé."""
        for model, ma in admins_metier():
            if not ma.has_view_permission(self.get_request()):
                continue
            opts = model._meta
            with self.subTest(model=opts.label):
                reponse = self.client.get(
                    reverse(f'admin:{opts.app_label}_{opts.model_name}_changelist')
                )
                self.assertEqual(reponse.status_code, 200)
                self.assertContains(reponse, 'wineadmin-design.css')

    def test_chaque_action_de_masse_a_un_libelle_lisible(self):
        """Une action doit s'afficher avec un libellé français, pas `exporter_csv`."""
        problemes = []
        for model, ma in admins_metier():
            actions = ma.get_actions(self.get_request())
            for nom, action in actions.items():
                if nom == 'delete_selected':
                    continue  # action globale de Django
                # Django 5 renvoie un objet Action (nom, fonction, description) ;
                # les versions antérieures renvoient la fonction brute.
                description = (
                    getattr(action, 'description', None)
                    or getattr(action, 'short_description', '')
                    or ''
                )
                if not description or '_' in description or description == nom:
                    problemes.append(f'{model._meta.label}.{nom} → {description!r}')
        self.assertEqual(problemes, [], f'actions sans libellé propre : {problemes}')

    def test_les_actions_de_masse_sont_proposees(self):
        """Une action déclarée doit apparaître dans le sélecteur d'actions."""
        for model, ma in admins_metier():
            actions = [n for n in ma.get_actions(self.get_request()) if n != 'delete_selected']
            if not actions:
                continue
            opts = model._meta
            reponse = self.client.get(
                reverse(f'admin:{opts.app_label}_{opts.model_name}_changelist')
            )
            with self.subTest(model=opts.label):
                self.assertEqual(reponse.status_code, 200)
                if not reponse.context['cl'].result_count:
                    self.skipTest('liste vide : le sélecteur d\'actions n\'est pas rendu')
                for nom in actions:
                    self.assertContains(reponse, f'value="{nom}"')


class PagesImpressionTests(TestCase):
    """Les pages imprimées (étiquettes, POS, Z-Report) ne doivent pas casser."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123',
        )
        self.client.force_login(self.admin)

    def test_etiquettes_ignore_les_produits_sans_code_barres(self):
        """Régression : `exclude(code_barre='')` laissait passer les NULL (500)."""
        sans_code = Produit.objects.create(
            nom='Vin sans code', code_barre=None, cout_revenir=1000, prix_vente=2000,
        )
        avec_code = Produit.objects.create(
            nom='Vin avec code', code_barre='2000000000017', cout_revenir=1000, prix_vente=2000,
        )
        reponse = self.client.get(reverse('admin:produits_etiquettes'))
        self.assertEqual(reponse.status_code, 200)
        # On regarde la planche d'étiquettes, pas la page entière : un produit en
        # rupture apparaît aussi dans les notifications de la barre du haut.
        planche = reponse.content.decode().split('<div class="etiquettes">')[1]
        self.assertNotIn(sans_code.nom, planche)
        self.assertIn(avec_code.nom, planche)

    def test_etiquettes_avec_selection_explicite(self):
        """Une sélection contenant un produit sans code ne doit pas casser."""
        sans_code = Produit.objects.create(
            nom='Vin selectionne sans code', code_barre=None, cout_revenir=1000, prix_vente=2000,
        )
        reponse = self.client.get(
            reverse('admin:produits_etiquettes'), {'ids': [sans_code.pk]}
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'aucun code-barres')
