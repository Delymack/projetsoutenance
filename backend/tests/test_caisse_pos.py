"""
Tests des fonctionnalités de caisse ajoutées au poste de vente :
paiement mixte, remise manuelle, retours partiels, sessions, réservations,
conditionnements et codes-barres.
"""

from decimal import Decimal

from django.db.models import Sum
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.clients.models import Client
from apps.produits.barcode import (
    _PATTERNS_128,
    START_B,
    STOP,
    cle_ean13_valide,
    modules_du_code,
    svg,
    valider_code,
)
from apps.produits.models import Produit
from apps.stocks.models import Stock
from apps.ventes.models import Paiement, Reservation, SessionCaisse, Vente
from apps.ventes.politiques import plafond_remise
from rest_framework.exceptions import ValidationError

from apps.ventes.services import (
    CaisseService,
    ReservationService,
    RetourService,
    VenteService,
)


def cles_erreur(erreur):
    """Clés de premier niveau d'une ValidationError (DRF ou Django)."""
    detail = getattr(erreur, 'detail', None) or getattr(erreur, 'message_dict', {})
    if isinstance(detail, dict):
        return set(detail)
    return set()


class BaseCaisse(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123',
        )
        self.vendeur = User.objects.create_user(
            username='vendeur', email='vendeur@test.com', password='password123',
            role=User.Role.VENDEUR,
        )
        self.client_obj = Client.objects.create(
            nom="Rakoto", prenom="Hanta", telephone="0340000000",
        )
        self.vin = self._produit("Cuvée 2018", prix=Decimal('10000.00'), stock=50)
        self.petit = self._produit("Pétillant", prix=Decimal('4000.00'), stock=6)

    def _produit(self, nom, prix, stock, **kwargs):
        produit = Produit.objects.create(
            nom=nom, type_vin="Rouge", marque="Domaine",
            cout_revenir=prix / 2, prix_vente=prix, statut=True, **kwargs,
        )
        Stock.objects.update_or_create(
            produit=produit, defaults={'quantite': stock, 'seuil_alerte': 2},
        )
        return produit

    def _vente(self, lignes=None, paiements=None, motif_remise='',
               utilisateur=None, mode=Vente.ModePaiement.ESPECES):
        return VenteService.creer_vente(
            client_id=self.client_obj.id,
            mode_paiement=mode,
            lignes_data=lignes or [{'produit_id': self.vin.id, 'quantite': 2}],
            utilisateur=utilisateur or self.vendeur,
            paiements=paiements,
            motif_remise=motif_remise,
        )


# ---------------------------------------------------------------------------
# Paiement mixte
# ---------------------------------------------------------------------------

class PaiementMixteTests(BaseCaisse):
    def test_deux_modes_creent_deux_lignes(self):
        vente = self._vente(paiements=[
            {'mode': Vente.ModePaiement.ESPECES, 'montant': Decimal('10000.00')},
            {'mode': Vente.ModePaiement.MOBILE_MONEY, 'montant': Decimal('10000.00')},
        ])

        self.assertEqual(vente.total, Decimal('20000.00'))
        self.assertEqual(vente.paiements.count(), 2)
        self.assertTrue(vente.est_paiement_mixte)
        # Le mode principal reste renseigné pour les exports et le Z-Report.
        self.assertEqual(vente.mode_paiement, Vente.ModePaiement.ESPECES)

    def test_somme_insuffisante_refusee(self):
        with self.assertRaises(ValidationError) as ctx:
            self._vente(paiements=[
                {'mode': Vente.ModePaiement.ESPECES, 'montant': Decimal('5000.00')},
                {'mode': Vente.ModePaiement.CARTE, 'montant': Decimal('5000.00')},
            ])
        self.assertIn('paiements', cles_erreur(ctx.exception))

    def test_somme_excessive_refusee(self):
        with self.assertRaises(ValidationError):
            self._vente(paiements=[
                {'mode': Vente.ModePaiement.ESPECES, 'montant': Decimal('25000.00')},
            ])

    def test_paiement_simple_legacy_toujours_accepte(self):
        """Le champ historique mode_paiement + montant reste valable."""
        vente = self._vente(mode=Vente.ModePaiement.CARTE)
        self.assertEqual(vente.paiements.count(), 1)
        self.assertEqual(vente.paiements.first().mode, Vente.ModePaiement.CARTE)
        self.assertFalse(vente.est_paiement_mixte)

    def test_vente_et_stock_atomiques(self):
        stock_avant = Stock.objects.get(produit=self.vin).quantite
        with self.assertRaises(ValidationError):
            self._vente(paiements=[
                {'mode': Vente.ModePaiement.ESPECES, 'montant': Decimal('1.00')},
            ])
        self.assertEqual(Stock.objects.get(produit=self.vin).quantite, stock_avant)
        self.assertFalse(Vente.objects.exists())


# ---------------------------------------------------------------------------
# Remise manuelle
# ---------------------------------------------------------------------------

class RemiseManuelleTests(BaseCaisse):
    def test_motif_obligatoire_des_quil_y_a_remise(self):
        with self.assertRaises(ValidationError) as ctx:
            self._vente(
                lignes=[{'produit_id': self.vin.id, 'quantite': 1, 'remise_manuelle': Decimal('500.00')}],
                motif_remise='',
            )
        self.assertIn('motif_remise', cles_erreur(ctx.exception))

    def test_sans_remise_le_motif_est_inutile(self):
        vente = self._vente(motif_remise='')
        self.assertEqual(vente.remise_manuelle_totale, Decimal('0.00'))

    def test_vendeur_plafonne_a_cinq_pourcents(self):
        # 2 × 10 000 = 20 000 de brut, plafond vendeur = 1 000.
        self.assertEqual(plafond_remise(self.vendeur, Decimal('20000.00')), Decimal('1000.00'))

        vente = self._vente(lignes=[{
            'produit_id': self.vin.id, 'quantite': 2, 'remise_manuelle': Decimal('1000.00'),
        }], motif_remise="Client fidèle")
        self.assertEqual(vente.remise_manuelle_totale, Decimal('1000.00'))
        self.assertEqual(vente.total, Decimal('19000.00'))
        self.assertEqual(vente.motif_remise, "Client fidèle")

    def test_vendeur_au_dela_du_plafond_refuse(self):
        with self.assertRaises(ValidationError):
            self._vente(lignes=[{
                'produit_id': self.vin.id, 'quantite': 2, 'remise_manuelle': Decimal('1500.00'),
            }], motif_remise="Trop gros")

    def test_administrateur_non_plafonne(self):
        self.assertIsNone(plafond_remise(self.admin, Decimal('20000.00')))
        vente = self._vente(
            lignes=[{'produit_id': self.vin.id, 'quantite': 2, 'remise_manuelle': Decimal('8000.00')}],
            motif_remise="Geste commercial exceptionnel", utilisateur=self.admin,
        )
        self.assertEqual(vente.total, Decimal('12000.00'))

    def test_remise_superieure_a_la_ligne_refusee(self):
        with self.assertRaises(ValidationError):
            self._vente(
                lignes=[{'produit_id': self.vin.id, 'quantite': 1, 'remise_manuelle': Decimal('99999.00')}],
                motif_remise="Erreur de saisie", utilisateur=self.admin,
            )


# ---------------------------------------------------------------------------
# Retours partiels
# ---------------------------------------------------------------------------

class RetoursPartielsTests(BaseCaisse):
    def test_retour_partiel_ajoute_le_stock_sans_bouger_le_total(self):
        vente = self._vente()
        ligne = vente.lignes.first()
        total_initial = vente.total

        retours, vente = RetourService.enregistrer(
            vente.id, [{'ligne_id': ligne.id, 'quantite': 1}], motif='Bouteille cassée',
            utilisateur=self.vendeur,
        )
        vente.refresh_from_db()

        self.assertEqual(vente.total, total_initial)          # inchangé : la vente existe
        self.assertEqual(vente.montant_retourne, Decimal('10000.00'))
        self.assertEqual(vente.total_net, Decimal('10000.00'))
        # 50 - 2 + 1
        self.assertEqual(Stock.objects.get(produit=self.vin).quantite, 49)
        self.assertEqual(len(retours), 1)
        self.assertEqual(retours[0].montant_rembourse, Decimal('10000.00'))
        self.assertEqual(retours[0].quantite, 1)

    def test_quantite_superieure_a_la_ligne_refusee(self):
        vente = self._vente()
        ligne = vente.lignes.first()
        with self.assertRaises(ValidationError):
            RetourService.enregistrer(
                vente.id, [{'ligne_id': ligne.id, 'quantite': 99}], motif='Erreur',
                utilisateur=self.vendeur,
            )

    def test_quantite_deja_retournee_refusee(self):
        vente = self._vente()
        ligne = vente.lignes.first()
        # Les 2 bouteilles sont restituées : il n'en reste plus à reprendre.
        RetourService.enregistrer(
            vente.id, [{'ligne_id': ligne.id, 'quantite': 2}], motif='Casse', utilisateur=self.vendeur,
        )
        with self.assertRaises(ValidationError) as ctx:
            RetourService.enregistrer(
                vente.id, [{'ligne_id': ligne.id, 'quantite': 1}], motif='Encore', utilisateur=self.vendeur,
            )
        self.assertIn('retours', cles_erreur(ctx.exception))
        vente.refresh_from_db()
        self.assertEqual(vente.montant_retourne, Decimal('20000.00'))

    def test_motif_obligatoire(self):
        vente = self._vente()
        ligne = vente.lignes.first()
        with self.assertRaises(ValidationError) as ctx:
            RetourService.enregistrer(vente.id, [{'ligne_id': ligne.id, 'quantite': 1}], motif='')
        self.assertIn('retours', cles_erreur(ctx.exception))

    def test_retour_complet_rend_la_ligne_entierement_reversible(self):
        vente = self._vente()
        ligne = vente.lignes.first()
        RetourService.enregistrer(
            vente.id, [{'ligne_id': ligne.id, 'quantite': 2}], motif='Erreur de saisie',
            utilisateur=self.vendeur,
        )
        vente.refresh_from_db()
        self.assertEqual(vente.montant_retourne, Decimal('20000.00'))
        self.assertEqual(vente.total_net, Decimal('0.00'))

    def test_rapport_compte_le_ca_net(self):
        vente = self._vente()
        ligne = vente.lignes.first()
        RetourService.enregistrer(
            vente.id, [{'ligne_id': ligne.id, 'quantite': 1}], motif='Casse', utilisateur=self.vendeur,
        )
        rapport = CaisseService.rapport_du_jour(timezone.localdate())
        self.assertEqual(rapport['ca_total'], Decimal('20000.00'))
        self.assertEqual(rapport['ca_rembourse'], Decimal('10000.00'))
        self.assertEqual(rapport['ca_net'], Decimal('10000.00'))
        self.assertEqual(rapport['nb_retours'], 1)


# ---------------------------------------------------------------------------
# Sessions de caisse
# ---------------------------------------------------------------------------

class SessionCaisseTests(BaseCaisse):
    def test_ouvrir_puis_encaisser(self):
        session = CaisseService.ouvrir(
            timezone.localdate(), self.vendeur, fonds_initial=Decimal('5000.00'),
        )
        self.assertEqual(session.statut, SessionCaisse.Statut.OUVERTE)
        self.assertFalse(CaisseService.session_requise_et_absente(self.vendeur))

    def test_deux_caissiers_peuvent_tenir_deux_postes_le_meme_jour(self):
        autre = User.objects.create_user(
            username='vendeur2', email='v2@test.com', password='password123',
            role=User.Role.VENDEUR,
        )
        CaisseService.ouvrir(timezone.localdate(), self.vendeur, fonds_initial=0)
        CaisseService.ouvrir(timezone.localdate(), autre, fonds_initial=0)
        self.assertEqual(
            SessionCaisse.objects.filter(
                date_ventes=timezone.localdate(), statut=SessionCaisse.Statut.OUVERTE,
            ).count(),
            2,
        )

    def test_deux_clotures_le_meme_jour_ne_se_confondent_pas(self):
        autre = User.objects.create_user(
            username='vendeur2', email='v2@test.com', password='password123',
            role=User.Role.VENDEUR,
        )
        CaisseService.cloturer(timezone.localdate(), self.vendeur, fonds_de_caisse=0)
        CaisseService.cloturer(timezone.localdate(), autre, fonds_de_caisse=0)
        self.assertEqual(
            SessionCaisse.objects.filter(
                date_ventes=timezone.localdate(), statut=SessionCaisse.Statut.FERMEE,
            ).count(),
            2,
        )

    def test_cloture_signale_les_postes_encores_ouverts(self):
        autre = User.objects.create_user(
            username='vendeur2', email='v2@test.com', password='password123',
            role=User.Role.VENDEUR,
        )
        CaisseService.ouvrir(timezone.localdate(), autre, fonds_initial=0)
        session = CaisseService.cloturer(timezone.localdate(), self.vendeur, fonds_de_caisse=0)
        restants = [p.utilisateur.username for p in session.sessions_restantes]
        self.assertEqual(restants, ['vendeur2'])

    def test_cloture_idempotente(self):
        CaisseService.cloturer(timezone.localdate(), self.vendeur, fonds_de_caisse=0, especes_reel=0)
        session = CaisseService.cloturer(
            timezone.localdate(), self.vendeur, fonds_de_caisse=0, especes_reel=0,
        )
        self.assertEqual(
            SessionCaisse.objects.filter(
                date_ventes=timezone.localdate(), statut=SessionCaisse.Statut.FERMEE,
            ).count(),
            1,
        )
        self.assertEqual(session.ecart, Decimal('0.00'))

    def test_ecart_calcule(self):
        CaisseService.ouvrir(timezone.localdate(), self.vendeur, fonds_initial=Decimal('5000.00'))
        self._vente(mode=Vente.ModePaiement.ESPECES)  # 20 000 espèces
        session = CaisseService.cloturer(
            timezone.localdate(), self.vendeur,
            fonds_de_caisse=Decimal('5000.00'), especes_reel=Decimal('24500.00'),
        )
        self.assertEqual(session.ecart, Decimal('-500.00'))


# ---------------------------------------------------------------------------
# Réservations et acomptes
# ---------------------------------------------------------------------------

class ReservationTests(BaseCaisse):
    def test_reserver_ne_bouge_pas_le_stock(self):
        stock_avant = Stock.objects.get(produit=self.vin).quantite
        reservation = ReservationService.creer(
            client_id=self.client_obj.id,
            lignes_data=[{'produit_id': self.vin.id, 'quantite': 6}],
            utilisateur=self.vendeur,
            acompte=Decimal('20000.00'),
            mode_acompte=Vente.ModePaiement.ESPECES,
        )
        self.assertEqual(reservation.montant_total, Decimal('60000.00'))
        self.assertEqual(Stock.objects.get(produit=self.vin).quantite, stock_avant)
        self.assertEqual(reservation.statut, Reservation.Statut.ACOMPTE)
        self.assertEqual(reservation.solde_du, Decimal('40000.00'))
        # L'acompte est bien de l'argent en caisse.
        self.assertTrue(
            Paiement.objects.filter(reservation=reservation, vente__isnull=True).exists()
        )

    def test_reservation_sans_acompte_en_attente(self):
        reservation = ReservationService.creer(
            client_id=self.client_obj.id,
            lignes_data=[{'produit_id': self.vin.id, 'quantite': 2}],
            utilisateur=self.vendeur,
        )
        self.assertEqual(reservation.statut, Reservation.Statut.EN_ATTENTE)
        self.assertEqual(reservation.solde_du, Decimal('20000.00'))

    def test_encaisser_cree_la_vente_et_bouge_le_stock(self):
        stock_avant = Stock.objects.get(produit=self.vin).quantite
        reservation = ReservationService.creer(
            client_id=self.client_obj.id,
            lignes_data=[{'produit_id': self.vin.id, 'quantite': 3}],
            utilisateur=self.vendeur,
            acompte=Decimal('10000.00'), mode_acompte=Vente.ModePaiement.ESPECES,
        )
        vente, reservation = ReservationService.encaisser(
            reservation.id, mode_paiement=Vente.ModePaiement.MOBILE_MONEY,
            utilisateur=self.vendeur,
        )

        # Le lien passe par la réservation : c'est elle qui porte la vente.
        self.assertEqual(reservation.vente_id, vente.id)
        self.assertEqual(vente.acompte_anticipe, Decimal('10000.00'))
        self.assertEqual(vente.total, Decimal('30000.00'))
        # L'acompte n'est pas encaissé une seconde fois.
        encaisse = vente.paiements.aggregate(total=Sum('montant'))['total']
        self.assertEqual(Decimal(encaisse), Decimal('20000.00'))
        self.assertEqual(Stock.objects.get(produit=self.vin).quantite, stock_avant - 3)
        self.assertEqual(reservation.statut, Reservation.Statut.SOLDEE)
        self.assertEqual(reservation.solde_du, Decimal('0.00'))

    def test_reservation_plus_de_stock_refusee(self):
        ReservationService.creer(
            client_id=self.client_obj.id,
            lignes_data=[{'produit_id': self.petit.id, 'quantite': 6}],
            utilisateur=self.vendeur,
        )
        Stock.objects.filter(produit=self.petit).update(quantite=1)
        reservation = Reservation.objects.filter(lignes__produit=self.petit).distinct().first()
        with self.assertRaises(ValidationError) as ctx:
            ReservationService.encaisser(
                reservation.id, mode_paiement=Vente.ModePaiement.ESPECES, utilisateur=self.vendeur,
            )
        self.assertIn('stock', cles_erreur(ctx.exception))

    def test_annulation_liberale_sans_bouger_le_stock(self):
        reservation = ReservationService.creer(
            client_id=self.client_obj.id,
            lignes_data=[{'produit_id': self.vin.id, 'quantite': 2}],
            utilisateur=self.vendeur,
        )
        ReservationService.annuler(reservation.id)
        reservation.refresh_from_db()
        self.assertEqual(reservation.statut, Reservation.Statut.ANNULEE)
        self.assertEqual(Stock.objects.get(produit=self.vin).quantite, 50)

    def test_acompte_au_dela_du_total_refuse(self):
        with self.assertRaises(ValidationError) as ctx:
            ReservationService.creer(
                client_id=self.client_obj.id,
                lignes_data=[{'produit_id': self.vin.id, 'quantite': 1}],
                utilisateur=self.vendeur,
                acompte=Decimal('999999.00'), mode_acompte=Vente.ModePaiement.ESPECES,
            )
        self.assertIn('acompte', cles_erreur(ctx.exception))


# ---------------------------------------------------------------------------
# Conditionnements
# ---------------------------------------------------------------------------

class ConditionnementTests(BaseCaisse):
    def test_vente_en_bouteille_par_defaut(self):
        self.assertEqual(self.vin.unite_vente, Produit.UniteVente.BOUTEILLE)
        self.assertEqual(self.vin.bouteilles_par_unite, 1)
        self.assertEqual(self.vin.prix_unitaire_vente, Decimal('10000.00'))

    def test_pack_de_six(self):
        self.vin.unite_vente = Produit.UniteVente.PACK
        self.vin.contenance = 6
        self.vin.save()
        self.assertEqual(self.vin.bouteilles_par_unite, 6)
        self.assertEqual(self.vin.prix_unitaire_vente, Decimal('60000.00'))
        self.assertEqual(self.vin.par_bouteille, Decimal('10000.00'))

    def test_prix_de_lot_dedie(self):
        self.vin.unite_vente = Produit.UniteVente.CARTON
        self.vin.contenance = 12
        self.vin.prix_conditionnement = Decimal('100000.00')
        self.vin.save()
        self.assertEqual(self.vin.prix_unitaire_vente, Decimal('100000.00'))
        self.assertEqual(self.vin.par_bouteille, Decimal('8333.33'))

    def test_vente_d_un_carton_consomme_le_stock_en_bouteilles(self):
        stock_avant = Stock.objects.get(produit=self.vin).quantite
        self.vin.unite_vente = Produit.UniteVente.PACK
        self.vin.contenance = 6
        self.vin.save()
        vente = self._vente(lignes=[{'produit_id': self.vin.id, 'quantite': 2}])
        self.assertEqual(vente.total, Decimal('120000.00'))
        self.assertEqual(Stock.objects.get(produit=self.vin).quantite, stock_avant - 12)

    def test_stock_insuffisant_en_bouteilles_refuse(self):
        self.petit.unite_vente = Produit.UniteVente.CARTON
        self.petit.contenance = 6
        self.petit.save()
        stock_avant = Stock.objects.get(produit=self.petit).quantite  # 6 bouteilles
        with self.assertRaises(ValidationError):
            self._vente(lignes=[{'produit_id': self.petit.id, 'quantite': 2}])  # 12 demandées
        self.assertEqual(Stock.objects.get(produit=self.petit).quantite, stock_avant)


# ---------------------------------------------------------------------------
# Codes-barres
# ---------------------------------------------------------------------------

class CodeBarreTests(TestCase):
    def test_symboles_hors_norme_code128(self):
        """Les symboles spéciaux doivent correspondre à la norme."""
        self.assertEqual(_PATTERNS_128[START_B], '211214')   # Start B
        self.assertEqual(_PATTERNS_128[STOP], '2331112')     # Stop, 7 éléments

    def test_code128_se_termeine_sur_une_barre(self):
        modules = modules_du_code('AB')
        # Un code démarre et finit sur une barre : nombre impair d'éléments.
        self.assertEqual(len(modules) % 2, 1)
        # La largeur d'un élément ne dépasse jamais 4 modules en Code 128 :
        # c'est la régression de l'espacement inter-symboles qui élargissait
        # artificiellement les barres et rendait le code illisible.
        self.assertLessEqual(max(modules), 4)

    def test_ean13_a_la_bonne_longueur(self):
        code = Produit.generer_code_interne(1)
        self.assertEqual(len(code), 13)
        self.assertTrue(cle_ean13_valide(code))
        # 3 (garde) + 6 x 7 (gauche) + 5 (séparateur) + 6 x 7 (droite) + 3 (garde)
        self.assertEqual(len(modules_du_code(code)), 95)

    def test_code_interne_unique_et_incrementale(self):
        codes = {Produit.generer_code_interne(i) for i in range(1, 200)}
        self.assertEqual(len(codes), 199)
        self.assertTrue(all(c.startswith('200') for c in codes))

    def test_attribuer_code_barre_ne_double_pas(self):
        premier = Produit.objects.create(nom='A', type_vin='Rouge', marque='D', cout_revenir=1, prix_vente=2)
        second = Produit.objects.create(nom='B', type_vin='Rouge', marque='D', cout_revenir=1, prix_vente=2)

        code_premier = premier.attribuer_code_barre()
        premier.save()
        code_second = second.attribuer_code_barre()
        second.save()

        self.assertNotEqual(code_premier, code_second)
        self.assertTrue(cle_ean13_valide(code_premier))
        # Un second appel ne change rien.
        self.assertEqual(premier.attribuer_code_barre(), code_premier)

    def test_valider_code(self):
        self.assertEqual(valider_code('  REF-VIN  '), 'REF-VIN')
        for invalide in ('', '   ', 'ab', 'cafe\u00e9'):
            with self.assertRaises(ValueError, msg=repr(invalide)):
                valider_code(invalide)

    def test_cle_ean13_invalide_detectee(self):
        bon = Produit.generer_code_interne(1)
        mauvais = bon[:12] + str((int(bon[12]) + 1) % 10)
        self.assertFalse(cle_ean13_valide(mauvais))
        self.assertFalse(cle_ean13_valide('2000000000'))   # mauvaise longueur
        self.assertFalse(cle_ean13_valide('abcdefghijklm'))

    def test_svg_contient_les_barres(self):
        rendu = svg(Produit.generer_code_interne(1), hauteur=40)
        self.assertTrue(rendu.startswith('<svg'))
        self.assertTrue(rendu.endswith('</svg>'))
        # 95 modules => 48 barres, plus le fond blanc.
        self.assertEqual(rendu.count('<rect'), 49)
