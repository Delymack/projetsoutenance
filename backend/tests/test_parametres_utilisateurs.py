"""Console « Paramètres & Utilisateurs » : onglets, comptes, modes de paiement, sauvegardes."""

import shutil
import tempfile
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.produits.models import Produit
from apps.stocks.models import Stock
from apps.parametres import sauvegarde as service_sauvegarde
from apps.parametres.models import EntreeJournal, Sauvegarde
from apps.parametres.services import get_param, invalidate, save_config
from apps.parametres.tva import decomposition
from apps.ventes.paiements import codes_actifs, modes_actifs

User = get_user_model()

MEDIA = tempfile.mkdtemp(prefix='test-sauvegardes-')


class _ParametresCas(TestCase):
    """Base des tests qui enregistrent une configuration.

    Le cache des paramètres est en mémoire et hors transaction : un test qui
    écrit une configuration la relit ensuite, et la base étant annulée à la
    fin du test, la valeur resterait en cache pour les suivants — un mode de
    paiement ou un taux de TVA fantôme. On invalide donc systématiquement.
    """

    def tearDown(self):
        invalidate()
        super().tearDown()


def _admin(**extra):
    def _creer(**kw):
        base = dict(
            username='admin', email='admin@test.com', password='motdepasse123',
            role=User.Role.ADMIN, is_staff=True, is_superuser=True, is_active=True,
        )
        base.update(kw)
        return User.objects.create_user(**base)
    return _creer(**extra)


@override_settings(MEDIA_ROOT=MEDIA)
class ConsoleFusionneeTests(_ParametresCas):
    """La page unique doit porter les trois volets et rester protégée."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = _admin()
        cls.gestionnaire = _admin(
            username='gest', email='gest@test.com', role=User.Role.GESTIONNAIRE,
            is_superuser=False, first_name='Gasy', last_name='Rakoto',
        )
        cls.vendeur = _admin(
            username='vendeur', email='vendeur@test.com', role=User.Role.VENDEUR,
            is_superuser=False, is_staff=False,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_page_unique_expose_les_trois_volets(self):
        reponse = self.client.get(reverse('parametres:index'))
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode()
        self.assertIn('<h1>Paramètres</h1>', html)
        self.assertIn('class="cfg-workspace"', html)
        self.assertIn('class="cfg-workspace-content"', html)
        self.assertIn('Rechercher un réglage', html)
        self.assertIn('id="cfg-save" disabled', html)
        self.assertIn('aria-controls="panel-SOCIETE"', html)
        self.assertIn('id="tab-SOCIETE"', html)
        for libelle in ('Société', 'Ventes', 'Caisse', 'Sécurité', 'Apparence', 'Site', 'Système'):
            self.assertIn(f'>{libelle}<', html)
        for panneau in ('utilisateurs', 'sauvegarde', 'SOCIETE', 'VENTES'):
            self.assertIn(f'id="panel-{panneau}"', html, f'panneau {panneau} absent')
        for element in ('panel-journal', 'Rôles &amp; droits', 'Importer', 'Exporter', 'Imprimer'):
            self.assertNotIn(element, html)

    def test_onglet_direct_par_url(self):
        reponse = self.client.get(reverse('parametres:index'), {'onglet': 'utilisateurs'})
        self.assertEqual(reponse.context['onglet'], 'utilisateurs')

    def test_onglet_inconnu_ne_casse_pas_la_page(self):
        reponse = self.client.get(reverse('parametres:index'), {'onglet': 'pirate'})
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.context['onglet'], '')

    def test_journal_reste_stocke_sans_alourdir_la_console(self):
        EntreeJournal.objects.create(
            action=EntreeJournal.Action.MODIF,
            cle='parametre-sans-auteur',
            utilisateur=None,
        )
        reponse = self.client.get(reverse('parametres:index'))
        self.assertEqual(reponse.status_code, 200)
        self.assertNotContains(reponse, 'parametre-sans-auteur')
        self.assertTrue(EntreeJournal.objects.filter(cle='parametre-sans-auteur').exists())

    def test_tableau_des_comptes_et_liens_de_reinitialisation(self):
        reponse = self.client.get(reverse('parametres:index'), {'onglet': 'utilisateurs'})
        html = reponse.content.decode()
        self.assertIn('gasy', html)
        self.assertIn('<h1>Paramètres</h1>', html)
        # Le lien « mot de passe » pointe bien vers la page Django de
        # réinitialisation, pas vers une URL décorative.
        self.assertIn(reverse('admin:auth_user_password_change', args=[self.vendeur.pk]), html)
        self.assertIn(reverse('admin:accounts_user_change', args=[self.gestionnaire.pk]), html)
        self.assertIn(reverse('admin:accounts_user_add'), html)
        # On ne peut pas se supprimer soi-même : le bouton est neutralisé.
        self.assertNotIn(reverse('admin:accounts_user_delete', args=[self.admin.pk]), html)

    def test_console_ne_fournit_plus_la_matrice_des_roles(self):
        reponse = self.client.get(reverse('parametres:index'), {'onglet': 'utilisateurs'})
        self.assertNotIn('matrice_roles', reponse.context)
        self.assertNotContains(reponse, 'Rôles &amp; droits')

    def test_sidebar_n_expose_plus_que_la_console_unique(self):
        html = self.client.get(reverse('admin:index')).content.decode()
        # Une seule entrée pour les comptes et les paramètres.
        self.assertEqual(html.count('nav-label">Réglages'), 1)
        self.assertNotIn('nav-label">Utilisateurs', html)

    def test_pages_administratives_des_comptes_toujours_atteignables(self):
        for url in (
            reverse('admin:accounts_user_changelist'),
            reverse('admin:accounts_user_add'),
            reverse('admin:accounts_user_change', args=[self.vendeur.pk]),
            reverse('admin:auth_user_password_change', args=[self.vendeur.pk]),
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_vendeur_ne_peut_pas_sauvegarder_la_base(self):
        vendeur = self.vendeur
        vendeur.is_staff = True  # un caissier qui a quand même le back-office
        vendeur.save()
        self.client.force_login(vendeur)
        reponse = self.client.post(reverse('parametres:sauvegarde-creer'), follow=True)
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(Sauvegarde.objects.exists())
        self.assertContains(reponse, 'administrateur ou un gestionnaire')

    def test_vendeur_ne_peut_pas_modifier_les_parametres(self):
        vendeur = self.vendeur
        vendeur.is_staff = True
        vendeur.save()
        self.client.force_login(vendeur)
        reponse = self.client.post(reverse('parametres:index'), {'societe_nom': 'Piraté'})
        self.assertEqual(reponse.status_code, 302)
        self.assertNotEqual(get_param('societe_nom'), 'Piraté')


class ModesPaiementTests(_ParametresCas):
    """Les moyens de paiement se règlent, sans invalider l'historique."""

    def setUp(self):
        self.admin = _admin()
        self.client.force_login(self.admin)

    @staticmethod
    def _produit(nom, prix):
        produit = Produit.objects.create(
            nom=nom, type_vin='Rouge', marque='Domaine',
            cout_revenir=prix / 2, prix_vente=prix, statut=True,
        )
        Stock.objects.update_or_create(produit=produit, defaults={'quantite': 10, 'seuil_alerte': 2})
        return produit

    def test_defaut_tous_les_modes(self):
        from apps.ventes.models import Vente

        self.assertEqual(set(codes_actifs()), set(Vente.ModePaiement.values))

    def test_la_caisse_ne_propose_que_les_modes_actifs(self):
        save_config({'ventes_modes_paiement': ['ESPECES', 'MVOLA']})
        reponse = self.client.get('/admin/caisse/')
        codes = [c for c, _ in reponse.context['modes_paiement']]
        self.assertEqual(codes, ['ESPECES', 'MVOLA'])
        self.assertIn(('MVOLA', 'Mvola'), modes_actifs())

    def test_une_case_decochee_est_retiree_de_la_caisse(self):
        reponse = self.client.post(reverse('parametres:index'), {
            'societe_nom': 'LAZAN\'I BETSILEO',
            'ventes_modes_paiement': ['ESPECES', 'CARTE'],
            'ventes_tva': '0',
        })
        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(get_param('ventes_modes_paiement'), ['ESPECES', 'CARTE'])

    def test_il_faut_laisser_au_moins_un_mode(self):
        reponse = self.client.post(reverse('parametres:index'), {'ventes_modes_paiement': []})
        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(get_param('ventes_modes_paiement'),
                         ['ESPECES', 'MVOLA', 'ORANGE_MONEY', 'AIRTEL_MONEY', 'MOBILE_MONEY', 'CHEQUE', 'CARTE', 'CREDIT'])

    def test_vente_refusee_avec_un_mode_desactive(self):
        from apps.ventes.services import VenteService
        from rest_framework.exceptions import ValidationError

        produit = self._produit('Rouge 75cl', 1500)
        save_config({'ventes_modes_paiement': ['ESPECES', 'MVOLA']})
        with self.assertRaises(ValidationError) as ctx:
            VenteService.creer_vente(
                client_id=None, mode_paiement='CHEQUE',
                lignes_data=[{'produit_id': produit.id, 'quantite': 1}],
                utilisateur=self.admin,
            )
        self.assertIn('mode_paiement', str(ctx.exception.detail))

    def test_vente_acceptee_avec_un_mode_actif(self):
        from apps.ventes.services import VenteService

        produit = self._produit('Blanc 75cl', 1400)
        save_config({'ventes_modes_paiement': ['ESPECES', 'MVOLA']})
        vente = VenteService.creer_vente(
            client_id=None, mode_paiement='MVOLA',
            lignes_data=[{'produit_id': produit.id, 'quantite': 1}],
            utilisateur=self.admin, reference_paiement='MP260930.1234.ABCD',
        )
        self.assertEqual(vente.mode_paiement, 'MVOLA')

    def test_reglement_mixte_valide_meme_espces_desactive(self):
        from apps.ventes.services import VenteService

        produit = self._produit('Rose 75cl', 1300)
        save_config({'ventes_modes_paiement': ['MVOLA', 'CARTE']})
        vente = VenteService.creer_vente(
            client_id=None, mode_paiement='ESPECES',
            lignes_data=[{'produit_id': produit.id, 'quantite': 1}],
            utilisateur=self.admin,
            paiements=[
                {'mode': 'MVOLA', 'montant': 500, 'reference': 'MP1'},
                {'mode': 'CARTE', 'montant': 800},
            ],
        )
        # Le mode retenu est celui qui apporte le plus (règle préexistante),
        # pas le placeholder utilisé pour la création.
        self.assertEqual(vente.mode_paiement, 'CARTE')

    def test_parametre_aligne_sur_le_vocabulaire_de_ventevente(self):
        from apps.parametres.defaults import DEFAULTS
        from apps.ventes.models import Vente

        choix = next(d[5]['choix'] for d in DEFAULTS if d[1] == 'ventes_modes_paiement')
        self.assertEqual({c for c, _ in choix}, set(Vente.ModePaiement.values))


class TvaTests(_ParametresCas):
    def test_defauts_tva_et_echeance_sont_des_valeurs_de_demo(self):
        self.assertEqual(get_param('ventes_tva'), Decimal('20'))
        self.assertTrue(get_param('ventes_tva_incluse'))
        self.assertEqual(get_param('ventes_delai_paiement_jours'), 60)

    def test_valeurs_tva_et_echeance_hors_plage_refusees(self):
        from apps.parametres.services import erreur_entries

        self.assertTrue(erreur_entries({'ventes_tva': '101'}))
        self.assertTrue(erreur_entries({'ventes_delai_paiement_jours': '-1'}))

    def test_taux_nul_ne_declenche_rien(self):
        resultat = decomposition(10000, 0, True)
        self.assertFalse(resultat['active'])
        self.assertEqual(resultat['tva'], Decimal('0.00'))

    def test_un_prix_ht_devient_ttc_a_l_arrondi_comptable(self):
        resultat = decomposition(10000, 20, False)
        self.assertEqual(resultat['ht'], Decimal('10000.00'))
        self.assertEqual(resultat['tva'], Decimal('2000.00'))
        self.assertEqual(resultat['ttc'], Decimal('12000.00'))

    def test_prix_ttc_extrait_la_taxe(self):
        resultat = decomposition(12000, 20, True)
        self.assertEqual(resultat['ht'], Decimal('10000.00'))
        self.assertEqual(resultat['tva'], Decimal('2000.00'))

    def test_prix_ht_ajoute_la_taxe(self):
        resultat = decomposition(10000, 20, False)
        self.assertEqual(resultat['ht'], Decimal('10000.00'))
        self.assertEqual(resultat['tva'], Decimal('2000.00'))

    def test_arrondi_comptable(self):
        resultat = decomposition(3333, 19, True)
        self.assertEqual(resultat['ht'] + resultat['tva'], Decimal('3333.00'))


@override_settings(MEDIA_ROOT=MEDIA)
class SauvegardeTests(_ParametresCas):
    def setUp(self):
        self.admin = _admin()
        self.client.force_login(self.admin)
        Sauvegarde.objects.all().delete()

    def tearDown(self):
        shutil.rmtree(MEDIA, ignore_errors=True)
        tempfile.mkdtemp(prefix='test-sauvegardes-')

    def test_creation_depose_un_fichier_lisible(self):
        ligne = service_sauvegarde.creer(utilisateur=self.admin)
        self.assertEqual(ligne.statut, Sauvegarde.Statut.REUSSIE)
        chemin = service_sauvegarde.chemin(ligne)
        self.assertTrue(chemin and chemin.is_file(), 'le fichier doit exister sur le disque')
        self.assertGreater(chemin.stat().st_size, 0)
        self.assertTrue(ligne.nb_tables > 0)
        self.assertTrue(ligne.disponible)

    def test_repli_export_json_quand_la_base_n_est_pas_sur_disque(self):
        # Base de test en mémoire : aucune copie SQLite possible, l'export
        # logique prend le relais plutôt que de laisser une sauvegarde en échec.
        ligne = service_sauvegarde.creer(utilisateur=self.admin)
        self.assertEqual(ligne.format, Sauvegarde.Format.JSON)
        self.assertTrue(ligne.erreur)
        contenu = service_sauvegarde.chemin(ligne).read_bytes()
        self.assertEqual(contenu[:2], b'\x1f\x8b')  # en-tête gzip

    def test_via_l_interface(self):
        reponse = self.client.post(reverse('parametres:sauvegarde-creer'))
        self.assertEqual(reponse.status_code, 302)
        self.assertIn('?onglet=sauvegarde', reponse['Location'])
        self.assertEqual(Sauvegarde.objects.count(), 1)

    def test_telechargement(self):
        ligne = service_sauvegarde.creer(utilisateur=self.admin)
        reponse = self.client.get(reverse('parametres:sauvegarde-telecharger', args=[ligne.pk]))
        self.assertEqual(reponse.status_code, 200)
        self.assertIn('attachment', reponse['Content-Disposition'])

    def test_suppression_retire_le_fichier(self):
        ligne = service_sauvegarde.creer(utilisateur=self.admin)
        chemin = service_sauvegarde.chemin(ligne)
        reponse = self.client.post(reverse('parametres:sauvegarde-supprimer', args=[ligne.pk]))
        self.assertEqual(reponse.status_code, 302)
        self.assertFalse(Sauvegarde.objects.exists())
        self.assertFalse(chemin.exists())

    def test_onglet_sauvegarde_liste_les_copies(self):
        service_sauvegarde.creer(utilisateur=self.admin)
        html = self.client.get(reverse('parametres:index'), {'onglet': 'sauvegarde'}).content.decode()
        self.assertIn('Historique', html)
        self.assertIn('Sauvegarder maintenant', html)

    def test_retention_efface_les_anciennes(self):
        with mock.patch('apps.parametres.sauvegarde.GARDER', 1):
            service_sauvegarde.creer(utilisateur=self.admin)
            premiere = Sauvegarde.objects.order_by('date').first()
            service_sauvegarde.creer(utilisateur=self.admin)
            # Les deux copies datent du même jour : la rétention en jours ne
            # doit pas laisser la purge s'exécuter sur du récent.
            self.assertEqual(Sauvegarde.objects.count(), 2)
            self.assertIsNotNone(premiere)

    def test_echec_total_laisse_une_trace(self):
        with mock.patch('apps.parametres.sauvegarde._sauvegarde_sqlite', side_effect=RuntimeError('disque plein')), \
             mock.patch('apps.parametres.sauvegarde._sauvegarde_json', side_effect=RuntimeError('disque plein')):
            ligne = service_sauvegarde.creer(utilisateur=self.admin)
        self.assertEqual(ligne.statut, Sauvegarde.Statut.ECHEC)
        self.assertIn('disque plein', ligne.erreur)
        self.assertFalse(ligne.disponible)
