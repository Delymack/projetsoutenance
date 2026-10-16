#!/usr/bin/env python
"""Retire exactement ce que ``seed_trois_donnees.py`` a ajouté.

Usage :
    venv/bin/python revert_seed_trois_donnees.py

Ce script ne supprime **que** les lignes créées par le peuplement du
14/10/2026, identifiées par leurs clés naturelles (codes-barres, téléphones,
noms de cuvées, comptes…). Aucune donnée antérieure n'est touchée : ni vos
61 connexions, ni vos 18 codes, ni vos 10 cuvées d'origine.

Le tableau final compare l'état obtenu à l'état d'avant le peuplement.
"""

import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import transaction  # noqa: E402

from apps.accounts.models import (  # noqa: E402
    LoginEvent, User, UserNotification, VerificationCode,
)
from apps.categories.models import Categorie  # noqa: E402
from apps.clients.models import Client, ReglementClient  # noqa: E402
from apps.parametres.models import EntreeJournal, Parametre, Sauvegarde  # noqa: E402
from apps.produits.models import Produit  # noqa: E402
from apps.promotions.models import Promotion, PromotionProduit  # noqa: E402
from apps.stocks.models import MouvementStock, Stock  # noqa: E402
from apps.ventes.models import (  # noqa: E402
    LigneReservation, LigneVente, MessageClient, Paiement, Reservation,
    RetourVente, SessionCaisse, Vente,
)

# --- Clés naturelles de ce qui a été ajouté ---------------------------------

COMPTES = ['rakoto.andrianina', 'razafy.niaina', 'hotel.lecolbert']
TELEPHONES_CLIENTS = ['+261 34 05 123 45', '+261 32 07 889 12', '+261 33 02 456 78']
CODES_BARRES = ['6002100000012', '6002100000013', '6002100000014']
NOMS_CATEGORIES = ['Cuvées de garde', 'Sélection premium', 'Vins de terroir betsileo']
NOMS_PROMOTIONS = [
    'Récolte 2026 — 15 % sur les rouges',
    'Blancs — 5 000 Ar de remise',
    'Lot apéritif — 3 achetées, 1 offerte',
]
SUJETS_MESSAGES = [
    'Devis pour un mariage de 120 couverts',
    'Disponibilité du Rosé de la Manandona',
    'Livraison possible à Toliara ?',
]
CONTACTS_CODES = ['rasoanaivo.miora@gmail.com', '+261 32 66 412 08', '+261 33 45 908 71']
CLES_PARAMETRES = ['ventes_tva', 'ventes_delai_paiement_jours', 'pos_alerte_rupture']

# --- État d'avant le peuplement, table par table ----------------------------
# Relevé avant la première exécution du script d'ajout : c'est la cible à
# retrouver, et la preuve qu'aucune donnée d'origine n'a été emportée.

CIBLE = {
    'accounts.User': 7,
    'accounts.LoginEvent': 61,
    'accounts.UserNotification': 10,
    'accounts.VerificationCode': 18,
    'categories.Categorie': 5,
    'clients.Client': 3,
    'clients.ReglementClient': 0,
    'produits.Produit': 10,
    'stocks.Stock': 10,
    'stocks.MouvementStock': 5,
    'promotions.Promotion': 5,
    'promotions.PromotionProduit': 6,
    'ventes.Vente': 4,
    'ventes.LigneVente': 5,
    'ventes.Paiement': 4,
    'ventes.RetourVente': 0,
    'ventes.SessionCaisse': 3,
    'ventes.Reservation': 4,
    'ventes.LigneReservation': 5,
    'ventes.MessageClient': 0,
    'parametres.Parametre': 0,
    'parametres.EntreeJournal': 0,
    'parametres.Sauvegarde': 0,
}

MODELES_SUIVIS = [
    User, LoginEvent, UserNotification, VerificationCode,
    Categorie, Client, ReglementClient,
    Produit, Stock, MouvementStock,
    Promotion, PromotionProduit,
    Vente, LigneVente, Paiement, RetourVente, SessionCaisse,
    Reservation, LigneReservation, MessageClient,
    Parametre, EntreeJournal, Sauvegarde,
]

suppressions = []


def supprimer(queryset, libelle):
    """Supprime le queryset et mémorise le nombre de lignes retirées."""
    nombre = queryset.count()
    if nombre:
        queryset.delete()
    suppressions.append((libelle, nombre))


def principal():
    # Les comptes créés servent de pivot : tout ce qui leur est rattaché doit
    # partir avant eux, sinon Django refuse (on_delete=PROTECT).
    comptes = User.objects.filter(username__in=COMPTES)
    clients = Client.objects.filter(telephone__in=TELEPHONES_CLIENTS)
    produits = Produit.objects.filter(code_barre__in=CODES_BARRES)
    promotions = Promotion.objects.filter(nom__in=NOMS_PROMOTIONS)
    ventes = Vente.objects.filter(client__in=clients)
    commandes = Reservation.objects.filter(client__in=clients)

    with transaction.atomic():
        # 1. Descendance des ventes : retours, paiements, lignes, puis la vente.
        supprimer(RetourVente.objects.filter(vente__in=ventes), 'RetourVente')
        supprimer(Paiement.objects.filter(vente__in=ventes), 'Paiement (ventes)')
        supprimer(LigneVente.objects.filter(vente__in=ventes), 'LigneVente')
        # 2. Descendance des cuvées : mouvements, liaisons, stock.
        supprimer(MouvementStock.objects.filter(produit__in=produits), 'MouvementStock')
        supprimer(PromotionProduit.objects.filter(produit__in=produits), 'PromotionProduit')
        supprimer(Stock.objects.filter(produit__in=produits), 'Stock')
        # 3. Descendance des commandes clients.
        supprimer(LigneReservation.objects.filter(reservation__in=commandes), 'LigneReservation')
        supprimer(Reservation.objects.filter(client__in=clients), 'Reservation')
        # 4. Ce qui bloque encore la suppression des clients et des comptes.
        supprimer(ventes, 'Vente')
        supprimer(ReglementClient.objects.filter(client__in=clients), 'ReglementClient')
        supprimer(SessionCaisse.objects.filter(utilisateur__in=comptes), 'SessionCaisse')
        # 5. Catalogue et promotions.
        supprimer(promotions, 'Promotion')
        supprimer(produits, 'Produit')
        supprimer(Categorie.objects.filter(nom__in=NOMS_CATEGORIES), 'Categorie')
        # 6. Traces et messages.
        supprimer(MessageClient.objects.filter(sujet__in=SUJETS_MESSAGES), 'MessageClient')
        supprimer(VerificationCode.objects.filter(contact__in=CONTACTS_CODES), 'VerificationCode')
        supprimer(UserNotification.objects.filter(user__in=comptes), 'UserNotification')
        supprimer(LoginEvent.objects.filter(user__in=comptes), 'LoginEvent')
        supprimer(Parametre.objects.filter(cle__in=CLES_PARAMETRES), 'Parametre')

        # Sauvegardes : la ligne et le fichier de dump qu'elle a produit.
        sauvegardes = list(Sauvegarde.objects.all())
        fichiers = [s.fichier.name for s in sauvegardes if s.fichier]
        supprimer(Sauvegarde.objects.all(), 'Sauvegarde')
        supprimer(EntreeJournal.objects.all(), 'EntreeJournal')

        # Enfin les clients et les comptes, une fois leur descendance partie.
        supprimer(clients, 'Client')
        supprimer(comptes, 'User')

    # Le catalogue de paramètres est mis en cache : sans cette purge, la
    # console continuerait d'afficher les valeurs retirées.
    from django.core.cache import cache
    from apps.parametres.services import CACHE_KEY
    cache.delete(CACHE_KEY)

    for nom in fichiers:
        try:
            from django.core.files.storage import default_storage
            if default_storage.exists(nom):
                default_storage.delete(nom)
                print(f'  fichier retiré : {nom}')
        except Exception as exc:  # noqa: BLE001
            print(f'  fichier non retiré : {nom} ({exc})')

    # --- Tableau de contrôle ------------------------------------------------
    largeur = max(len(m._meta.label) for m in MODELES_SUIVIS)
    print()
    print(f"{'table':<{largeur}}  {'cible':>6}  {'obtenu':>6}  état")
    print('-' * (largeur + 24))
    ecarts = []
    for modele in MODELES_SUIVIS:
        nom = modele._meta.label
        obtenu = modele.objects.count()
        cible = CIBLE[nom]
        if obtenu == cible:
            etat = 'ok'
        elif obtenu < cible:
            etat = 'MANQUE DES LIGNES'
            ecarts.append(f'{nom} : {obtenu} lignes au lieu de {cible}')
        else:
            etat = 'lignes en trop'
            ecarts.append(f'{nom} : {obtenu} lignes au lieu de {cible}')
        print(f'{nom:<{largeur}}  {cible:>6}  {obtenu:>6}  {etat}')

    print()
    total = sum(nombre for _, nombre in suppressions)
    print(f'Lignes supprimées : {total}')
    for libelle, nombre in suppressions:
        if nombre:
            print(f'  {libelle:<20} {nombre:>3}')

    if ecarts:
        print()
        print('Écarts à examiner :')
        for ecart in ecarts:
            print(f'  - {ecart}')
        return 1

    print()
    print("Retour à l'état d'avant le peuplement : toutes les tables concordent.")
    return 0


if __name__ == '__main__':
    sys.exit(principal())