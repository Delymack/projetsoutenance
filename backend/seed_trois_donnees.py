#!/usr/bin/env python
"""Ajoute trois enregistrements réels par table métier.

Usage :
    venv/bin/python seed_trois_donnees.py

Principes
---------
* **Trois par table, jamais plus.** Le script est idempotent : relancé, il
  n'ajoute rien. Le tableau final compare le nombre de lignes avant / après
  et signale toute table qui dépasserait trois créations.
* **Données réelles**, pas des `test1` / `toto` : les cuvées, clients,
  fournisseurs et prix reprennent le contexte du domaine (Isaha,
  Fianarantsoa, Madagascar) et des montants en ariary plausibles.
* **Passage par les services métier** quand ils existent
  (``VenteService``, ``ReservationService``, ``ReglementService``,
  ``parametres.sauvegarde``) : la TVA, les promotions, les points de
  fidélité, les mouvements de stock et les numéros de facture sont donc
  calculés par le code de l'application, jamais à la main.
* **Aucune suppression.** Le script n'efface ni ne modifie les données
  existantes ; il ajoute uniquement.
* **Un bloc qui échoue n'arrête pas les autres** : chaque bloc est
  transactionnel et son erreur est affichée en fin de tableau.

Deux écarts volontaires à la cohérence comptable, imposés par la règle
« pas plus de trois » (voir le commentaire du bloc RETOURS) : les retours
client sont enregistrés sans leur mouvement de stock, et la clôture de
caisse réutilise la session ouverte au lieu d'en créer une quatrième.
"""

import os
import sys
import traceback
from datetime import datetime, time, timedelta
from decimal import Decimal

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.accounts.models import (  # noqa: E402
    LoginEvent, User, UserNotification, VerificationCode,
)
from apps.categories.models import Categorie  # noqa: E402
from apps.clients.models import Client, ReglementClient  # noqa: E402
from apps.parametres import sauvegarde as service_sauvegarde  # noqa: E402
from apps.parametres.models import EntreeJournal, Parametre, Sauvegarde  # noqa: E402
from apps.produits.models import Produit  # noqa: E402
from apps.promotions.models import Promotion, PromotionProduit  # noqa: E402
from apps.stocks.models import MouvementStock, Stock  # noqa: E402
from apps.ventes.models import (  # noqa: E402
    LigneReservation, LigneVente, MessageClient, Paiement, Reservation,
    RetourVente, SessionCaisse, Vente,
)
from apps.ventes.services import (  # noqa: E402
    CaisseService, ReglementService, ReservationService, VenteService,
)

# ---------------------------------------------------------------------------
# Paramètres du jeu de données — tout est ici, rien n'est enfoui plus bas.
# ---------------------------------------------------------------------------

AUJOURDHUI = timezone.localdate()

#: Mot de passe commun aux trois comptes créés. À changer après la
#: démonstration : ces comptes sont destinés à la soutenance, pas à la vente.
MOT_DE_PASSE_DEMO = 'Lazani@2026!'

#: Fonds de caisse remis au caissier en début de journée (ariary).
FONDS_DE_CAISSE = Decimal('200000.00')

#: Devise affichée dans les libellés (le projet est en ariary).
DEVISE = 'Ar'

#: Codes de vérification écrits en clair ici pour que la démonstration soit
#: rejouable : ils sont hachés en base par ``VerificationCode.set_code``.
CODES_DEMO = ('428913', '705246', '316084')

MODELES_SUIVIS = [
    User, LoginEvent, UserNotification, VerificationCode,
    Categorie, Client, ReglementClient,
    Produit, Stock, MouvementStock,
    Promotion, PromotionProduit,
    Vente, LigneVente, Paiement, RetourVente, SessionCaisse,
    Reservation, LigneReservation, MessageClient,
    Parametre, EntreeJournal, Sauvegarde,
]

# ---------------------------------------------------------------------------
# Petite infrastructure : blocs indépendants + comptage avant / après.
# ---------------------------------------------------------------------------

BLOCS = []


def bloc(titre):
    """Déclare un bloc de peuplement exécuté indépendamment des autres."""
    def enregistrer(fonction):
        BLOCS.append((titre, fonction))
        return fonction
    return enregistrer


def creer_si_absent(modele, filtre, **champs):
    """Crée la ligne si ``filtre`` ne ramène rien.

    Renvoie ``(objet, True)`` si la ligne vient d'être créée, ``(objet, False)``
    si elle existait déjà. C'est ce qui rend le script rejouable sans jamais
    dépasser trois lignes par table.
    """
    existant = modele.objects.filter(**filtre).first()
    if existant is not None:
        return existant, False
    return modele.objects.create(**{**filtre, **champs}), True


def _debut_jour(jours_avant=0):
    """Minuit local, il y a ``jours_avant`` jours."""
    jour = AUJOURDHUI - timedelta(days=jours_avant)
    return timezone.make_aware(datetime.combine(jour, time(0, 0)))


def _fin_jour(jours_apres=0):
    """23 h 59 locales, dans ``jours_apres`` jours."""
    jour = AUJOURDHUI + timedelta(days=jours_apres)
    return timezone.make_aware(datetime.combine(jour, time(23, 59, 59)))


def _afficher_tableau(avant, apres):
    """Tableau avant / après : la preuve du « trois par table, pas plus »."""
    largeur = max(len(m._meta.label) for m in MODELES_SUIVIS)
    print()
    print(f"{'table':<{largeur}}  {'avant':>7}  {'après':>7}  {'créés':>6}  état")
    print('-' * (largeur + 36))
    anomalies = []
    for modele in MODELES_SUIVIS:
        nom = modele._meta.label
        delta = apres[modele] - avant[modele]
        if delta > 3:
            etat = 'DÉPASSEMENT'
            anomalies.append(f'{nom} : {delta} lignes créées (maximum 3)')
        elif delta == 3:
            etat = 'ok'
        elif delta == 0:
            etat = 'déjà présent'
        else:
            etat = 'partiel'
        print(f'{nom:<{largeur}}  {avant[modele]:>7}  {apres[modele]:>7}  {delta:>6}  {etat}')
    return anomalies
# Objets partagés entre les blocs (comptes, clients, cuvées, ventes…).
CTX = {}


# ---------------------------------------------------------------------------
# 1. Comptes utilisateurs
# ---------------------------------------------------------------------------

@bloc('Comptes utilisateurs')
def bloc_comptes():
    comptes = [
        {
            'username': 'rakoto.andrianina',
            'email': 'rakoto.andrianina@lazani-betsileo.mg',
            'first_name': 'Andrianina',
            'last_name': 'RAKOTO',
            'role': User.Role.GESTIONNAIRE,
            'telephone': '+261 34 12 345 67',
        },
        {
            'username': 'razafy.niaina',
            'email': 'razafy.niaina@lazani-betsileo.mg',
            'first_name': 'Niaina',
            'last_name': 'RAZAFY',
            'role': User.Role.VENDEUR,
            'telephone': '+261 32 45 678 90',
        },
        {
            'username': 'hotel.lecolbert',
            'email': 'achat@hotel-lecolbert.mg',
            'first_name': 'Achat',
            'last_name': 'Le Colbert',
            'role': User.Role.CLIENT,
            'telephone': '+261 33 11 223 34',
        },
    ]
    for champs in comptes:
        username = champs.pop('username')
        existant = User.objects.filter(username=username).first()
        if existant is not None:
            CTX[username] = existant
            continue
        CTX[username] = User.objects.create_user(
            username=username, password=MOT_DE_PASSE_DEMO, **champs,
        )


# ---------------------------------------------------------------------------
# 2. Catégories du catalogue
# ---------------------------------------------------------------------------

@bloc('Catégories')
def bloc_categories():
    categories = [
        {
            'nom': 'Cuvées de garde',
            'description': "Cuvées structurées du domaine, destinées à vieillir en cave.",
        },
        {
            'nom': 'Sélection premium',
            'description': "Les bouteilles les plus régulières du domaine, servies à table.",
        },
        {
            'nom': 'Vins de terroir betsileo',
            'description': "Cuvées issues des parcelles historiques de la vallée.",
        },
    ]
    for champs in categories:
        categorie, _ = creer_si_absent(Categorie, {'nom': champs['nom']}, **{
            k: v for k, v in champs.items() if k != 'nom'
        })
        CTX[f"categorie:{champs['nom']}"] = categorie


# ---------------------------------------------------------------------------
# 3. Clients
# ---------------------------------------------------------------------------

@bloc('Clients')
def bloc_clients():
    clients = [
        {
            'nom': 'Hôtel Le Colbert',
            'prenom': 'Réception',
            'telephone': '+261 34 05 123 45',
            'email': 'achat@hotel-lecolbert.mg',
            'adresse': 'Avenue de la Libération, Fianarantsoa 301',
            'type_client': Client.TypeClient.HOTEL,
            # 16 200 points : au-dessus du seuil OR (15 000).
            'points_fidelite': 16200,
            'max_credit': Decimal('5000000.00'),
            'solde_du': Decimal('1250000.00'),
        },
        {
            'nom': 'Restaurant Le Rond-Point',
            'prenom': 'Gérance',
            'telephone': '+261 32 07 889 12',
            'email': 'contact@lerondpoint.mg',
            'adresse': 'Rue du Rova, Fianarantsoa 301',
            'type_client': Client.TypeClient.RESTAURANT,
            # 3 600 points : au-dessus du seuil ARGENT (3 000).
            'points_fidelite': 3600,
            'max_credit': Decimal('2000000.00'),
            'solde_du': Decimal('480000.00'),
        },
        {
            'nom': 'Épicerie Tsianolondroa',
            'prenom': 'Famille Rabe',
            'telephone': '+261 33 02 456 78',
            'email': None,
            'adresse': 'RN7, Tsianolondroa, Fianarantsoa',
            'type_client': Client.TypeClient.REVENDEUR,
            'points_fidelite': 780,
            'max_credit': Decimal('1000000.00'),
            'solde_du': Decimal('150000.00'),
        },
    ]
    for champs in clients:
        telephone = champs['telephone']
        client, _ = creer_si_absent(
            Client, {'telephone': telephone},
            **{k: v for k, v in champs.items() if k != 'telephone'},
        )
        CTX[f'client:{telephone}'] = client


# ---------------------------------------------------------------------------
# 4. Cuvées et leur stock d'ouverture
# ---------------------------------------------------------------------------

@bloc('Produits et stocks')
def bloc_produits():
    cuvees = [
        {
            'nom': "Côtes de l'Isaha Rouge",
            'categorie': 'Cuvées de garde',
            'type_vin': Produit.TypeVin.ROUGE,
            'code_barre': '6002100000012',
            'appellation': 'Isaha, Fianarantsoa',
            'cepage': 'Syrah, Grenache',
            'degre_alcool': Decimal('13.5'),
            'elevage': '12 mois en fût de chêne',
            'temperature_service': 17,
            'potentiel_garde': '8 à 10 ans',
            'cout_revenir': Decimal('32000.00'),
            'prix_vente': Decimal('68000.00'),
            'prix_revendeur': Decimal('52000.00'),
            'description': "La cuvée de garde du domaine : tannins serrés, notes de "
                           "mûre et de poivre, finale longue sur le terroir d'Isaha.",
            'stock_initial': 180,
            'seuil_alerte': 24,
        },
        {
            'nom': 'Ambalavao Blanc Sec',
            'categorie': 'Sélection premium',
            'type_vin': Produit.TypeVin.BLANCHE,
            'code_barre': '6002100000013',
            'appellation': 'Ambalavao',
            'cepage': 'Chenin, Ugni blanc',
            'degre_alcool': Decimal('12.0'),
            'elevage': 'Cuve inox, élevage sur lies fines',
            'temperature_service': 10,
            'potentiel_garde': '3 à 4 ans',
            'cout_revenir': Decimal('21000.00'),
            'prix_vente': Decimal('45000.00'),
            'prix_revendeur': Decimal('35000.00'),
            'description': "Blanc sec et vif, fleurs blanches et agrumes, pensé pour "
                           "les grillades et les poissons du Sud.",
            'stock_initial': 20,
            'seuil_alerte': 24,
        },
        {
            'nom': 'Rosé de la Manandona',
            'categorie': 'Vins de terroir betsileo',
            'type_vin': Produit.TypeVin.ROSE,
            'code_barre': '6002100000014',
            'appellation': 'Vallée de la Manandona',
            'cepage': 'Grenache, Cinsault',
            'degre_alcool': Decimal('12.5'),
            'elevage': 'Cuve inox, saignée',
            'temperature_service': 8,
            'potentiel_garde': '2 à 3 ans',
            'cout_revenir': Decimal('18000.00'),
            'prix_vente': Decimal('39000.00'),
            'prix_revendeur': Decimal('30000.00'),
            'description': "Rosé de saignée, frais et fruité, la bouteille d'apéritif "
                           "de la maison.",
            'stock_initial': 60,
            'seuil_alerte': 12,
        },
    ]
    for champs in cuvees:
        categorie = CTX[f"categorie:{champs.pop('categorie')}"]
        stock_initial = champs.pop('stock_initial')
        seuil_alerte = champs.pop('seuil_alerte')
        code_barre = champs['code_barre']

        produit, cree = creer_si_absent(
            Produit,
            {'code_barre': code_barre},
            marque="Lazan'i Betsileo",
            volume='75 cl',
            unite_vente=Produit.UniteVente.BOUTEILLE,
            contenance=1,
            statut=True,
            categorie=categorie,
            **{k: v for k, v in champs.items() if k != 'code_barre'},
        )
        CTX[f'produit:{code_barre}'] = produit

        # Le signal ``garantir_stock_produit`` a déjà ouvert la ligne de stock
        # à zéro : on y inscrit le stock d'ouverture réel du domaine. Sur une
        # relance, le produit existe déjà et le stock en cours n'est pas touché.
        if cree:
            stock = Stock.objects.get(produit=produit)
            stock.quantite = stock_initial
            stock.seuil_alerte = seuil_alerte
            stock.save(update_fields=['quantite', 'seuil_alerte', 'date_mise_a_jour'])


# ---------------------------------------------------------------------------
# 5. Promotions et rattachement aux cuvées
# ---------------------------------------------------------------------------

@bloc('Promotions')
def bloc_promotions():
    promotions = [
        {
            'nom': 'Récolte 2026 — 15 % sur les rouges',
            'type_promotion': Promotion.TypePromotion.POURCENTAGE,
            'valeur': Decimal('15.00'),
            'type_cible': Promotion.TypeCible.TOUS,
            'date_debut': _debut_jour(5),
            'date_fin': _fin_jour(45),
            'quantite_min': 1,
            'priorite': 5,
            'statut': True,
            'description': "Remise de campagne sur les rouges du domaine.",
            'produit': '6002100000012',
        },
        {
            'nom': 'Blancs — 5 000 Ar de remise',
            'type_promotion': Promotion.TypePromotion.MONTANT_FIXE,
            'valeur': Decimal('5000.00'),
            'type_cible': Promotion.TypeCible.REVENDEUR,
            'date_debut': _debut_jour(2),
            'date_fin': _fin_jour(30),
            'quantite_min': 6,
            'priorite': 3,
            'statut': True,
            'description': "Remise détaillant à partir de six bouteilles de blanc.",
            'produit': '6002100000013',
        },
        {
            'nom': 'Lot apéritif — 3 achetées, 1 offerte',
            'type_promotion': Promotion.TypePromotion.LOT,
            'valeur': Decimal('1.00'),
            'quantite_achetee': 3,
            'quantite_offerte': 1,
            'type_cible': Promotion.TypeCible.PARTICULIER,
            'date_debut': _debut_jour(1),
            'date_fin': _fin_jour(60),
            'quantite_min': 3,
            'priorite': 1,
            'statut': True,
            'description': "Quatre bouteilles pour le prix de trois, sur le rosé.",
            'produit': '6002100000014',
        },
    ]
    for champs in promotions:
        code_produit = champs.pop('produit')
        produit = CTX[f'produit:{code_produit}']
        promotion, _ = creer_si_absent(
            Promotion, {'nom': champs['nom']},
            **{k: v for k, v in champs.items() if k != 'nom'},
        )
        CTX[f'promotion:{champs["nom"]}'] = promotion
        # Table de liaison explicite : une ligne par couple promotion / cuvée.
        PromotionProduit.objects.get_or_create(promotion=promotion, produit=produit)
# ---------------------------------------------------------------------------
# 6. Sessions de caisse
# ---------------------------------------------------------------------------

@bloc('Sessions de caisse')
def bloc_sessions():
    caissier = CTX['razafy.niaina']

    # Deux journées déjà clôturées : l'instantané de caisse d'un jour passé.
    journees = [
        {
            'jours_avant': 2, 'nb_tickets': 9, 'nb_articles': 24,
            'ca_especes': Decimal('412000.00'), 'ca_mobile_money': Decimal('268000.00'),
            'ca_carte': Decimal('0.00'), 'ca_credit': Decimal('120000.00'),
            'remise_totale': Decimal('24000.00'), 'remise_manuelle_totale': Decimal('0.00'),
        },
        {
            'jours_avant': 1, 'nb_tickets': 6, 'nb_articles': 15,
            'ca_especes': Decimal('305000.00'), 'ca_mobile_money': Decimal('145000.00'),
            'ca_carte': Decimal('90000.00'), 'ca_credit': Decimal('0.00'),
            'remise_totale': Decimal('0.00'), 'remise_manuelle_totale': Decimal('0.00'),
        },
    ]
    for journee in journees:
        jour = AUJOURDHUI - timedelta(days=journee.pop('jours_avant'))
        ca_total = (
            journee['ca_especes'] + journee['ca_mobile_money']
            + journee['ca_carte'] + journee['ca_credit']
        )
        creer_si_absent(
            SessionCaisse,
            {'date_ventes': jour, 'utilisateur': caissier, 'statut': SessionCaisse.Statut.FERMEE},
            date_ouverture=_debut_jour(0) - timedelta(days=(AUJOURDHUI - jour).days),
            date_cloture=_debut_jour(0) - timedelta(days=(AUJOURDHUI - jour).days) + timedelta(hours=11),
            ca_total=ca_total,
            ca_net=ca_total,
            ca_rembourse=Decimal('0.00'),
            nb_retours=0,
            fonds_de_caisse=FONDS_DE_CAISSE,
            # Tiroir compté juste : fonds de caisse + les espèces encaissées.
            especes_reel=FONDS_DE_CAISSE + journee['ca_especes'],
            ecart=Decimal('0.00'),
            note='Journée clôturée sans écart.',
            **journee,
        )

    # Poste du jour. On cherche d'abord une session existante, quel que soit
    # son statut : sur une relance la journée a déjà été ouverte puis clôturée,
    # et recréer un poste ouvert donnerait une quatrième session pour le même
    # caissier — puis un conflit avec la journée déjà clôturée.
    session_jour = (
        SessionCaisse.objects
        .filter(date_ventes=AUJOURDHUI, utilisateur=caissier)
        .order_by('id').first()
    )
    if session_jour is None:
        session_jour = SessionCaisse.objects.create(
            date_ventes=AUJOURDHUI,
            utilisateur=caissier,
            statut=SessionCaisse.Statut.OUVERTE,
            date_ouverture=timezone.now(),
            fonds_de_caisse=FONDS_DE_CAISSE,
            note='Poste du jour ouvert par le caissier.',
        )
    CTX['session_jour'] = session_jour


# ---------------------------------------------------------------------------
# 7. Ventes encaissées (passage par VenteService)
# ---------------------------------------------------------------------------

@bloc('Ventes encaissées')
def bloc_ventes():
    caissier = CTX['razafy.niaina']
    session = CTX['session_jour']

    encaissements = [
        {
            'client': CTX['client:+261 34 05 123 45'],
            'produit': '6002100000012',
            'quantite': 12,
            'mode_paiement': Vente.ModePaiement.MVOLA,
            'reference_paiement': 'MVOLA-20261014-8842',
        },
        {
            'client': CTX['client:+261 32 07 889 12'],
            'produit': '6002100000013',
            'quantite': 6,
            'mode_paiement': Vente.ModePaiement.ESPECES,
            'reference_paiement': '',
        },
        {
            'client': CTX['client:+261 33 02 456 78'],
            'produit': '6002100000014',
            'quantite': 24,
            'mode_paiement': Vente.ModePaiement.ESPECES,
            'reference_paiement': '',
        },
    ]

    for encaissement in encaissements:
        client = encaissement['client']
        produit = CTX[f"produit:{encaissement['produit']}"]
        quantite = encaissement['quantite']

        # Clé naturelle : ce client a-t-il déjà une vente payée de cette cuvée
        # dans cette quantité ? Si oui, la ligne existe et on ne la recrée pas.
        deja = Vente.objects.filter(
            client=client, statut=Vente.Statut.PAYEE,
            lignes__produit=produit, lignes__quantite=quantite,
        ).exists()
        if deja:
            CTX[f"vente:{encaissement['produit']}"] = Vente.objects.filter(
                client=client, lignes__produit=produit, lignes__quantite=quantite,
            ).order_by('-id').first()
            continue

        # Le service applique la TVA, les promotions en cours, les tarifs
        # détaillant (hôtel / restaurant / revendeur), décrémente le stock,
        # écrit le mouvement de sortie et crédite les points de fidélité.
        vente = VenteService.creer_vente(
            client_id=client.id,
            mode_paiement=encaissement['mode_paiement'],
            lignes_data=[{'produit_id': produit.id, 'quantite': quantite}],
            utilisateur=caissier,
            session=session,
            reference_paiement=encaissement['reference_paiement'],
        )
        CTX[f"vente:{encaissement['produit']}"] = vente

    # Clôture du poste du jour sur les chiffres réellement calculés par la
    # caisse : aucun montant n'est saisi à la main ici. Sur une relance le
    # poste est déjà fermé : le reclôturer écraserait l'instantané existant.
    if session is not None and session.statut == SessionCaisse.Statut.OUVERTE:
        rapport = CaisseService.rapport_du_jour(AUJOURDHUI)
        CaisseService.cloturer(
            AUJOURDHUI, caissier,
            fonds_de_caisse=FONDS_DE_CAISSE,
            especes_reel=FONDS_DE_CAISSE + Decimal(rapport['ca_especes']),
            note='Clôture de démonstration, tiroir compté juste.',
        )


# ---------------------------------------------------------------------------
# 8. Retours de vente
# ---------------------------------------------------------------------------

@bloc('Retours de vente')
def bloc_retours():
    caissier = CTX['razafy.niaina']

    retours = [
        {
            'produit': '6002100000012',
            'quantite': 1,
            'motif': 'Bouteille cassée pendant le transport',
            'mode_remboursement': Vente.ModePaiement.ESPECES,
        },
        {
            'produit': '6002100000013',
            'quantite': 1,
            'motif': 'Erreur de saisie à la caisse',
            'mode_remboursement': Vente.ModePaiement.ESPECES,
        },
        {
            'produit': '6002100000014',
            'quantite': 2,
            'motif': 'Produit non conforme à la commande livrée',
            'mode_remboursement': Vente.ModePaiement.MVOLA,
        },
    ]

    for retour in retours:
        produit = CTX[f"produit:{retour['produit']}"]
        vente = CTX.get(f"vente:{retour['produit']}")
        if vente is None:
            continue
        ligne = vente.lignes.filter(produit=produit).first()
        if ligne is None:
            continue
        if RetourVente.objects.filter(vente=vente, ligne=ligne, motif=retour['motif']).exists():
            continue
        if ligne.quantite_restante < retour['quantite']:
            continue

        # Remboursement au prorata de ce qui a réellement été payé : le
        # sous-total de la ligne porte déjà la promotion et la remise.
        prix_net_unitaire = (Decimal(ligne.sous_total) / ligne.quantite).quantize(Decimal('0.01'))
        montant = prix_net_unitaire * retour['quantite']

        RetourVente.objects.create(
            vente=vente,
            ligne=ligne,
            utilisateur=caissier,
            quantite=retour['quantite'],
            motif=retour['motif'],
            mode_remboursement=retour['mode_remboursement'],
            montant_rembourse=montant,
            reference=f'RET-DEMO-{produit.code_barre[-3:]}',
        )
        vente.montant_retourne = Decimal(vente.montant_retourne) + montant
        vente.save(update_fields=['montant_retourne', 'updated_at'])

        # La marchandise revient en stock. Le mouvement de stock n'est pas
        # écrit ici : les trois mouvements autorisés pour cette table sont
        # déjà les sorties de vente du bloc précédent. RetourService, lui,
        # en ajouterait trois de plus.
        stock = Stock.objects.get(produit=produit)
        stock.quantite += retour['quantite'] * max(int(ligne.contenance or 1), 1)
        stock.save(update_fields=['quantite', 'date_mise_a_jour'])


# ---------------------------------------------------------------------------
# 9. Commandes clients
# ---------------------------------------------------------------------------

@bloc('Commandes clients')
def bloc_commandes():
    caissier = CTX['razafy.niaina']

    commandes = [
        {
            'client': CTX['client:+261 34 05 123 45'],
            'produit': '6002100000012',
            'quantite': 6,
            'source': Reservation.Source.SITE,
            'mode_reception': Reservation.ModeReception.LIVRAISON,
            'adresse_livraison': 'Avenue de la Libération, Fianarantsoa 301',
            'note': 'Commande site — livraison pour la réception du 20',
            'valider': False,
        },
        {
            'client': CTX['client:+261 32 07 889 12'],
            'produit': '6002100000013',
            'quantite': 12,
            'source': Reservation.Source.SITE,
            'mode_reception': Reservation.ModeReception.RETRAIT,
            'adresse_livraison': '',
            'note': 'Commande site — retrait au comptoir le vendredi',
            'valider': True,
        },
        {
            'client': CTX['client:+261 33 02 456 78'],
            'produit': '6002100000014',
            'quantite': 18,
            'source': Reservation.Source.INTERNE,
            'mode_reception': Reservation.ModeReception.RETRAIT,
            'adresse_livraison': '',
            'note': 'Commande prise au comptoir pour la semaine',
            'valider': False,
        },
    ]

    for commande in commandes:
        client = commande['client']
        produit = CTX[f"produit:{commande['produit']}"]
        note = commande['note']

        existante = Reservation.objects.filter(client=client, note=note).first()
        if existante is not None:
            CTX[f'reservation:{commande["produit"]}'] = existante
            continue

        reservation = ReservationService.creer(
            client_id=client.id,
            lignes_data=[{'produit_id': produit.id, 'quantite': commande['quantite']}],
            utilisateur=caissier,
            source=commande['source'],
            mode_reception=commande['mode_reception'],
            adresse_livraison=commande['adresse_livraison'],
            note=note,
        )
        # Une commande du site est validée par un responsable : on rejoue la
        # transition réelle plutôt que d'écrire le statut à la main.
        if commande['valider']:
            reservation = ReservationService.valider(reservation.id, caissier)
        CTX[f'reservation:{commande["produit"]}'] = reservation
# ---------------------------------------------------------------------------
# 10. Règlements clients
# ---------------------------------------------------------------------------

@bloc('Règlements clients')
def bloc_reglements():
    gerant = CTX['rakoto.andrianina']

    reglements = [
        {
            'client': CTX['client:+261 34 05 123 45'],
            'montant': Decimal('500000.00'),
            'mode': ReglementClient.Mode.MOBILE_MONEY,
            'reference_facture': 'FAC-2026-0912',
            'note': 'Acompte sur les livraisons de septembre',
        },
        {
            'client': CTX['client:+261 32 07 889 12'],
            'montant': Decimal('180000.00'),
            'mode': ReglementClient.Mode.ESPECES,
            'reference_facture': 'FAC-2026-0927',
            'note': 'Règlement partiel remis au comptoir',
        },
        {
            'client': CTX['client:+261 33 02 456 78'],
            'montant': Decimal('150000.00'),
            'mode': ReglementClient.Mode.CARTE,
            'reference_facture': 'FAC-2026-0930',
            'note': 'Solde de la facture de septembre',
        },
    ]

    for reglement in reglements:
        client = reglement['client']
        if ReglementClient.objects.filter(
            client=client, montant=reglement['montant'], mode=reglement['mode'],
        ).exists():
            continue
        # Le service refuse tout règlement supérieur au solde dû et met
        # l'encours du client à jour dans la même transaction.
        ReglementService.enregistrer(
            client.id, reglement['montant'], reglement['mode'],
            utilisateur=gerant,
            reference_facture=reglement['reference_facture'],
            note=reglement['note'],
        )


# ---------------------------------------------------------------------------
# 11. Messages reçus par le formulaire de contact
# ---------------------------------------------------------------------------

@bloc('Messages clients')
def bloc_messages():
    messages = [
        {
            'sujet': 'Devis pour un mariage de 120 couverts',
            'nom': 'Rasoanaivo Miora',
            'telephone': '+261 34 87 157 30',
            'email': 'rasoanaivo.miora@gmail.com',
            'message': "Bonjour, nous organisons un mariage le 12 décembre à "
                       "Fianarantsoa et cherchons 40 bouteilles de rouge et 30 de "
                       "blanc. Pouvez-vous nous faire un devis avec la livraison ?",
            'statut': MessageClient.Statut.NOUVEAU,
        },
        {
            'sujet': 'Disponibilité du Rosé de la Manandona',
            'nom': 'Rakotondrainibe Hery',
            'telephone': '+261 32 66 412 08',
            'email': 'hery.rakotondrainibe@yahoo.fr',
            'message': "Bonjour, avez-vous encore du rosé de la Manandona en stock ? "
                       "J'en voudrais six bouteilles pour ce week-end.",
            'statut': MessageClient.Statut.TRAITE,
        },
        {
            'sujet': 'Livraison possible à Toliara ?',
            'nom': 'Épicerie du Sud',
            'telephone': '+261 33 45 908 71',
            'email': 'contact@epiceriedusud.mg',
            'message': "Nous sommes une épicerie à Toliara et souhaitons référencer "
                       "vos cuvées. Proposez-vous une livraison en dehors de "
                       "Fianarantsoa, et à partir de quel volume ?",
            'statut': MessageClient.Statut.ARCHIVE,
        },
    ]
    for message in messages:
        creer_si_absent(
            MessageClient, {'sujet': message['sujet']},
            **{k: v for k, v in message.items() if k != 'sujet'},
        )


# ---------------------------------------------------------------------------
# 12. Historique de connexion
# ---------------------------------------------------------------------------

@bloc('Historique de connexion')
def bloc_connexions():
    evenements = [
        {
            'user': CTX['rakoto.andrianina'],
            'statut': LoginEvent.Statut.SUCCESS,
            'ip': '192.168.1.10',
            'appareil': 'Firefox 132 · Windows',
            'heures_avant': 6,
        },
        {
            'user': CTX['razafy.niaina'],
            'statut': LoginEvent.Statut.SUCCESS,
            'ip': '192.168.1.42',
            'appareil': 'Chrome 130 · Linux',
            'heures_avant': 5,
        },
        {
            'user': CTX['hotel.lecolbert'],
            'statut': LoginEvent.Statut.FAILED,
            'ip': '41.188.12.7',
            'appareil': 'Chrome 130 · Android',
            'heures_avant': 2,
        },
    ]
    for evenement in evenements:
        creer_si_absent(
            LoginEvent,
            {'user': evenement['user'], 'statut': evenement['statut'], 'ip': evenement['ip']},
            appareil=evenement['appareil'],
            user_agent='Mozilla/5.0 (compatible; démonstration de soutenance)',
            cree_le=timezone.now() - timedelta(hours=evenement['heures_avant']),
        )


# ---------------------------------------------------------------------------
# 13. Notifications utilisateur
# ---------------------------------------------------------------------------

@bloc('Notifications utilisateur')
def bloc_notifications():
    gerant = CTX['rakoto.andrianina']
    caissier = CTX['razafy.niaina']
    commande_hotel = CTX['reservation:6002100000012']
    commande_restaurant = CTX['reservation:6002100000013']
    blanc_sec = CTX['produit:6002100000013']

    notifications = [
        # Une commande du site attend encore une validation : l'alerte est
        # réellement non lue.
        {'user': gerant, 'key': f'commande-client:web:{commande_hotel.id}',
         'etat': UserNotification.Etat.NON_LUE},
        # Le blanc sec est passé sous son seuil d'alerte après la vente du jour.
        {'user': gerant, 'key': f'stock:faible:{blanc_sec.id}',
         'etat': UserNotification.Etat.NON_LUE},
        # Le caissier a déjà traité la commande du restaurant.
        {'user': caissier, 'key': f'commande-client:web:{commande_restaurant.id}',
         'etat': UserNotification.Etat.LUE},
    ]
    for notification in notifications:
        creer_si_absent(
            UserNotification,
            {'user': notification['user'], 'key': notification['key']},
            etat=notification['etat'],
        )


# ---------------------------------------------------------------------------
# 14. Codes de vérification en cours
# ---------------------------------------------------------------------------

@bloc('Codes de vérification')
def bloc_codes():
    from django.contrib.auth.hashers import make_password

    codes = [
        {
            'contact': 'rasoanaivo.miora@gmail.com',
            'contact_type': VerificationCode.CONTACT_EMAIL,
            'purpose': VerificationCode.PURPOSE_SIGNUP,
            'code': CODES_DEMO[0],
            'user_data': {
                'nom': 'Rasoanaivo Miora',
                'email': 'rasoanaivo.miora@gmail.com',
                'telephone': '+261 34 87 157 30',
                'password': make_password('Rasoanaivo@2026'),
            },
        },
        {
            'contact': '+261 32 66 412 08',
            'contact_type': VerificationCode.CONTACT_SMS,
            'purpose': VerificationCode.PURPOSE_LOGIN,
            'code': CODES_DEMO[1],
            'user_data': None,
        },
        {
            'contact': '+261 33 45 908 71',
            'contact_type': VerificationCode.CONTACT_SMS,
            'purpose': VerificationCode.PURPOSE_SIGNUP,
            'code': CODES_DEMO[2],
            'user_data': {
                'nom': 'Épicerie du Sud',
                'email': 'contact@epiceriedusud.mg',
                'telephone': '+261 33 45 908 71',
                'password': make_password('EpicerieSud@2026'),
            },
        },
    ]
    for entree in codes:
        if VerificationCode.objects.filter(
            contact=entree['contact'], purpose=entree['purpose'],
        ).exists():
            continue
        vc = VerificationCode.objects.create(
            contact=entree['contact'],
            contact_type=entree['contact_type'],
            purpose=entree['purpose'],
            code_hash='',
            expires_at=timezone.now() + timedelta(minutes=10),
            user_data=entree['user_data'],
        )
        # Le code est haché en base, jamais stocké en clair.
        vc.set_code(entree['code'])


# ---------------------------------------------------------------------------
# 15. Paramètres explicitement enregistrés
# ---------------------------------------------------------------------------

@bloc('Paramètres')
def bloc_parametres():
    parametres = [
        {
            'section': 'VENTES', 'cle': 'ventes_tva',
            'libelle': 'Taux de TVA (en %)', 'type': 'DECIMAL', 'valeur': '20', 'ordre': 40,
            'aide': "Taux appliqué aux nouvelles factures.",
        },
        {
            'section': 'VENTES', 'cle': 'ventes_delai_paiement_jours',
            'libelle': 'Délai de paiement des factures (jours)', 'type': 'INT',
            'valeur': '60', 'ordre': 46,
            'aide': "Échéance portée sur la facture à l'émission.",
        },
        {
            'section': 'POS', 'cle': 'pos_alerte_rupture',
            'libelle': 'Alerter les ruptures de stock', 'type': 'BOOL',
            'valeur': '1', 'ordre': 30,
            'aide': "Signale à la caisse les cuvées en rupture.",
        },
    ]
    for parametre in parametres:
        creer_si_absent(
            Parametre, {'cle': parametre['cle']},
            **{k: v for k, v in parametre.items() if k != 'cle'},
        )

    # Le catalogue de paramètres est mis en cache : sans cette purge, la
    # console d'administration continuerait d'afficher les valeurs par défaut.
    from django.core.cache import cache
    from apps.parametres.services import CACHE_KEY
    cache.delete(CACHE_KEY)


# ---------------------------------------------------------------------------
# 16. Sauvegardes de la base
# ---------------------------------------------------------------------------

@bloc('Sauvegardes')
def bloc_sauvegardes():
    gerant = CTX['rakoto.andrianina']

    # ``creer`` produit un vrai fichier de dump dans media/sauvegardes/AAAA/MM/
    # et journalise l'opération. On garde purger=False : le script ne doit
    # jamais supprimer de sauvegarde existante.
    for _ in range(3):
        if Sauvegarde.objects.filter(statut=Sauvegarde.Statut.REUSSIE).count() >= 3:
            break
        service_sauvegarde.creer(utilisateur=gerant, purger=False)


# ---------------------------------------------------------------------------
# Exécution
# ---------------------------------------------------------------------------

def principal():
    print(f"Jeu de trois données par table — {AUJOURDHUI:%d/%m/%Y}")
    print(f"Base utilisée : {__import__('django.conf', fromlist=['settings']).settings.DATABASES['default']['ENGINE']}")
    print()

    avant = {modele: modele.objects.count() for modele in MODELES_SUIVIS}

    erreurs = []
    for titre, fonction in BLOCS:
        try:
            with transaction.atomic():
                fonction()
            print(f'  ok      {titre}')
        except Exception as exc:  # noqa: BLE001 — un bloc cassé ne doit pas tout arrêter
            erreurs.append((titre, exc))
            print(f'  ERREUR  {titre} : {type(exc).__name__} — {exc}')

    apres = {modele: modele.objects.count() for modele in MODELES_SUIVIS}
    anomalies = _afficher_tableau(avant, apres)

    if erreurs:
        print()
        print('Blocs en erreur :')
        for titre, exc in erreurs:
            print(f'  - {titre} : {type(exc).__name__} — {exc}')
        print()
        print('Détail de la dernière erreur :')
        traceback.print_exception(type(erreurs[-1][1]), erreurs[-1][1], erreurs[-1][1].__traceback__)

    if anomalies:
        print()
        print('Tables au-delà de trois créations :')
        for anomalie in anomalies:
            print(f'  - {anomalie}')

    if erreurs or anomalies:
        print()
        print('Terminé avec des anomalies : rien n\'a été supprimé, relancez après correction.')
        return 1

    print()
    print(f"Terminé. Mot de passe des trois comptes créés : {MOT_DE_PASSE_DEMO}")
    return 0


if __name__ == '__main__':
    sys.exit(principal())