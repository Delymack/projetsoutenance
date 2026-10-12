from decimal import Decimal

from django.test import TestCase

from apps.dashboard.templatetags.dashboard_tags import montant_en_lettres


class EnLettresTests(TestCase):
    def test_montants_simples(self):
        self.assertEqual(montant_en_lettres(0), "zéro ariary")
        self.assertEqual(montant_en_lettres(1), "un ariary")
        self.assertEqual(montant_en_lettres(15), "quinze ariary")
        self.assertEqual(montant_en_lettres(21), "vingt-et-un ariary")

    def test_dizaines_irregulieres(self):
        self.assertEqual(montant_en_lettres(70), "soixante-dix ariary")
        self.assertEqual(montant_en_lettres(71), "soixante-et-onze ariary")
        self.assertEqual(montant_en_lettres(72), "soixante-douze ariary")
        self.assertEqual(montant_en_lettres(80), "quatre-vingts ariary")
        self.assertEqual(montant_en_lettres(81), "quatre-vingt-un ariary")
        self.assertEqual(montant_en_lettres(90), "quatre-vingt-dix ariary")
        self.assertEqual(montant_en_lettres(99), "quatre-vingt-dix-neuf ariary")

    def test_centaines_et_milles(self):
        self.assertEqual(montant_en_lettres(100), "cent ariary")
        self.assertEqual(montant_en_lettres(101), "cent un ariary")
        self.assertEqual(montant_en_lettres(200), "deux cents ariary")
        self.assertEqual(montant_en_lettres(201), "deux cent un ariary")
        self.assertEqual(montant_en_lettres(1000), "mille ariary")
        self.assertEqual(montant_en_lettres(2000), "deux mille ariary")
        self.assertEqual(montant_en_lettres(1500), "mille cinq cents ariary")
        self.assertEqual(montant_en_lettres(100000), "cent mille ariary")

    def test_petites_unites_centimes(self):
        self.assertEqual(montant_en_lettres('1.50'), "un ariary et cinquante iraimbilanja")
        self.assertEqual(montant_en_lettres('12.05'), "douze ariary et cinq iraimbilanja")
        self.assertEqual(montant_en_lettres('100.99'), "cent ariary et quatre-vingt-dix-neuf iraimbilanja")
        self.assertEqual(montant_en_lettres(Decimal('1234567.89')),
                         "un million deux cent trente-quatre mille cinq cent soixante-sept ariary et quatre-vingt-neuf iraimbilanja")

    def test_filtre_template(self):
        from django.template import Template, Context
        t = Template("{% load dashboard_tags %}{{ v|en_lettres }}")
        self.assertEqual(t.render(Context({'v': '125000.50'})),
                         "cent vingt-cinq mille ariary et cinquante iraimbilanja")