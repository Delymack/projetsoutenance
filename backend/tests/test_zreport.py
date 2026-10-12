from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.produits.models import Produit
from apps.stocks.models import Stock
from apps.clients.models import Client
from apps.ventes.models import Vente, LigneVente, SessionCaisse
from apps.ventes.services import CaisseService


class ClotureCaisseTests(TestCase):
    def setUp(self):
        self.vendeur = User.objects.create_user(
            username='caissier', email='caissier@test.com', password='password123',
        )
        self.client_obj = Client.objects.create(nom="Caisse", prenom="Test", telephone="0350000000")
        self.produit = Produit.objects.create(
            nom="Vin de Cave 2020", type_vin="Rouge", marque="Caviste",
            cout_revenir=Decimal('4000.00'), prix_vente=Decimal('10000.00'), statut=True,
        )
        Stock.objects.update_or_create(produit=self.produit, defaults={'quantite': 50, 'seuil_alerte': 5})

    def _vente(self, mode=Vente.ModePaiement.ESPECES, quantite=2):
        vente = Vente.objects.create(
            client=self.client_obj, utilisateur=self.vendeur,
            mode_paiement=mode, total=0,
        )
        ligne = LigneVente.objects.create(
            vente=vente, produit=self.produit, quantite=quantite,
            prix_unitaire=self.produit.prix_vente, remise=Decimal('0.00'),
            sous_total=self.produit.prix_vente * quantite,
        )
        vente.total = ligne.sous_total
        vente.save()
        return vente

    def test_rapport_du_jour_compte_les_payees(self):
        self._vente()
        self._vente(mode=Vente.ModePaiement.MOBILE_MONEY, quantite=1)
        jour = timezone.localdate()

        rapport = CaisseService.rapport_du_jour(jour)
        self.assertEqual(rapport['ca_total'], Decimal('30000.00'))
        self.assertEqual(rapport['ca_especes'], Decimal('20000.00'))
        self.assertEqual(rapport['ca_mobile_money'], Decimal('10000.00'))
        self.assertEqual(rapport['nb_tickets'], 2)
        self.assertEqual(rapport['nb_articles'], 3)
        self.assertEqual(rapport['nb_par_mode'][Vente.ModePaiement.ESPECES], 1)

    def test_rapport_ignore_les_annulees(self):
        vente = self._vente()
        vente.statut = Vente.Statut.ANNULEE
        vente.save(update_fields=['statut'])

        rapport = CaisseService.rapport_du_jour(timezone.localdate())
        self.assertEqual(rapport['ca_total'], Decimal('0.00'))
        self.assertEqual(rapport['nb_tickets'], 0)

    def test_cloture_archive_et_calcule_ecart(self):
        self._vente()  # 20000 espèces
        jour = timezone.localdate()

        session = CaisseService.cloturer(
            jour=jour, utilisateur=self.vendeur,
            fonds_de_caisse=5000, especes_reel=24500, note="Bon encaissement",
        )
        self.assertEqual(session.ecart, Decimal('-500.00'))  # 24500 - (5000+20000)
        self.assertEqual(SessionCaisse.objects.filter(date_ventes=jour).count(), 1)

        # Idempotent : une nouvelle clôture réécrit la précédente.
        session2 = CaisseService.cloturer(jour=jour, utilisateur=self.vendeur, fonds_de_caisse=5000, especes_reel=25000)
        self.assertEqual(SessionCaisse.objects.filter(date_ventes=jour).count(), 1)
        self.assertEqual(session2.ecart, Decimal('0.00'))
