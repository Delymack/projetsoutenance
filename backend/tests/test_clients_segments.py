"""Segments, filtres et actions de la page Clients.

Ces tests verrouillent la correction de « sans achat 90 j » (dernier achat
réellement ancien), le regroupement des niveaux de fidélité, et le
caractère non destructif de l'action de plafond de crédit.
"""
from datetime import timedelta

from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.clients.admin import clients_a_risque, clients_sans_achat
from apps.clients.models import Client
from apps.ventes.models import Vente

User = get_user_model()

LISTE = '/admin/clients/client/'


class FiltresClientsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123',
        )
        self.client.force_login(self.admin)

    def _vente_payee(self, client, il_y_a_jours, montant=10000):
        """Crée une vente payée et recule sa date (auto_now_add)."""
        vente = Vente.objects.create(
            client=client, utilisateur=self.admin, total=montant, statut=Vente.Statut.PAYEE,
        )
        Vente.objects.filter(pk=vente.pk).update(
            date_vente=timezone.now() - timedelta(days=il_y_a_jours)
        )
        return vente

    # ---------- Sans achat 90 jours ----------

    def test_client_avec_vente_recente_nest_pas_compte(self):
        client = Client.objects.create(nom='Actif', prenom='Jean', telephone='0340000001')
        self._vente_payee(client, il_y_a_jours=5)
        self.assertFalse(clients_sans_achat(Client.objects.filter(pk=client.pk)).exists())

    def test_client_dernier_achat_ancien_est_compte(self):
        """Régression : avant, un client ayant acheté il y a 2 ans était ignoré
        parce qu'il avait déjà une vente (exclu du calcul)."""
        client = Client.objects.create(nom='Ancien', prenom='Paul', telephone='0340000002')
        self._vente_payee(client, il_y_a_jours=200)
        self._vente_payee(client, il_y_a_jours=400)  # une autre, encore plus vieille
        self.assertTrue(clients_sans_achat(Client.objects.filter(pk=client.pk)).exists())

    def test_client_sans_vente_et_recent_est_exclu(self):
        Client.objects.create(nom='Nouveau', prenom='Sam', telephone='0340000003')
        self.assertFalse(clients_sans_achat(Client.objects.all()).exists())

    def test_client_sans_vente_et_ancien_est_compte(self):
        client = Client.objects.create(nom='Dormant', prenom='Luc', telephone='0340000004')
        Client.objects.filter(pk=client.pk).update(
            date_creation=timezone.now() - timedelta(days=365)
        )
        self.assertTrue(clients_sans_achat(Client.objects.filter(pk=client.pk)).exists())

    def test_vente_annulee_ne_compte_pas_comme_un_achat(self):
        client = Client.objects.create(nom='Annule', prenom='Ana', telephone='0340000005')
        vente = Vente.objects.create(
            client=client, utilisateur=self.admin, total=5000, statut=Vente.Statut.ANNULEE,
        )
        Vente.objects.filter(pk=vente.pk).update(
            date_vente=timezone.now() - timedelta(days=300)
        )
        Client.objects.filter(pk=client.pk).update(
            date_creation=timezone.now() - timedelta(days=400)
        )
        self.assertTrue(clients_sans_achat(Client.objects.filter(pk=client.pk)).exists())

    def test_filtre_inactif_90j_applique_le_parametre(self):
        actif = Client.objects.create(nom='Actif', prenom='Jean', telephone='0340000001')
        inactif = Client.objects.create(nom='Ancien', prenom='Paul', telephone='0340000002')
        self._vente_payee(actif, il_y_a_jours=5)
        self._vente_payee(inactif, il_y_a_jours=200)

        reponse = self.client.get(LISTE, {'inactif_90j': '1'})
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode('utf-8')
        self.assertIn('Ancien', html)
        self.assertNotIn('Actif<', html.replace('Actifs', ''))

    # ---------- Fidélité ----------

    def test_filtre_fidelite_regroupe_argent_et_or(self):
        # `niveau` est recalculé à chaque enregistrement : on passe par les
        # points, qui sont la seule saisie réellement possible.
        bronze = Client.objects.create(nom='Bronze', prenom='B', points_fidelite=10)
        argent = Client.objects.create(nom='Argent', prenom='A', points_fidelite=Client.SEUIL_ARGENT)
        or_ = Client.objects.create(nom='Or', prenom='O', points_fidelite=Client.SEUIL_OR)

        ids = {str(o.pk) for o in self.client.get(LISTE, {'fidelite': 'fidelite'}).context['cl'].result_list}
        self.assertEqual(ids, {str(argent.pk), str(or_.pk)})
        self.assertNotIn(str(bronze.pk), ids)

    def test_filtre_ambassadeur_ne_garde_que_or(self):
        Client.objects.create(nom='Argent', prenom='A', points_fidelite=Client.SEUIL_ARGENT)
        or_ = Client.objects.create(nom='Or', prenom='O', points_fidelite=Client.SEUIL_OR)
        ids = {str(o.pk) for o in self.client.get(LISTE, {'fidelite': 'ambassadeur'}).context['cl'].result_list}
        self.assertEqual(ids, {str(or_.pk)})

    # ---------- Risque ----------

    def test_clients_a_risque_encours_haut_ou_sans_plafond(self):
        Client.objects.create(nom='Sain', prenom='A', telephone='1', max_credit=100000, solde_du=1000)
        Client.objects.create(nom='Presque', prenom='B', telephone='2', max_credit=100000, solde_du=70000)
        Client.objects.create(nom='SansPlafond', prenom='C', telephone='3', max_credit=0, solde_du=5000)
        Client.objects.create(nom='Endette', prenom='D', telephone='4', max_credit=100000, solde_du=0)

        noms = {c.nom for c in clients_a_risque(Client.objects.all())}
        self.assertEqual(noms, {'Presque', 'SansPlafond'})

    def test_filtre_risque_applique_le_parametre(self):
        Client.objects.create(nom='Presque', prenom='B', telephone='2', max_credit=100000, solde_du=70000)
        Client.objects.create(nom='Sain', prenom='A', telephone='1', max_credit=100000, solde_du=1000)
        html = self.client.get(LISTE, {'credit_ouvert': '1'}).content.decode('utf-8')
        self.assertIn('Presque', html)
        self.assertNotIn('Sain<', html.replace('Sains', ''))

    # ---------- Filtres de la liste ----------

    def test_raccourcis_segments_ne_sont_plus_rendus(self):
        """La liste garde ses indicateurs sans réafficher la rangée de liens."""
        reponse = self.client.get(LISTE, {'solde_due': '1'})
        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn('clients_segments', reponse.context)
        self.assertNotContains(reponse, 'lb-segments')

    def test_filtres_metier_conservent_leurs_parametres(self):
        """Les liens de segments ont disparu, pas les filtres auxquels ils menaient."""
        from django.contrib import admin as dj_admin
        model_admin = dj_admin.site._registry[Client]
        parametres = set()
        for f in model_admin.list_filter:
            if isinstance(f, str):
                parametres.add(f'{f}__exact')
            else:
                parametres.add(f.parameter_name)

        for nom in ('solde_due', 'fidelite', 'credit_ouvert', 'inactif_90j', 'type_client__exact'):
            self.assertIn(nom, parametres, f'filtre métier « {nom} » manquant')

    def test_kpi_sans_achat_90j_suit_la_corrélation(self):
        actif = Client.objects.create(nom='Actif', prenom='Jean', telephone='0340000001')
        inactif = Client.objects.create(nom='Ancien', prenom='Paul', telephone='0340000002')
        self._vente_payee(actif, il_y_a_jours=5)
        self._vente_payee(inactif, il_y_a_jours=200)

        kpis = self.client.get(LISTE).context['clients_kpis']
        self.assertEqual(kpis['sans_achat_90j'], 1)
        self.assertEqual(kpis['actifs'], 2)


class ActionCreditTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123',
        )
        self.client.force_login(self.admin)
        self.cible = Client.objects.create(nom='Nouveau', prenom='Client', telephone='0341111111')

    def _lancer(self, clients):
        return self.client.post(
            LISTE,
            {'action': 'actions_liberer_credit', '_selected_action': [str(c.pk) for c in clients]},
            follow=True,
        )

    @override_settings(SOCIETE={**django_settings.SOCIETE, 'credit_plafond_defaut': 250000})
    def test_plafond_provient_des_settings(self):
        self._lancer([self.cible])
        self.cible.refresh_from_db()
        self.assertEqual(self.cible.max_credit, 250000)

    def test_client_deja_plafonne_est_laisse_intact(self):
        """Non destructif : l'action ne doit jamais augmenter un plafond."""
        deja = Client.objects.create(
            nom='Plafonne', prenom='Client', telephone='0342222222', max_credit=50000,
        )
        reponse = self._lancer([self.cible, deja])
        deja.refresh_from_db()
        self.cible.refresh_from_db()
        self.assertEqual(deja.max_credit, 50000, 'le plafond existant doit être conservé')
        self.assertGreater(self.cible.max_credit, 0)
        self.assertContains(reponse, 'déjà plafonné')

    def test_action_refusee_si_aucun_plafond_defaut(self):
        with override_settings(SOCIETE={**django_settings.SOCIETE, 'credit_plafond_defaut': 0}):
            self._lancer([self.cible])
        self.cible.refresh_from_db()
        self.assertEqual(self.cible.max_credit, 0)
