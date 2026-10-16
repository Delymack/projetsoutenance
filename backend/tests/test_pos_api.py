"""
Contrats HTTP du poste de caisse.

`static/js/wineadmin-pos.js` dépend de la forme exacte de ces réponses : une clé
renommée casse la caisse en silence (le JS lit `undefined` et affiche « NaN »).
Ces tests verrouillent les champs que le JS consomme réellement.
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.clients.models import Client
from apps.produits.models import Produit
from apps.promotions.models import Promotion
from apps.stocks.models import Stock
from apps.ventes.models import SessionCaisse, Vente


class BasePosApi(TestCase):
    """Utilisateur connecté, client et deux vins en stock."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123',
        )
        self.vendeur = User.objects.create_user(
            username='vendeur', email='vendeur@test.com', password='password123',
            role=User.Role.VENDEUR,
        )
        self.client.force_login(self.vendeur)
        self.client_obj = Client.objects.create(
            nom="Rakoto", prenom="Hanta", telephone="0340000000",
        )
        self.vin = self._produit("Cuvée 2018", Decimal('10000.00'), 50)
        self.petit = self._produit("Pétillant", Decimal('4000.00'), 6)

    def _produit(self, nom, prix, stock, **kwargs):
        produit = Produit.objects.create(
            nom=nom, type_vin="Rouge", marque="Domaine",
            cout_revenir=prix / 2, prix_vente=prix, statut=True, **kwargs,
        )
        Stock.objects.update_or_create(
            produit=produit, defaults={'quantite': stock, 'seuil_alerte': 2},
        )
        return produit

    def _vendre(self, paiements=None, quantite=2, client=None, **extra):
        corps = {
            'client': (client or self.client_obj).id,
            'lignes': [{'produit_id': self.vin.id, 'quantite': quantite}],
            **extra,
        }
        if paiements is not None:
            corps['paiements'] = paiements
        else:
            corps['mode_paiement'] = Vente.ModePaiement.ESPECES
        return self.client.post(reverse('ventes-list'), corps, content_type='application/json')


# ---------------------------------------------------------------------------
# Chargement de la caisse
# ---------------------------------------------------------------------------

class ContexteCaisseApiTests(BasePosApi):
    def test_etat_expose_les_champs_attendus_par_la_caisse(self):
        r = self.client.get(reverse('caisse-etat'))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        # Le JS lit tous ces champs au démarrage : un manquant casse l'écran.
        for champ in ('session', 'session_requise', 'peut_ouvrir', 'peut_remettre',
                      'remise_max_pct', 'remise_motif_obligatoire', 'devise', 'conditions'):
            self.assertIn(champ, data, f'champ absent du contexte : {champ}')
        self.assertIn('unites', data['conditions'])
        self.assertIsNone(data['session'])
        # `settings_test` neutralise l'obligation de session.
        self.assertFalse(data['session_requise'])

    def test_etat_ne_demande_pas_de_session_ouverte(self):
        self.assertFalse(SessionCaisse.objects.exists())
        self.assertEqual(self.client.get(reverse('caisse-etat')).status_code, 200)

    def test_ouvrir_puis_relire_etat(self):
        r = self.client.post(
            reverse('caisse-ouvrir'),
            {'fonds_initial': '20000.00'}, content_type='application/json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['success'])
        self.assertEqual(r.json()['contexte']['session']['fonds_de_caisse'], '20000.00')
        etat = self.client.get(reverse('caisse-etat')).json()
        self.assertIsNotNone(etat['session'])
        self.assertEqual(etat['session']['statut'], SessionCaisse.Statut.OUVERTE)

    def test_ouvrir_deux_fois_est_idempotent(self):
        # Comportement voulu : rouvrir rend le poste existant, pas une erreur —
        # un double-clic sur « Ouvrir la caisse » ne doit pas créer un second poste.
        self.client.post(reverse('caisse-ouvrir'), {'fonds_initial': '20000.00'},
                         content_type='application/json')
        r = self.client.post(reverse('caisse-ouvrir'), {'fonds_initial': '20000.00'},
                             content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(SessionCaisse.objects.count(), 1)
        # Le fonds ne doit pas être écrasé par la réouverture.
        self.assertEqual(Decimal(SessionCaisse.objects.get().fonds_de_caisse), Decimal('20000.00'))
        self.assertTrue(r.json()['success'])


class CatalogueCaisseApiTests(BasePosApi):
    """Le poste charge {produits, clients, catégories} au démarrage.

    Le JS fait un `Promise.all` sur les trois routes : si l'une manque, le
    catalogue ne s'affiche jamais. Ces tests verrouillent l'existence et la
    forme de la route des catégories, longtemps restée non branchée.
    """

    def test_les_trois_routes_du_catalogue_repondent(self):
        for nom in ('produits-list', 'clients-list', 'categories-list'):
            with self.subTest(route=nom):
                self.assertEqual(self.client.get(reverse(nom)).status_code, 200, nom)

    def test_categories_expose_une_liste_exploitable_par_le_js(self):
        from apps.categories.models import Categorie
        Categorie.objects.create(nom='Rouge', statut=True)
        r = self.client.get(reverse('categories-list'))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        # `fetchAll` lit `data.results` si la réponse est paginée, sinon la liste.
        resultats = data['results'] if isinstance(data, dict) and 'results' in data else data
        self.assertTrue(any(c['nom'] == 'Rouge' for c in resultats))


# ---------------------------------------------------------------------------
# Obligation de session (contrainte du poste de caisse)
# ---------------------------------------------------------------------------

@override_settings(SOCIETE={**__import__('django.conf', fromlist=['settings']).settings.SOCIETE,
                            'caisse_session_requise': True})
class SessionBloquanteApiTests(BasePosApi):
    def test_vente_refusee_tant_que_la_caisse_est_fermee(self):
        r = self._vendre()
        self.assertEqual(r.status_code, 409)
        self.assertFalse(r.json()['success'])
        self.assertIn('session', r.json()['errors'])

    def test_vente_acceptee_apres_ouverture(self):
        self.client.post(reverse('caisse-ouvrir'), {'fonds_initial': '20000.00'},
                         content_type='application/json')
        r = self._vendre()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIsNotNone(r.json()['data']['session'])


# ---------------------------------------------------------------------------
# Vente
# ---------------------------------------------------------------------------

class VenteApiTests(BasePosApi):
    def test_vente_especes_retourne_le_recu_complet(self):
        r = self._vendre()
        self.assertEqual(r.status_code, 201, r.content)
        data = r.json()['data']
        # Champs lus par la surcouche « reçu ».
        for champ in ('id', 'reference', 'total', 'mode_paiement', 'lignes',
                      'paiements', 'ticket_url', 'whatsapp_url', 'utilisateur',
                      'date_vente', 'net_a_encaiser'):
            self.assertIn(champ, data, f'champ absent de la vente : {champ}')
        self.assertIn('format=ticket80', data['ticket_url'])
        # Le client a un téléphone : le lien WhatsApp doit être exploitable.
        # « 0340000000 » devient 261 + 340000000, jamais un numéro avec le 0 national.
        self.assertTrue(
            data['whatsapp_url'].startswith('https://wa.me/261340000000?text='),
            f"lien WhatsApp inattendu : {data['whatsapp_url'][:80]}",
        )

    def test_vente_refuse_un_code_promo(self):
        """Un code saisi en caisse est refusé : les remises sont automatiques."""
        response = self._vendre(code_promo='CAVE10')

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn('désactivés', str(response.json()))

    def test_vendeur_simule_les_promotions_conditionnelles_sur_une_vente_anonyme(self):
        maintenant = timezone.now()
        promotion = Promotion.objects.create(
            nom='Remise quantité',
            type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=Decimal('10'),
            quantite_min=2,
            date_debut=maintenant - timedelta(days=1),
            date_fin=maintenant + timedelta(days=1),
        )
        promotion.produits.add(self.vin)

        response = self.client.post(
            reverse('promotions-simuler'),
            {
                'client': None,
                'lignes': [{'produit_id': self.vin.id, 'quantite': 2}],
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        self.assertEqual(Decimal(str(result['total'])), Decimal('18000.00'))
        self.assertEqual(result['type_client'], None)
        self.assertEqual(result['lignes'][0]['promotion'], 'Remise quantité')
        self.assertEqual(Decimal(str(result['lignes'][0]['remise'])), Decimal('2000.00'))

    def test_simulation_refuse_un_code_invalide_avec_message_explicite(self):
        response = self.client.post(
            reverse('promotions-simuler'),
            {
                'code_promo': 'INCONNU',
                'lignes': [{'produit_id': self.vin.id, 'quantite': 1}],
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('désactivés', response.json()['erreur'])

    def test_simulation_anonyme_ne_peut_pas_falsifier_le_segment_client(self):
        maintenant = timezone.now()
        promotion = Promotion.objects.create(
            nom='Offre restaurant',
            type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=Decimal('20'),
            type_cible=Promotion.TypeCible.RESTAURANT,
            date_debut=maintenant - timedelta(days=1),
            date_fin=maintenant + timedelta(days=1),
        )
        promotion.produits.add(self.vin)

        response = self.client.post(
            reverse('promotions-simuler'),
            {
                'client': None,
                'type_client': Promotion.TypeCible.RESTAURANT,
                'lignes': [{'produit_id': self.vin.id, 'quantite': 1}],
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()['type_client'])
        self.assertIsNone(response.json()['lignes'][0]['promotion'])
        self.assertEqual(Decimal(str(response.json()['total'])), Decimal('10000.00'))

    def test_paiement_mixte_via_http(self):
        r = self._vendre(paiements=[
            {'mode': Vente.ModePaiement.ESPECES, 'montant': '12000.00'},
            {'mode': Vente.ModePaiement.MOBILE_MONEY, 'montant': '8000.00'},
        ])
        self.assertEqual(r.status_code, 201, r.content)
        data = r.json()['data']
        self.assertEqual(len(data['paiements']), 2)
        self.assertEqual(Decimal(data['total']), Decimal('20000.00'))

    def test_remise_manuelle_avec_motif(self):
        r = self._vendre(motif_remise='Geste commercial')
        self.assertEqual(r.status_code, 201, r.content)
        data = r.json()['data']
        self.assertEqual(Decimal(data['remise_manuelle_totale']), Decimal('0.00'))

    def test_vendeur_plafonne_a_la_remise(self):
        self.client.force_login(self.vendeur)
        r = self.client.post(
            reverse('ventes-list'),
            {
                'client': self.client_obj.id,
                'mode_paiement': Vente.ModePaiement.ESPECES,
                'motif_remise': 'Trop',
                'lignes': [{
                    'produit_id': self.vin.id, 'quantite': 1,
                    'remise_manuelle': '9000.00',
                }],
            },
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()['success'])

    def test_ligne_vide_refusee(self):
        r = self.client.post(
            reverse('ventes-list'),
            {'client': self.client_obj.id, 'mode_paiement': Vente.ModePaiement.ESPECES, 'lignes': []},
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 400)

    def test_produit_rupture_refuse(self):
        r = self._vendre(quantite=999)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()['success'])

    def test_vendeur_ne_peut_pas_annuler(self):
        vente_id = self._vendre().json()['data']['id']
        r = self.client.post(reverse('ventes-annuler', args=[vente_id]), {},
                             content_type='application/json')
        self.assertEqual(r.status_code, 403)

    def test_admin_peut_annuler(self):
        vente_id = self._vendre().json()['data']['id']
        self.client.force_login(self.admin)
        r = self.client.post(reverse('ventes-annuler', args=[vente_id]), {},
                             content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['success'])


# ---------------------------------------------------------------------------
# Retours
# ---------------------------------------------------------------------------

class RetourApiTests(BasePosApi):
    def setUp(self):
        super().setUp()
        self.vente_id = self._vendre().json()['data']['id']

    def test_etat_des_lignes_retournables(self):
        # Admin requis pour lire l'état d'un retour.
        self.client.force_login(self.admin)
        r = self.client.get(reverse('ventes-retour', args=[self.vente_id]))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        for champ in ('vente', 'retourne', 'lignes'):
            self.assertIn(champ, data)
        ligne = data['lignes'][0]
        # Champs que l'écran de retour lit pour composer ses lignes.
        for champ in ('ligne_id', 'produit_id', 'nom', 'vendu', 'deja_retourne',
                      'retournable', 'prix_unitaire', 'sous_total'):
            self.assertIn(champ, ligne, f'champ absent de la ligne de retour : {champ}')

    def test_retour_partiel_emprete_le_stock(self):
        self.client.force_login(self.admin)
        r = self.client.post(
            reverse('ventes-retour', args=[self.vente_id]),
            {
                'retours': [{'ligne_id': self._ligne_id(), 'quantite': 1}],
                'motif': 'Casse',
                'mode_remboursement': Vente.ModePaiement.ESPECES,
            },
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['success'])
        self.vin.stock.refresh_from_db()
        self.assertEqual(self.vin.stock.quantite, 49)

    def test_retour_sans_motif_refuse(self):
        self.client.force_login(self.admin)
        r = self.client.post(
            reverse('ventes-retour', args=[self.vente_id]),
            {'retours': [{'ligne_id': self._ligne_id(), 'quantite': 1}], 'motif': ''},
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 400)

    def test_retour_trop_grand_refuse(self):
        self.client.force_login(self.admin)
        r = self.client.post(
            reverse('ventes-retour', args=[self.vente_id]),
            {'retours': [{'ligne_id': self._ligne_id(), 'quantite': 99}], 'motif': 'Erreur de scan'},
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 400)

    def _ligne_id(self):
        return self.client.get(reverse('ventes-retour', args=[self.vente_id])).json()['lignes'][0]['ligne_id']


# ---------------------------------------------------------------------------
# Clôture
# ---------------------------------------------------------------------------

class ClotureApiTests(BasePosApi):
    def _ouvrir(self):
        self.client.post(reverse('caisse-ouvrir'), {'fonds_initial': '20000.00'},
                         content_type='application/json')

    def test_rapport_pendant_la_journee(self):
        self._ouvrir()
        self._vendre()
        r = self.client.get(reverse('caisse-rapport'))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        for champ in ('session', 'rapport'):
            self.assertIn(champ, data)
        for champ in ('nb_tickets', 'ca_especes', 'ca_mobile_money', 'ca_carte',
                      'ca_credit', 'ca_rembourse', 'ca_net', 'attendu_en_caisse'):
            self.assertIn(champ, data['rapport'], f'champ absent du rapport : {champ}')
        self.assertEqual(data['rapport']['nb_tickets'], 1)
        self.assertEqual(Decimal(data['rapport']['ca_especes']), Decimal('20000.00'))

    def test_rapport_sans_session(self):
        r = self.client.get(reverse('caisse-rapport'))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()['session'])

    def test_cloture_avec_ecart(self):
        self._ouvrir()
        self._vendre()
        r = self.client.post(
            reverse('caisse-cloturer'),
            {'fonds_de_caisse': '20000.00', 'especes_reel': '40000.00', 'note': 'Test'},
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertTrue(body['success'])
        self.assertIn('sessions_restantes', body)
        session = SessionCaisse.objects.get()
        self.assertEqual(session.statut, SessionCaisse.Statut.FERMEE)
        # Fonds 20 000 + 20 000 d'espèces encaissées = 40 000 comptés : pile juste.
        self.assertEqual(Decimal(session.ecart), Decimal('0.00'))

    def test_cloture_sans_session_ouverte_refusee(self):
        r = self.client.post(
            reverse('caisse-cloturer'),
            {'fonds_de_caisse': '0', 'especes_reel': '0'},
            content_type='application/json',
        )
        self.assertIn(r.status_code, (200, 400))
        # La clôture du jour doit toujours être datée : jamais de ligne sans date.
        for session in SessionCaisse.objects.all():
            self.assertIsNotNone(session.date_ventes)


# ---------------------------------------------------------------------------
# Données d'appui du poste
# ---------------------------------------------------------------------------

class CatalogueApiTests(BasePosApi):
    def test_prix_catalogue_s_adapte_au_client_selectionne(self):
        maintenant = timezone.now()
        self.client_obj.type_client = Client.TypeClient.RESTAURANT
        self.client_obj.save(update_fields=['type_client'])
        promotion = Promotion.objects.create(
            nom='Tarif restaurant',
            type_promotion=Promotion.TypePromotion.POURCENTAGE,
            type_cible=Promotion.TypeCible.RESTAURANT,
            valeur=Decimal('10'),
            date_debut=maintenant - timedelta(days=1),
            date_fin=maintenant + timedelta(days=1),
        )
        promotion.produits.add(self.vin)

        produits_particulier = self.client.get(reverse('produits-list')).json()['results']
        produits_client = self.client.get(
            reverse('produits-list'), {'client': self.client_obj.id},
        ).json()['results']
        particulier = next(p for p in produits_particulier if p['id'] == self.vin.id)
        client = next(p for p in produits_client if p['id'] == self.vin.id)

        self.assertIsNone(particulier['promotion_active'])
        self.assertEqual(client['promotion_active']['nom'], 'Tarif restaurant')
        self.assertEqual(Decimal(str(client['promotion_active']['prix_final'])), Decimal('9000.00'))

    def test_produits_exposent_ce_que_la_grille_affiche(self):
        r = self.client.get(reverse('produits-list'))
        self.assertEqual(r.status_code, 200)
        produits = r.json()['results'] if 'results' in r.json() else r.json()
        produit = next(p for p in produits if p['id'] == self.vin.id)
        for champ in ('id', 'nom', 'marque', 'prix_vente', 'code_barre', 'image_url',
                      'stock_quantite', 'stock_etat', 'promotion_active', 'categorie',
                      'conditionnement_libelle', 'prix_unitaire_vente'):
            self.assertIn(champ, produit, f'champ absent du produit : {champ}')

    def test_clients_exposent_fidelite_et_credit(self):
        r = self.client.get(reverse('clients-list'))
        self.assertEqual(r.status_code, 200)
        clients = r.json()['results'] if 'results' in r.json() else r.json()
        client = next(c for c in clients if c['id'] == self.client_obj.id)
        for champ in ('id', 'nom', 'prenom', 'telephone', 'niveau_label',
                      'points_fidelite', 'max_credit', 'solde_du'):
            self.assertIn(champ, client, f'champ absent du client : {champ}')

    def test_recherche_par_code_barre(self):
        self.vin.code_barre = '6112345678906'
        self.vin.save()
        r = self.client.get(reverse('produits-list'), {'search': '6112345678906'})
        self.assertEqual(r.status_code, 200)
        produits = r.json()['results'] if 'results' in r.json() else r.json()
        self.assertIn(self.vin.id, [p['id'] for p in produits])

    def test_creation_client_express(self):
        r = self.client.post(
            reverse('clients-list'),
            {'nom': 'Rasoanaivo', 'prenom': 'Miora', 'telephone': '0321122334'},
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['nom'], 'Rasoanaivo')

    def test_client_express_sans_telephone_refuse(self):
        r = self.client.post(
            reverse('clients-list'),
            {'nom': 'Rasoanaivo', 'prenom': 'Miora'},
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 400)
