"""Espace Caisse : une page, trois onglets, une seule entrée de menu.

La caisse, le journal des ventes et les réservations ne sont pas trois
modules : c'est le même travail de comptoir. Ces tests verrouillent la fusion
— la barre d'onglets présente et active sur les trois pages, et une unique
entrée « Caisse » dans la sidebar.
"""
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

ONGLETS = ('Nouvelle vente', 'Ventes', 'Commandes clients')


class EspaceCaisseOngletsTests(TestCase):
    """La même barre d'onglets ouvre les trois pages de l'espace caisse."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123',
        )
        self.client.force_login(self.admin)

    def test_les_trois_pages_portent_la_meme_barre(self):
        pages = {
            reverse('caisse-enregistreuse'): 'Nouvelle vente',
            reverse('admin:ventes_vente_changelist'): 'Ventes',
            reverse('admin:ventes_reservation_changelist'): 'Commandes clients',
        }
        for url, actif in pages.items():
            with self.subTest(page=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                html = response.content.decode('utf-8')
                self.assertIn('class="lb-tabs"', html)
                for onglet in ONGLETS:
                    self.assertIn(f'<span>{onglet}</span>', html)
                tabs = re.findall(
                    r'class="lb-tab( is-active)?"[^>]*>\s*<i[^>]*></i>\s*<span>([^<]+)</span>', html,
                )
                self.assertEqual([t[1] for t in tabs if t[0]], [actif])

    def test_la_caisse_est_la_seule_porte_du_menu(self):
        """Une entrée « Caisse », et rien d'autre pour le travail de comptoir."""
        html = self.client.get(reverse('admin:index')).content.decode('utf-8')
        aside = html[html.index('<aside'):html.index('</aside>')]
        liens = re.findall(r'<span class="nav-label">([^<]+)</span>', aside)
        self.assertIn('Caisse', liens)
        for doublon in ('Ventes', 'Réservations'):
            self.assertNotIn(doublon, liens)

    def test_le_journal_reste_atteignable_par_son_url(self):
        """Repliée dans l'onglet, la liste des ventes reste une vraie page."""
        self.assertEqual(self.client.get(reverse('admin:ventes_vente_changelist')).status_code, 200)

    def test_la_caisse_n_affiche_pas_carte_ni_compte_client(self):
        modes = [
            ('ESPECES', 'Espèces'),
            ('CHEQUE', 'Chèque'),
            ('CARTE', 'Carte bancaire'),
            ('CREDIT', 'Compte client'),
        ]
        with patch('apps.ventes.views_pos.modes_actifs', return_value=modes):
            response = self.client.get(reverse('caisse-enregistreuse'))

        self.assertEqual(response.status_code, 200)
        modes_affiches = re.findall(
            r'<button type="button" data-mode="([^"]+)"',
            response.content.decode('utf-8'),
        )
        self.assertIn('ESPECES', modes_affiches)
        self.assertIn('CHEQUE', modes_affiches)
        self.assertNotIn('CARTE', modes_affiches)
        self.assertNotIn('CREDIT', modes_affiches)

    def test_la_caisse_signale_si_aucun_moyen_de_paiement_ne_reste(self):
        modes = [('CARTE', 'Carte bancaire'), ('CREDIT', 'Compte client')]
        with patch('apps.ventes.views_pos.modes_actifs', return_value=modes):
            response = self.client.get(reverse('caisse-enregistreuse'))

        self.assertContains(response, 'Aucun moyen de paiement disponible')
        self.assertContains(response, 'id="payment-pills"')

    def test_la_caisse_calcule_les_offres_sans_code_promo(self):
        """Plus d'entrée de code : la caisse recalcule les offres toute seule."""
        response = self.client.get(reverse('caisse-enregistreuse'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="promo-code"')
        self.assertContains(response, 'id="promo-code-feedback"')
        self.assertContains(response, "wineadmin-pos.js")
