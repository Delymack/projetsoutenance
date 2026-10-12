"""``GET /api/accueil/`` : textes + les deux couleurs de la page principale."""

import json

from django.test import TestCase
from django.urls import reverse

from apps.parametres import services
from apps.parametres.defaults import ACCUEIL_TEXTES_DEFAUT, DEFAULTS, SECTIONS
from apps.parametres.models import Parametre


def _param(cle, valeur, type_='TEXT'):
    return Parametre.objects.create(
        section='ACCUEIL', cle=cle, libelle=cle, type=type_, valeur=valeur,
    )


class AccueilApiTests(TestCase):
    def setUp(self):
        services.invalidate()

    def tearDown(self):
        services.invalidate()

    def test_reponse_par_defaut(self):
        reponse = self.client.get(reverse('accueil-api'))
        self.assertEqual(reponse.status_code, 200)
        donnees = reponse.json()
        # Deux couleurs maximum : noir profond + or.
        self.assertEqual(donnees['couleurFond'], '#0C0A09')
        self.assertEqual(donnees['couleurAccent'], '#C9A227')
        # Textes des trois langues, avec les champs attendus.
        for langue in ('fr', 'mg', 'en'):
            with self.subTest(langue=langue):
                bloc = donnees['textes'][langue]
                self.assertEqual(bloc['titre'], "Lazan'i Betsileo")
                self.assertTrue(bloc['eyebrow'])
                self.assertEqual(len(bloc['motsCles']), 3)
                self.assertTrue(bloc['ctaCatalogue'])
                self.assertTrue(bloc['selectionTitre'])

    def test_valeurs_personnalisees(self):
        _param('accueil_couleur_fond', '#101010')
        _param('accueil_couleur_accent', '#FFD700')
        _param(
            'accueil_textes',
            json.dumps({'fr': {'titre': 'Titre perso', 'motsCles': ['A', 'B']}}),
            type_='TEXTAREA',
        )
        services.invalidate()
        donnees = self.client.get(reverse('accueil-api')).json()
        self.assertEqual(donnees['couleurFond'], '#101010')
        self.assertEqual(donnees['couleurAccent'], '#FFD700')
        self.assertEqual(donnees['textes']['fr']['titre'], 'Titre perso')
        self.assertEqual(donnees['textes']['fr']['motsCles'], ['A', 'B'])
        # Langue absente du paramètre : le client repasse sur son i18n.
        self.assertNotIn('mg', donnees['textes'])

    def test_couleur_invalide_retombe_sur_le_defaut(self):
        _param('accueil_couleur_fond', 'rouge')
        _param('accueil_couleur_accent', '#XYZ123')
        services.invalidate()
        donnees = self.client.get(reverse('accueil-api')).json()
        self.assertEqual(donnees['couleurFond'], '#0C0A09')
        self.assertEqual(donnees['couleurAccent'], '#C9A227')

    def test_json_invalide_est_ignore(self):
        _param('accueil_textes', '{pas du json}', type_='TEXTAREA')
        services.invalidate()
        donnees = self.client.get(reverse('accueil-api')).json()
        self.assertEqual(donnees['textes'], {})

    def test_methodes_non_get_refusees(self):
        self.assertEqual(self.client.post(reverse('accueil-api')).status_code, 405)

    def test_console_refuse_un_json_invalide(self):
        self.assertTrue(services.erreur_entries({'accueil_textes': '{oops}'}))
        self.assertFalse(services.erreur_entries({'accueil_textes': ACCUEIL_TEXTES_DEFAUT}))

    def test_section_accueil_declaree(self):
        codes = [section['code'] for section in SECTIONS]
        self.assertIn('ACCUEIL', codes)
        # Chaque section utilisée par DEFAULTS doit exister (sinon build_sections plante).
        for entree in DEFAULTS:
            with self.subTest(cle=entree[1]):
                self.assertIn(entree[0], codes)
