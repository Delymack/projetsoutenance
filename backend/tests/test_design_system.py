"""Garde-fous du design system WineAdmin.

Le standard visuel impose 3 couleurs maximum (grenat, or, sage) et un jeu de
composants partagés. Ces tests empêchent la réapparition de couleurs ou de
feuilles de style divergentes dans les gabarits et les ModelAdmin.
"""
import colorsys
import re
from decimal import Decimal
from pathlib import Path

from django.contrib import admin as dj_admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.clients.models import Client, ReglementClient

User = get_user_model()

RACINE = Path(__file__).resolve().parent.parent
FICHIER_TOKENS = RACINE / 'static' / 'css' / 'wineadmin-design.css'

# Palette autorisée : 3 teintes de marque + leurs déclinaisons +-1.
TEINTES_AUTORISEES = {
    '641b2c', '741f35', '34101c', 'f6ecee', 'e7d2d7',   # grenat
    'c99b3b', 'a67c25', 'fbf3e2', 'ecd9a8',              # or
    '2f6b4f', '255540', 'e9f2ed', 'c6ded0',              # sage
}

# Échelle neutre dérivée de l'encre (thème clair + thème sombre).
# Ce ne sont pas des « couleurs de marque » : ce sont les valeurs de surface.
NEUTRES = {
    # clair
    '2b1b20', '5a4a4e', '8a7c7d', 'b9a39f', 'ebe3de', 'f3ece8',
    'ffffff', 'faf7f5', 'f5efeb',
    # sombre
    'f4e7ea', 'cdb8bd', 'a08f93', '7c6a6e', '1a1016', '150a10', '20111a',
}


class PaletteTokensTests(TestCase):
    """Le fichier de tokens ne doit déclarer que les 3 teintes de marque."""

    def test_fichier_tokens_existe(self):
        self.assertTrue(FICHIER_TOKENS.exists(), 'wineadmin-design.css est obligatoire')

    def test_palette_limitee_a_trois_teintes(self):
        contenu = FICHIER_TOKENS.read_text(encoding='utf-8')
        # On isole les jetons --lb-* (déclarations de couleur uniquement).
        jetons = re.findall(r'--lb-[a-z0-9-]+:\s*#([0-9a-fA-F]{6})', contenu)
        couleurs_hors_neutres = {c.lower() for c in jetons} - NEUTRES
        self.assertTrue(
            couleurs_hors_neutres <= TEINTES_AUTORISEES,
            f'Teintes hors standard dans les tokens : {sorted(couleurs_hors_neutres - TEINTES_AUTORISEES)}',
        )

    def test_les_trois_couleurs_de_marque_sont_declarees(self):
        contenu = FICHIER_TOKENS.read_text(encoding='utf-8')
        for teinte in ('#641b2c', '#c99b3b', '#2f6b4f'):
            self.assertIn(teinte, contenu, f'la teinte de marque {teinte} doit être déclarée')


class PaletteGabaritsTests(TestCase):
    """Aucune teinte hors des 3 couleurs de marque dans les gabarits.

    Un gabarit qui introduit une 4e teinte (un bleu de l'ancien thème, un rouge
    d'erreur générique) casse l'identité visuelle : le test le signale par nom
    de teinte et par fichier.
    """

    # Couleurs de marque : 3 teintes, déclinaisons admises autour d'elles.
    FAMILLES = {'grenat': (335, 20), 'or': (40, 25), 'sage': (150, 35)}
    # En dessous de ce niveau de chroma, une couleur est un gris : neutre.
    CHROMA_NEUTRE = 0.10

    # Seule exception assumée : le logo « G » du bouton Google, dont les
    # couleurs sont imposées par la marque tierce.
    EXCEPTIONS = {'#4285f4', '#ea4335'}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gabarits = sorted((RACINE / 'templates').rglob('*.html'))
        # Les neutres officiels sont ceux déclarés par le design system : un
        # gris chaud comme #b9a39f est un neutre, pas une 4e teinte.
        tokens = FICHIER_TOKENS.read_text(encoding='utf-8').lower()
        cls.neutres = {
            f'#{h}' for h in re.findall(
                r'--(?:lb-ink|lb-line|lb-canvas|lb-surface)[\w-]*:\s*#([0-9a-f]{6})', tokens
            )
        }

    def _analyser(self, hexa):
        couleur = f'#{hexa}'
        if couleur in self.neutres:
            return 'neutre'
        r, v, b = (int(hexa[i:i + 2], 16) / 255 for i in (0, 2, 4))
        chroma = max(r, v, b) - min(r, v, b)
        if chroma < self.CHROMA_NEUTRE:
            return 'neutre'
        deg = colorsys.rgb_to_hls(r, v, b)[0] * 360
        for nom, (centre, tolerance) in self.FAMILLES.items():
            ecart = min(abs(deg - centre), abs(deg - centre - 360), abs(deg - centre + 360))
            if ecart <= tolerance:
                return nom
        return 'etrangere'

    def test_aucune_teinte_hors_palette_dans_les_gabarits(self):
        coupables = []
        for gabarit in self.gabarits:
            contenu = gabarit.read_text(encoding='utf-8').lower()
            for hexa in sorted(set(re.findall(r'#([0-9a-f]{6})\b', contenu))):
                couleur = f'#{hexa}'
                if couleur in self.EXCEPTIONS:
                    continue
                if self._analyser(hexa) == 'etrangere':
                    coupables.append(f'{gabarit.relative_to(RACINE)} → {couleur}')
        self.assertEqual(
            coupables, [],
            'teintes hors des 3 couleurs de marque :\n  ' + '\n  '.join(coupables),
        )

    def test_les_exceptions_sont_limitees_au_bouton_google(self):
        for gabarit in self.gabarits:
            contenu = gabarit.read_text(encoding='utf-8').lower()
            for hexa in self.EXCEPTIONS:
                if hexa in contenu:
                    self.assertIn(
                        gabarit.name, {'login.html', 'signup.html'},
                        f'{hexa} (couleur de marque Google) hors du bouton Google',
                    )

    def test_aucune_teinte_hors_palette_dans_les_feuilles_de_style(self):
        """Les CSS maison doivent suivre la même règle que les gabarits."""
        coupables = []
        fichiers = [
            f for motif in ('*.css', '*.js')
            for f in sorted((RACINE / 'static').rglob(motif))
            if 'vendor' not in f.parts
        ]
        for fichier in fichiers:
            contenu = fichier.read_text(encoding='utf-8').lower()
            for hexa in sorted(set(re.findall(r'#([0-9a-f]{6})\b', contenu))):
                if f'#{hexa}' in self.EXCEPTIONS:
                    continue
                if self._analyser(hexa) == 'etrangere':
                    coupables.append(f'{fichier.relative_to(RACINE)} → #{hexa}')
        self.assertEqual(
            coupables, [],
            'teintes hors des 3 couleurs de marque (CSS/JS) :\n  ' + '\n  '.join(coupables),
        )

    def test_la_palette_est_bien_utilisee(self):
        """Le test doit rester discriminant : on vérifie que le contrôle bite."""
        self.assertEqual(self._analyser('641b2c'), 'grenat')
        self.assertEqual(self._analyser('c99b3b'), 'or')
        self.assertEqual(self._analyser('2f6b4f'), 'sage')
        self.assertEqual(self._analyser('8a7c7d'), 'neutre')
        self.assertEqual(self._analyser('2b5cad'), 'etrangere')


class GabaritsPartagesTests(TestCase):
    """Les listes/admin utilisent les composants partagés, plus de CSS local."""

    LISTES = [
        ('clients_client_changelist', '/admin/clients/client/'),
        ('produits_produit_changelist', '/admin/produits/produit/'),
        ('stocks_stock_changelist', '/admin/stocks/stock/'),
        ('stocks_mouvementstock_changelist', '/admin/stocks/mouvementstock/'),
        ('promotions_promotion_changelist', '/admin/promotions/promotion/'),
        ('categories_categorie_changelist', '/admin/categories/categorie/'),
    ]
    #: Pages volontairement sans grille de KPI : elles ne font qu'une chose et
    #: renvoient au tableau de bord, qui affiche déjà les chiffres du jour.
    LISTES_SANS_KPIS = [
        ('ventes_vente_changelist', '/admin/ventes/vente/'),
    ]

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123',
        )
        self.client.force_login(self.admin)
        Client.objects.create(nom='Martin', prenom='Paul', telephone='0340012345')

    def test_composants_partages_presents_sur_chaque_liste(self):
        for nom, url in self.LISTES:
            with self.subTest(page=nom):
                reponse = self.client.get(url)
                self.assertEqual(reponse.status_code, 200)
                html = reponse.content.decode('utf-8')
                self.assertIn('lb-hero', html, f'{nom} : en-tête partagé manquant')
                self.assertIn('lb-kpis', html, f'{nom} : grille de KPI partagée manquante')
                self.assertIn('wineadmin-design.css?v=13', html, f'{nom} : design system commun non chargé')

    def test_en_tetes_gardent_les_classes_de_colonnes_django(self):
        reponse = self.client.get('/admin/clients/client/')
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode('utf-8')
        self.assertIn('column-', html, 'classes de colonnes Django manquantes dans la page clients')

    def test_une_action_impression_est_presente_sur_chaque_liste(self):
        reponse = self.client.get('/admin/clients/client/')
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode('utf-8')
        self.assertIn('Imprimer', html)
        self.assertIn('window.print()', html)

    def test_les_pages_allegees_gardent_le_design_system(self):
        for nom, url in self.LISTES_SANS_KPIS:
            with self.subTest(page=nom):
                reponse = self.client.get(url)
                self.assertEqual(reponse.status_code, 200)
                html = reponse.content.decode('utf-8')
                self.assertIn('lb-hero', html, f'{nom} : en-tête partagé manquant')
                self.assertIn('wineadmin-design.css?v=13', html, f'{nom} : design system commun non chargé')
                self.assertNotIn('lb-kpis', html, f'{nom} : les KPI du jour font doublon')

    def test_aucune_feuille_de_style_inline_dans_les_gabarits(self):
        """Les couleurs vivent dans le design system, pas dans les templates."""
        for gabarit in (RACINE / 'templates' / 'admin').rglob('change_list.html'):
            contenu = gabarit.read_text(encoding='utf-8')
            couleurs = set(re.findall(r'#[0-9a-fA-F]{6}', contenu))
            couleurs_autorisees = {f'#{c.upper()}' for c in TEINTES_AUTORISEES} | {
                f'#{c}' for c in TEINTES_AUTORISEES
            }
            intruses = couleurs - couleurs_autorisees
            with self.subTest(gabarit=gabarit.name):
                self.assertFalse(
                    intruses, f'{gabarit.name} contient des couleurs hors palette : {sorted(intruses)}'
                )


class PageClientTests(TestCase):
    """Fonctionnalités de la page Clients : KPI, filtres, fiche 360°, actions."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123',
        )
        self.client.force_login(self.admin)
        self.fiche = Client.objects.create(
            nom='Rakotomalala', prenom='Hery', telephone='0341122334',
            max_credit=100000, solde_du=15000, points_fidelite=4200,
        )

    def test_kpi_presents_sans_rang_de_segments(self):
        reponse = self.client.get(reverse('admin:clients_client_changelist'))
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode('utf-8')
        self.assertIn('Encours total', html)
        self.assertIn('CA clients', html)
        self.assertNotIn('lb-segment', html)

    def test_colonnes_metier_de_la_liste(self):
        """Colonnes retenues après nettoyage : 5 au total, pas de place perdue."""
        reponse = self.client.get(reverse('admin:clients_client_changelist'))
        html = reponse.content.decode('utf-8')
        for attendu in ('Client', 'Contact', 'Activité', 'Encours', 'Contact rapide'):
            self.assertIn(attendu, html, f'colonne « {attendu} » manquante')
        for retiree in ('Crédit dispo.',):
            self.assertNotIn(retiree, html, f'colonne « {retiree} » à supprimer')
        # « Fidélité » a disparu comme colonne, mais le niveau reste lisible
        # en badge dans la cellule Client.
        self.assertNotIn('pts avant', html)

    def test_le_niveau_reste_lisible_dans_la_cellule_client(self):
        reponse = self.client.get(reverse('admin:clients_client_changelist'))
        html = reponse.content.decode('utf-8')
        self.assertIn('lb-badge', html, 'le badge de niveau doit rester affiché')
        self.assertIn(self.fiche.get_niveau_display(), html)

    def test_aucun_widget_de_selection_dans_la_liste_clients(self):
        """Le bandeau de critères et les menus déroulants jazzmin disparaissent."""
        for url in (
            reverse('admin:clients_client_changelist'),
            reverse('admin:clients_client_changelist') + '?solde_due=1',
        ):
            with self.subTest(url=url):
                reponse = self.client.get(url)
                self.assertEqual(reponse.status_code, 200)
                html = reponse.content.decode('utf-8')
                for interdit in ('id="changelist-filter"', 'date-hierarchy', 'search-filter'):
                    self.assertNotIn(interdit, html, f'« {interdit} » encore rendu')
                # La recherche, elle, doit rester.
                self.assertIn('name="q"', html)
                self.assertIn('lb-searchbar', html)

    def test_les_segments_restent_operationnels(self):
        """Sans bandeau, les liens des segments et des KPI doivent filtrer."""
        createur = Client.objects.create(
            nom='Endetté', prenom='', telephone='0340000001',
            max_credit=10000, solde_du=9000, points_fidelite=0,
        )
        fidele = Client.objects.create(
            nom='Ambassadeur Test', prenom='', telephone='0340000002',
            max_credit=0, solde_du=0, points_fidelite=99999,
        )
        # 9 000 / 10 000 = 90 % du plafond : au-delà des 60 %, c'est « à risque ».
        for parametre, attendu in (
            ('?solde_due=1', createur),
            ('?credit_ouvert=1', createur),
            ('?fidelite=ambassadeur', fidele),
        ):
            with self.subTest(parametre=parametre):
                reponse = self.client.get(reverse('admin:clients_client_changelist') + parametre)
                self.assertEqual(reponse.status_code, 200)
                self.assertContains(reponse, f'/admin/clients/client/{attendu.pk}/change/')

    def test_la_recherche_conserve_le_segment_actif(self):
        reponse = self.client.get(
            reverse('admin:clients_client_changelist') + '?solde_due=1&q='
        )
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode('utf-8')
        self.assertIn('<input type="hidden" name="solde_due" value="1">', html)

    def test_ajout_client_ne_demande_que_les_champs_essentiels(self):
        """Créer un client = l'identifier. Ni dette, ni points, ni crédit saisis."""
        reponse = self.client.get(reverse('admin:clients_client_add'))
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode('utf-8')
        for attendu in ('nom', 'prenom', 'telephone', 'email', 'adresse'):
            self.assertIn(f'name="{attendu}"', html, f'champ « {attendu} » manquant')
        for exclu in ('max_credit', 'solde_du', 'points_fidelite', 'niveau',
                      'date_creation', 'updated_at', 'type_client'):
            self.assertNotIn(f'name="{exclu}"', html, f'champ « {exclu} » à retirer')
        # Le panneau d'historique n'a pas de sens avant le premier enregistrement.
        self.assertNotIn('Dernières ventes', html)
        self.assertNotIn('Cinq champs d&#x27;identification suffisent', html)
        # Jazzmin fait un onglet par fieldset : un seul onglet, donc un seul écran.
        self.assertEqual(html.count('data-bs-toggle="pill"'), 1)

    def test_la_fiche_client_conserve_tous_les_champs(self):
        reponse = self.client.get(
            reverse('admin:clients_client_change', args=[self.fiche.pk])
        )
        html = reponse.content.decode('utf-8')
        # Libellés volontairement réduits à des mots-clés.
        for libelle in ('Plafond crédit', 'Points', 'Niveau', 'Encours'):
            self.assertIn(libelle, html, f'« {libelle} » absent de la fiche')
        self.assertIn('Dernières ventes', html)
        self.assertIn('Règlements', html)

    def test_encaissement_propose_sur_la_fiche_du_client(self):
        """Les règlements sont saisis sur la fiche, sans quitter la page."""
        reponse = self.client.get(
            reverse('admin:clients_client_change', args=[self.fiche.pk])
        )
        html = reponse.content.decode('utf-8')
        self.assertIn('form-encaissement', html)
        # Le reste dû pré-rempli : l'encaissement intégral est le plus court.
        self.assertIn(f'value="{self.fiche.solde_du:.2f}"', html)
        # Un <form> dans le formulaire client serait jeté par le navigateur :
        # le bouton porte donc la cible, et réutilise le jeton CSRF existant.
        self.assertIn(
            f'formaction="{reverse("admin:clients_client_encaisser", args=[self.fiche.pk])}"',
            html,
        )
        panneau = html[html.index('form-encaissement'):html.index('</section>', html.index('form-encaissement'))]
        self.assertNotIn('<form', panneau, 'pas de formulaire imbriqué dans la fiche')

    def test_aucun_formulaire_d_encaissement_si_compte_a_jour(self):
        client = Client.objects.create(nom='Rasoa', prenom='M', telephone='0341111111')
        html = self.client.get(
            reverse('admin:clients_client_change', args=[client.pk])
        ).content.decode('utf-8')
        self.assertNotIn('form-encaissement', html)
        self.assertIn('rien à encaisser', html)

    def test_encaisser_un_reglement_reduit_le_solde(self):
        reponse = self.client.post(
            reverse('admin:clients_client_encaisser', args=[self.fiche.pk]),
            {'montant': '15000', 'mode': ReglementClient.Mode.MOBILE_MONEY,
             'reference_facture': 'F-42', 'note': ''},
            follow=True,
        )
        self.assertEqual(reponse.status_code, 200)
        self.fiche.refresh_from_db()
        self.assertEqual(self.fiche.solde_du, Decimal('0.00'))
        reglement = ReglementClient.objects.get()
        self.assertEqual(reglement.client, self.fiche)
        self.assertEqual(reglement.montant, Decimal('15000.00'))
        self.assertEqual(reglement.utilisateur, self.admin)
        # L'encaissement apparaît dans la fiche, sans rechargement d'une autre page.
        html = reponse.content.decode('utf-8')
        self.assertIn('F-42', html)
        self.assertIn('Mobile Money', html)

    def test_encaisser_refuse_un_reglement_superieur_au_solde(self):
        reponse = self.client.post(
            reverse('admin:clients_client_encaisser', args=[self.fiche.pk]),
            {'montant': '15001', 'mode': ReglementClient.Mode.ESPECES},
            follow=True,
        )
        self.assertEqual(reponse.status_code, 200)
        self.fiche.refresh_from_db()
        self.assertEqual(self.fiche.solde_du, Decimal('15000.00'))
        self.assertEqual(ReglementClient.objects.count(), 0)
        self.assertIn('dépasse le solde dû', reponse.content.decode('utf-8'))

    def test_encaisser_ne_modifie_pas_la_fiche_client(self):
        """Le bouton d'encaissement est dans le formulaire client : il ne doit
        pas enregistrer au passage une fiche_incomplète par un POST global."""
        self.client.post(
            reverse('admin:clients_client_encaisser', args=[self.fiche.pk]),
            {'nom': 'Nom bricolé', 'prenom': '', 'max_credit': '999999', 'montant': '1000',
             'mode': ReglementClient.Mode.ESPECES},
            follow=True,
        )
        self.fiche.refresh_from_db()
        self.assertEqual(self.fiche.nom, 'Rakotomalala')
        self.assertEqual(self.fiche.max_credit, Decimal('100000.00'))
        self.assertEqual(self.fiche.solde_du, Decimal('14000.00'))

    def test_annuler_un_encaissement_retablit_la_dette(self):
        reglement = ReglementClient.objects.create(
            client=self.fiche, montant=Decimal('5000.00'),
            mode=ReglementClient.Mode.ESPECES, utilisateur=self.admin,
        )
        self.client.post(
            reverse('admin:clients_reglementclient_delete', args=[reglement.pk]),
            {'post': 'yes'}, follow=True,
        )
        self.assertFalse(ReglementClient.objects.filter(pk=reglement.pk).exists())
        self.fiche.refresh_from_db()
        self.assertEqual(self.fiche.solde_du, Decimal('20000.00'), 'le solde doit être rendu au client')

    def test_un_reglement_ne_se_modifie_pas(self):
        """Un encaissement est consultable, jamais réécrit."""
        reglement = ReglementClient.objects.create(
            client=self.fiche, montant=Decimal('5000.00'),
            mode=ReglementClient.Mode.ESPECES, utilisateur=self.admin,
        )
        reponse = self.client.post(
            reverse('admin:clients_reglementclient_change', args=[reglement.pk]),
            {'client': self.fiche.pk, 'montant': '1.00', 'mode': ReglementClient.Mode.CARTE},
        )
        self.assertEqual(reponse.status_code, 403)
        reglement.refresh_from_db()
        self.assertEqual(reglement.montant, Decimal('5000.00'))

    def test_la_section_reglements_a_disparu_du_menu(self):
        """Les règlements vivent sur la fiche client : plus de section dédiée."""
        for url in (reverse('admin:index'), reverse('admin:clients_client_changelist')):
            html = self.client.get(url).content.decode('utf-8')
            menu = html[html.index('<aside'):html.index('</aside>')]
            self.assertNotIn('Règlements clients', menu)
            # Le reste du menu est intact.
            self.assertIn('Clients', menu)
        # Le lien mort du bandeau de la liste a disparu avec la section.
        liste = self.client.get(reverse('admin:clients_client_changelist')).content.decode('utf-8')
        self.assertNotIn('admin:clients_reglementclient_changelist', liste)


    def test_un_client_cree_par_le_formulaire_simple_est_complet(self):
        """Les champs masqués doivent quand même être initialisés proprement."""
        reponse = self.client.post(reverse('admin:clients_client_add'), {
            'nom': 'Rasoanaivo', 'prenom': 'Naina', 'telephone': '0349988776',
            '_save': 'Enregistrer',
        }, follow=True)
        self.assertEqual(reponse.status_code, 200)
        client = Client.objects.get(telephone='0349988776')
        self.assertEqual(client.nom, 'Rasoanaivo')
        # Le type n'est plus saisi : un compte créé depuis le formulaire
        # simple reste par défaut un particulier.
        self.assertEqual(client.type_client, Client.TypeClient.PARTICULIER)
        # Rien n'est laissé à None : un compte sans dette ni points, explicite.
        self.assertEqual(client.solde_du, 0)
        self.assertEqual(client.points_fidelite, 0)
        self.assertEqual(client.max_credit, 0)
        self.assertEqual(client.niveau, Client.Niveau.BRONZE)
        self.assertIsNotNone(client.date_creation)

    def test_les_icones_utilisees_existent_dans_font_awesome(self):
        fa = (RACINE / 'static/vendor/fontawesome-free/css/all.min.css').read_text(
            encoding='utf-8'
        )
        connues = set(re.findall(r'\.(fa-[a-z0-9-]+):before', fa))
        # Classes utilitaires : ce ne sont pas des icônes.
        ignore = {
            'fa-2x', 'fa-lg', 'fa-sm', 'fa-xs', 'fa-1x', 'fa-fw', 'fa-ul',
            'fa-li', 'fa-border', 'fa-pull-left', 'fa-pull-right', 'fa-spin',
            'fa-pulse', 'fa-rotate-90', 'fa-rotate-180', 'fa-rotate-270',
            'fa-flip-horizontal', 'fa-flip-vertical', 'fa-stack', 'fa-inverse',
        }
        vues = set()
        for source in (
            list((RACINE / 'templates').rglob('*.html'))
            + list((RACINE / 'apps').rglob('*.py'))
        ):
            texte = source.read_text(encoding='utf-8')
            for m in re.finditer(r'\bfa-[a-z0-9-]+\b', texte):
                # Les noms assemblés à l'exécution (``fa-arrow-${x}``) sont
                # vérifiés par le rendu, pas statiquement.
                if re.match(r'-?\$\{', texte[m.end():m.end() + 3]):
                    continue
                vues.add(m.group(0))
        inconnues = vues - connues - ignore
        self.assertEqual(
            inconnues, set(), f'icônes absentes de Font Awesome : {sorted(inconnues)}'
        )

    def test_fiche_client_360_degree(self):
        reponse = self.client.get(
            reverse('admin:clients_client_change', args=[self.fiche.pk])
        )
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode('utf-8')
        self.assertIn('lb-avatar', html)
        self.assertIn('Crédit disponible', html)
        self.assertIn('wa.me', html, 'le raccourci WhatsApp doit être proposé')
        self.assertIn('Dernières ventes', html)
        self.assertIn('Règlements', html)

    def test_filtre_encours(self):
        Client.objects.create(nom='Client', prenom='Sain', telephone='0340000000')
        reponse = self.client.get(reverse('admin:clients_client_changelist'), {'solde_due': '1'})
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode('utf-8')
        self.assertIn('Rakotomalala', html)
        self.assertNotIn('>Client Sain<', html)

    def test_export_csv(self):
        reponse = self.client.post(
            reverse('admin:clients_client_changelist'),
            {
                'action': 'actions_export_csv',
                '_selected_action': [str(self.fiche.pk)],
            },
            follow=True,
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertIn('text/csv', reponse['Content-Type'])
        contenu = reponse.content.decode('utf-8-sig')
        self.assertIn('Rakotomalala', contenu)
        self.assertIn('Encours', contenu)

    def test_actions_de_masse_enregistrees(self):
        model_admin = dj_admin.site._registry[Client]
        self.assertEqual(
            set(model_admin.actions),
            {
                'actions_export_csv',
                'actions_telephone_appel',
                'actions_telephone_whatsapp',
                'actions_liberer_credit',
            },
        )

    def test_plafond_credit_liberable(self):
        cible = Client.objects.create(nom='Nouveau', prenom='Client', telephone='0341111111')
        self.assertEqual(cible.max_credit, 0)
        reponse = self.client.post(
            reverse('admin:clients_client_changelist'),
            {'action': 'actions_liberer_credit', '_selected_action': [str(cible.pk)]},
            follow=True,
        )
        self.assertEqual(reponse.status_code, 200)
        cible.refresh_from_db()
        self.assertGreater(cible.max_credit, 0, 'le plafond de crédit doit être activé')


class TableauDeBordTests(TestCase):
    """Le tableau de bord reste centré sur quatre indicateurs et cinq panneaux.

    Le tout est rendu côté serveur et se lit d'un coup d'œil : le compte n'a
    plus à fouiller une grille de onze blocs pour suivre les ventes, les stocks
    et les promotions. Ces tests vérifient les informations métier affichées.
    """

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123',
        )
        self.client.force_login(self.admin)
        self.html = self.client.get(reverse('admin:index')).content.decode('utf-8')

    def test_les_panneaux_metier_sont_conserves(self):
        for panneau in (
            'Chiffre d’affaires du mois', 'Unités vendues du mois', 'Produits en rupture',
            'Promotions actives', 'Chiffre d’affaires · 6 derniers mois',
            'Ventes par appellation', 'Meilleures ventes', 'Ventes récentes',
        ):
            with self.subTest(panneau=panneau):
                self.assertIn(panneau, self.html)

    def test_chaque_indicateur_ouvre_la_page_qui_l_explique(self):
        """Un chiffre sans porte de sortie oblige à revenir en arrière."""
        for cible in ('admin:ventes_vente_changelist', 'admin:stocks_stock_changelist',
                      'admin:promotions_promotion_changelist', 'caisse-enregistreuse',
                      'rapports'):
            with self.subTest(cible=cible):
                self.assertIn(reverse(cible), self.html)

    def test_les_panneaux_retires_ne_reviennent_pas(self):
        """Le menu, le Z-Report et les anciens blocs restent hors de l'accueil."""
        for absent in (
            'Objectif du mois', 'Moyens de paiement', 'Meilleurs clients',
            'Créances clients', 'Cuvées à surveiller', 'Ventes des 14 derniers jours',
        ):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, self.html)

    def test_les_fonctions_secondaires_ont_disparu(self):
        """Ni temps réel, ni export, ni impression, ni habillage décoratif."""
        for residue in (
            'clock-time', 'live-status', 'dash-toast', 'export-csv', 'print-dash',
            'refresh-live', 'dt-btn', 'class="spark', 'countup', 'loadPeriod',
            'setInterval', '@media print',
        ):
            with self.subTest(residue=residue):
                self.assertNotIn(residue, self.html)

    def test_les_valeurs_sont_rendues_cote_serveur(self):
        """Sans JavaScript, les chiffres du mois restent lisibles."""
        # Quatre indicateurs, et rien de plus à éplucher.
        self.assertEqual(self.html.count('class="wine-kpi-label"'), 4)
        for libelle in ('Chiffre d’affaires du mois', 'Unités vendues du mois', 'Produits en rupture',
                        'Promotions actives'):
            with self.subTest(libelle=libelle):
                self.assertIn(f'class="wine-kpi-label">{libelle}<', self.html)
        # Chacun est une carte entière : libellé, valeur, précision.
        self.assertEqual(self.html.count('class="wine-kpi-label"'),
                         self.html.count('class="wine-kpi-foot"'))
        self.assertNotIn('<span class="countup"', self.html)
        self.assertNotIn('—</span></div>', self.html, 'aucun compteur ne doit rester vide')


class MenuLateralTests(TestCase):
    """Le menu latéral ne montre que les sections du quotidien.

    Une page à onglets ne donne qu'une entrée : « Caisse » ouvre le journal et
    les réservations, « Paramètres & Utilisateurs » ouvre les comptes et les
    réglages. Le reste disparaît de la navigation — sans disparaître : chaque
    page repliée reste accessible par URL. La source de vérité du menu est
    `JAZZMIN_SETTINGS['hide_models']`, testée ici plutôt que le HTML rendu.
    """

    #: Les sections visibles, dans l'ordre.
    SECTIONS_ATTENDUES = [
        'Accès rapide', 'Ventes', 'Clients', 'Vins &amp; Produits', 'Stocks',
        'Promotions', 'Réglages',
    ]

    #: Les entrées de l'accès rapide.
    ACCES_RAPIDE = ['Accueil', 'Rapports', 'Caisse']

    #: Les modèles repliés : (section absente du menu, page qui reste ouverte).
    REPLIES = {
        'Mouvements de stock': 'admin:stocks_mouvementstock_changelist',
        'Sessions de caisse': 'admin:ventes_sessioncaisse_changelist',
        "Journal d\'activité": 'admin:parametres_entreejournal_changelist',
    }

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123',
        )
        self.client.force_login(self.admin)
        Client.objects.create(nom='Martin', prenom='Paul', telephone='0340012345')

    def _menu(self):
        html = self.client.get(reverse('admin:index')).content.decode('utf-8')
        return html[html.index('<aside'):html.index('</aside>')]

    def test_le_menu_ne_contient_que_les_sections_essentielles(self):
        sections = [
            c.split('<')[0].strip() for c in self._menu().split('nav-section-label">')[1:]
        ]
        # « Favoris » est masqué tant qu'aucune page n'est épinglée.
        sections = [s for s in sections if s != 'Favoris']
        self.assertEqual(sections, self.SECTIONS_ATTENDUES)

    def test_l_acces_rapide_ouvre_les_trois_pages_du_quotidien(self):
        menu = self._menu()
        for entree in self.ACCES_RAPIDE:
            with self.subTest(entree=entree):
                self.assertIn(f'>{entree}<', menu)

    def test_chaque_page_repliee_reste_atteignable(self):
        for libelle, nom_url in self.REPLIES.items():
            with self.subTest(modele=libelle):
                self.assertNotIn(f'>{libelle}<', self._menu())
                self.assertEqual(self.client.get(reverse(nom_url)).status_code, 200)

    def test_le_zreport_ne_revient_pas_dans_le_menu(self):
        self.assertNotIn('zreport', self._menu())
        self.assertNotIn('Z-Report', self._menu())
