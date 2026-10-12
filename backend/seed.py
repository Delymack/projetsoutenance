"""Jeu de données de démonstration pour LAZAN'I BETSILEO.

La cave produit ses cuvées : le stock d'ouverture est saisi directement.

    python seed.py                    # base métier vide uniquement
    python seed.py --reset-demo-data  # destructif : base de démonstration uniquement
"""
import argparse
import os
from datetime import timedelta
from decimal import Decimal

import django
from django.core.management.base import CommandError
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

from apps.accounts.models import LoginEvent  # noqa: E402
from apps.categories.models import Categorie  # noqa: E402
from apps.clients.models import Client, ReglementClient  # noqa: E402
from apps.produits.models import Produit  # noqa: E402
from apps.promotions.models import Promotion, PromotionProduit  # noqa: E402
from apps.stocks.models import Stock  # noqa: E402
from apps.ventes.models import SessionCaisse, Vente  # noqa: E402
from apps.ventes.services import CaisseService, ReglementService, VenteService  # noqa: E402

User = get_user_model()

MARQUE = "LAZAN'I BETSILEO"
ANNEE = timezone.localdate().year


def run_seed(reset_demo_data=False):
    if not reset_demo_data:
        donnees_metier = (
            SessionCaisse, ReglementClient, Vente, Promotion, Stock,
            Produit, Categorie, Client, LoginEvent,
        )
        if any(modele.objects.exists() for modele in donnees_metier) or User.objects.exclude(
            is_superuser=True
        ).exists():
            raise CommandError(
                "Le seed refuse de supprimer des données existantes. "
                "Sur une base de démonstration uniquement, relancez avec "
                "--reset-demo-data."
            )

    print("Nettoyage des tables (ordre FK sûr)...")
    SessionCaisse.objects.all().delete()
    ReglementClient.objects.all().delete()
    Vente.objects.all().delete()
    Promotion.objects.all().delete()
    Stock.objects.all().delete()
    Produit.objects.all().delete()
    Categorie.objects.all().delete()
    Client.objects.all().delete()
    LoginEvent.objects.all().delete()
    User.objects.exclude(is_superuser=True).delete()

    # ------------------------------------------------------------------
    # Utilisateurs
    # ------------------------------------------------------------------
    print("Création de 3 Utilisateurs (Vendeurs)...")
    vendeurs = []
    for i in range(1, 4):
        vendeurs.append(User.objects.create_user(
            username=f'vendeur{i}',
            email=f'vendeur{i}@lazani-betsileo.mg',
            password='password123',
            first_name=['Hery', 'Mialy', 'Tiana'][i - 1],
            last_name=['Rakotomalala', 'Andrianarivelo', 'Rabe'][i - 1],
            role=User.Role.VENDEUR,
            # Les vendeurs utilisent le back-office Django pour la caisse.
            # Django exige is_staff=True pour autoriser /admin/login/.
            is_staff=True,
        ))

    print("Création de 3 Événements de connexion...")
    LoginEvent.objects.create(user=vendeurs[0], statut=LoginEvent.Statut.SUCCESS, ip="192.168.1.10",
                              user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)", appareil="Chrome — Windows")
    LoginEvent.objects.create(user=vendeurs[1], statut=LoginEvent.Statut.SUCCESS, ip="10.0.0.5",
                              user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X)", appareil="Firefox — macOS")
    LoginEvent.objects.create(user=vendeurs[2], statut=LoginEvent.Statut.FAILED, ip="10.0.0.9",
                              user_agent="Mozilla/5.0 (Linux; Android 14)", appareil="Chrome — Android")

    # ------------------------------------------------------------------
    # Catalogue
    # ------------------------------------------------------------------
    print("Création de 3 Catégories...")
    categories = []
    for nom, description in [
        ("Rouges", "Cuvées rouges des hautes terres, élevage en fût de chêne."),
        ("Blancs", "Vins blancs frais, vendange manuelle, fermentation en cuve."),
        ("Rosés & Pétillants", "Rosés de pressée et vins pétillants méthode traditionnelle."),
    ]:
        categories.append(Categorie.objects.create(nom=nom, description=description, statut=True))

    print("Création de 3 Clients (niveaux variés)...")
    clients = [
        Client.objects.create(
            nom="Établissements", prenom="Partenaire Isaha", telephone="034 00 000 01",
            adresse="Isaha, Fianarantsoa", type_client=Client.TypeClient.REVENDEUR,
            points_fidelite=0, max_credit=Decimal('2500000.00'),
        ),
        Client.objects.create(
            nom="Andrianarivelo", prenom="Mialy", telephone="033 98 765 43",
            email="mialy.andrianarivelo@gmail.com", adresse="Antananarivo — Ivandry",
            points_fidelite=8000,
        ),
        Client.objects.create(
            nom="Rabe", prenom="Tiana", telephone="032 11 223 34",
            email="tiana.rabe@gmail.com", adresse="Fianarantsoa — Isaha",
            points_fidelite=180000,
        ),
    ]

    print("Création de 3 Cuvées avec Stocks...")
    produits_data = [
        {
            "nom": "Vin Rouge LAZAN'I BETSILEO 75cl", "type": "Rouge", "millesime": None,
            "cout_revenir": "18000.00", "prix_revendeur": "35000.00",
            "prix_vente": "38000.00",
            "appellation": "Fianarantsoa",
            "cepage": "", "degre_alcool": "13.5",
            "elevage": "", "temperature_service": "17", "potentiel_garde": "",
            "desc": "Vin rouge 75 cl de la gamme LAZAN'I BETSILEO.",
        },
        {
            "nom": "Vin Blanc Moelleux LAZAN'I BETSILEO 75cl", "type": "Blanche", "millesime": None,
            "cout_revenir": "14000.00", "prix_revendeur": "27000.00",
            "prix_vente": "30000.00",
            "appellation": "Fianarantsoa",
            "cepage": "", "degre_alcool": "12.0",
            "elevage": "", "temperature_service": "8", "potentiel_garde": "",
            "desc": "Vin blanc moelleux 75 cl de la gamme LAZAN'I BETSILEO.",
        },
        {
            "nom": "Vin Rouge Doux LAZAN'I BETSILEO 75cl", "type": "Rouge", "millesime": None,
            "cout_revenir": "20000.00", "prix_revendeur": "40000.00",
            "prix_vente": "45000.00",
            "appellation": "Fianarantsoa",
            "cepage": "", "degre_alcool": "12.5",
            "elevage": "", "temperature_service": "12", "potentiel_garde": "",
            "desc": "Vin rouge doux 75 cl de la gamme LAZAN'I BETSILEO.",
        },
    ]
    produits = []
    for i, p in enumerate(produits_data):
        prod = Produit.objects.create(
            nom=p["nom"], description=p["desc"], type_vin=p["type"],
            marque=MARQUE, millesime=p["millesime"], volume="75cl",
            appellation=p["appellation"], cepage=p["cepage"],
            degre_alcool=Decimal(p["degre_alcool"]), elevage=p["elevage"],
            temperature_service=int(p["temperature_service"]),
            potentiel_garde=p["potentiel_garde"],
            cout_revenir=Decimal(p["cout_revenir"]),
            prix_revendeur=Decimal(p["prix_revendeur"]),
            prix_vente=Decimal(p["prix_vente"]),
            categorie=categories[i], statut=True,
        )
        Stock.objects.filter(produit=prod).update(quantite=0, seuil_alerte=24)
        produits.append(prod)

    # ------------------------------------------------------------------
    # Approvisionnement de la cave
    # ------------------------------------------------------------------
    # La cave produit ses cuvées : le stock d'ouverture est saisi directement.
    # Les deux premières cuvées sont en cave ; la troisième n'est pas encore
    # embouteillée. Le prix d'achat reste renseigné à titre indicatif.
    print("Mise en stock des cuvées...")
    for produit, quantite, prix_achat in zip(
        produits, (180, 240, 0), ['17500', '13800', '19500']
    ):
        produit.prix_achat = Decimal(prix_achat)
        produit.save(update_fields=['prix_achat'])
        Stock.objects.filter(produit=produit).update(quantite=quantite)

    # ------------------------------------------------------------------
    # Commerce
    # ------------------------------------------------------------------
    print("Création de 3 Promotions (dont une expirée)...")
    promo_active = Promotion.objects.create(
        nom="Vendange fraîche",
        description="15 % de remise particuliers sur les cuvées sélectionnées.",
        type_promotion=Promotion.TypePromotion.POURCENTAGE,
        valeur=Decimal('15.00'),
        type_cible=Promotion.TypeCible.PARTICULIER,
        date_debut=timezone.now() - timedelta(days=2),
        date_fin=timezone.now() + timedelta(days=10),
        statut=True,
    )
    promo_fixe = Promotion.objects.create(
        nom="Offre Dégustation",
        description="10 000 Ar offerts sur le pétillant brut.",
        type_promotion=Promotion.TypePromotion.MONTANT_FIXE,
        valeur=Decimal('10000.00'),
        date_debut=timezone.now() - timedelta(days=5),
        date_fin=timezone.now() + timedelta(days=5),
        statut=True,
    )
    Promotion.objects.create(
        nom="Fin de millésime",
        description="Offre de fin d'année, désormais terminée.",
        type_promotion=Promotion.TypePromotion.POURCENTAGE,
        valeur=Decimal('20.00'),
        date_debut=timezone.now() - timedelta(days=30),
        date_fin=timezone.now() - timedelta(days=10),
        statut=False,
    )
    PromotionProduit.objects.create(promotion=promo_active, produit=produits[0])
    PromotionProduit.objects.create(promotion=promo_fixe, produit=produits[2])
    PromotionProduit.objects.create(promotion=promo_active, produit=produits[1])

    print("Création de 3 Ventes (une à crédit)...")
    # Le pétillant n'a pas été commandé : il n'y en a pas en cave. Les ventes
    # portent donc sur les deux cuvées réceptionnées.
    ventes_data = [
        {"client": clients[0], "vendeur": vendeurs[0], "mode": Vente.ModePaiement.ESPECES,
         "lignes": [{"produit_id": produits[0].id, "quantite": 2}]},
        {"client": clients[1], "vendeur": vendeurs[1], "mode": Vente.ModePaiement.MOBILE_MONEY,
         "lignes": [{"produit_id": produits[1].id, "quantite": 3}]},
        {"client": clients[0], "vendeur": vendeurs[2], "mode": Vente.ModePaiement.CREDIT,
         "lignes": [{"produit_id": produits[1].id, "quantite": 2}]},
    ]
    for v in ventes_data:
        VenteService.creer_vente(
            client_id=v["client"].id,
            mode_paiement=v["mode"],
            lignes_data=v["lignes"],
            utilisateur=v["vendeur"],
        )

    print("Création de 3 Règlements clients (crédit partiellement apuré)...")
    # La vente à crédit applique le tarif détaillant : 54 000 Ar, dont
    # 45 000 Ar encaissés ensuite, 9 000 Ar restent dus.
    reglements = [
        {"montant": Decimal('20000.00'), "mode": ReglementClient.Mode.ESPECES,
         "reference_facture": "FAC-2026-0101", "note": "Premier versement."},
        {"montant": Decimal('15000.00'), "mode": ReglementClient.Mode.MOBILE_MONEY,
         "reference_facture": "FAC-2026-0102", "note": "Acompte Mobile Money."},
        {"montant": Decimal('10000.00'), "mode": ReglementClient.Mode.CARTE,
         "reference_facture": "FAC-2026-0103", "note": "Solde partiel."},
    ]
    for r in reglements:
        ReglementService.enregistrer(
            client_id=clients[0].id, montant=r["montant"], mode=r["mode"],
            utilisateur=vendeurs[0], reference_facture=r["reference_facture"], note=r["note"],
        )

    print("Création de 3 clôtures de caisse...")
    for i, j in enumerate([timezone.localdate() - timedelta(days=d) for d in (0, 1, 3)]):
        CaisseService.cloturer(
            jour=j, utilisateur=vendeurs[i], fonds_de_caisse=50000,
            especes_reel=None, note=f"Clôture de démonstration n°{i + 1}",
        )

    print("--- SEED TERMINE : 3 exemples par table ---")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Charger les données de démonstration WineAdmin.")
    parser.add_argument(
        '--reset-demo-data',
        action='store_true',
        help='supprimer les données existantes avant de recréer les exemples (base de démonstration uniquement)',
    )
    arguments = parser.parse_args()
    try:
        run_seed(reset_demo_data=arguments.reset_demo_data)
    except CommandError as erreur:
        parser.error(str(erreur))
