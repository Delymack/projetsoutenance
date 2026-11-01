"""Catalogue de démonstration — AJOUT SEUL, aucun effacement.

`seed.py` refuse de s'exécuter dès qu'un compte non-superutilisateur existe
(c'est le cas sur cette base) et son option `--reset-demo-data` supprimerait
les comptes, les clients et les ventes. Ce script-ci ne crée QUE le catalogue
(catégories, produits, stocks, promotions) et s'arrête si des produits
existent déjà :

    python seed_catalogue.py

Les cuvées reprennent celles du jeu de démonstration du frontend
(`frontend/src/app/core/data/mock-vins.ts`) pour que la
page principale affiche exactement ce que la maquette annonçait.
"""
import os
from datetime import timedelta
from decimal import Decimal

import django
from django.core.management.base import CommandError
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.categories.models import Categorie  # noqa: E402
from apps.produits.models import Produit  # noqa: E402
from apps.promotions.models import Promotion  # noqa: E402
from apps.stocks.models import Stock  # noqa: E402

# (nom, description)
CATEGORIES = [
    ("Rouges", "Cuvées rouges des hautes terres, élevage en fût de chêne."),
    ("Blancs", "Vins blancs frais, vendange manuelle, fermentation en cuve."),
    ("Rosés", "Rosés de pressée, à boire jeunes et frais."),
    ("Mousseux", "Vins pétillants, méthode traditionnelle betsileo."),
    ("Liqueurs & Apéritifs", "Liqueurs et apéritifs de cépages, service frais."),
]

# (nom, type_vin, categorie, cépage, appellation, marque, prix_vente,
#  stock, seuil_alerte, degré, description)
PRODUITS = [
    ("Tsiky dia Loatra", "Rouge", "Rouges", "Syrah", "Fianarantsoa",
     "Domaine Tsiky", 55000, 42, 10, 13.5,
     "Rouge profond des hautes terres betsileo, syrah vieillie en fût de chêne "
     "local. Tanins soyeux, finale longue et poivrée."),
    ("Gris de Betsileo", "Blanche", "Blancs", "Viognier", "Fianarantsoa",
     "Domaine Tsiky", 38000, 65, 10, 12.5,
     "Blanc sec et minéral, nez d'agrumes confits et de fleurs blanches. "
     "Idéal sur les entrées et les poissons de rivière."),
    ("Rosé d'Ihosy", "Rose", "Rosés", "Cabernet Sauvignon", "Ihosy",
     "Cave d'Ihosy", 35000, 30, 10, 12.0,
     "Rosé de pressée directe, fruits rouges frais et bouche vive. "
     "Le vin des après-midi chauds."),
    ("Pétillant de Tsarasaotra", "Blanche", "Mousseux", "Colombard",
     "Tsarasaotra", "Maison Tsarasaotra", 80000, 18, 6, 11.5,
     "Pétillant méthode traditionnelle, bulle fine et finale sèche. "
     "Pour les grandes occasions."),
    ("Malbec Ambatondrazaka", "Rouge", "Rouges", "Malbec", "Ambatondrazaka",
     "Domaine Ambatondrazaka", 58000, 55, 10, 14.0,
     "Malbec charpenté des hautes terres, fruits noirs et réglisse. "
     "Compagnon des viandes grillées."),
    ("Vermentino Antsirabe", "Blanche", "Blancs", "Vermentino", "Antsirabe",
     "Domaine Vert", 42000, 38, 10, 13.0,
     "Blanc de montagne, floral et salin, élevé sur lies fines."),
    ("Cuvée des Rogations", "Rose", "Rosés", "Merlot", "Fianarantsoa",
     "Domaine Tsiky", 39000, 26, 10, 11.0,
     "Rosé doux et fruité, notes de pêche et de grenadine."),
    ("Pinot Noir Androy", "Rouge", "Rouges", "Pinot Noir", "Androy",
     "Domaine Androy", 75000, 4, 6, 13.5,
     "Cuvée prestige, pinot noir délicat et parfumé, élevage long. "
     "Stock limité."),
    ("Liqueur de Moussafely", "Liqueur", "Liqueurs & Apéritifs", "Assemblage",
     "Moussafely", "Maison Moussafely", 52000, 0, 5, 20.0,
     "Liqueur de cépages, notes de miel et d'orange amère. "
     "À servir très frais."),
    ("Sauvignon Blanc Vakio", "Blanche", "Blancs", "Sauvignon Blanc",
     "Vakio", "Domaine Vakio", 33000, 72, 12, 12.0,
     "Blanc vif et aromatique, buis et pamplemousse."),
    ("Cabernet Fianarantsoa", "Rouge", "Rouges", "Cabernet Sauvignon",
     "Fianarantsoa", "Domaine Tsiky", 60000, 48, 10, 13.5,
     "Cuvée charpentée, tanins fermes et longue garde."),
    ("Vendange d'Or", "Blanche", "Mousseux", "Chardonnay", "Tsarasaotra",
     "Maison Tsarasaotra", 92000, 8, 4, 12.5,
     "Mousseux de prestige, chardonnay vinifié en blanc de blancs."),
]

# (nom, pourcentage, produits ciblés, catégories ciblées)
PROMOTIONS = [
    ("Fête des vendanges -18 %", Decimal('18'),
     ["Tsiky dia Loatra", "Pétillant de Tsarasaotra", "Cabernet Fianarantsoa"], []),
    ("Happy hour Rouges -10 %", Decimal('10'), [], ["Rouges"]),
]


def run_seed_catalogue():
    if Produit.objects.exists():
        raise CommandError(
            "Des produits existent déjà : ce script n'écrase rien. "
            "Supprimez-les explicitement (ou utilisez seed.py --reset-demo-data) "
            "si vous voulez repartir du catalogue de démonstration."
        )

    print("Catégories…")
    categories = {}
    for nom, description in CATEGORIES:
        categories[nom] = Categorie.objects.create(nom=nom, description=description)

    print(f"Produits ({len(PRODUITS)})…")
    produits = {}
    for (
        nom, type_vin, categorie, cepage, appellation, marque,
        prix_vente, stock, seuil, degre, description,
    ) in PRODUITS:
        prix = Decimal(prix_vente)
        produit = Produit.objects.create(
            nom=nom,
            description=description,
            type_vin=type_vin,
            marque=marque,
            volume="75 cl",
            appellation=appellation,
            cepage=cepage,
            degre_alcool=Decimal(str(degre)),
            elevage="Fût de chêne local" if type_vin == "Rouge" else "Cuve inox",
            temperature_service=16 if type_vin == "Rouge" else 8,
            potentiel_garde="5 ans",
            # Coût d'achat à 70 % du tarif public : la marge reste réaliste
            # pour les écrans du back-office.
            cout_revenir=Decimal('0'),
            prix_achat=(prix * Decimal('0.70')).quantize(Decimal('1')),
            prix_vente=prix,
            prix_revendeur=Decimal('0'),
            code_barre=f"6002100000{len(produits) + 1:03d}",
            unite_vente=Produit.UniteVente.BOUTEILLE,
            contenance=1,
            statut=True,
            categorie=categories[categorie],
        )
        # Le signal post_save de `apps.produits` garantit déjà l'existence de
        # la ligne de stock (quantité 0) : on la met à jour au lieu d'en créer
        # une seconde, ce que la contrainte d'unicité refuserait.
        Stock.objects.filter(produit=produit).update(quantite=stock, seuil_alerte=seuil)
        produits[nom] = produit

    print(f"Promotions ({len(PROMOTIONS)})…")
    maintenant = timezone.now()
    for nom, pourcentage, cibles_produits, cibles_categories in PROMOTIONS:
        promotion = Promotion.objects.create(
            nom=nom,
            description="Campagne de démonstration créée par seed_catalogue.py.",
            type_promotion=Promotion.TypePromotion.POURCENTAGE,
            valeur=pourcentage,
            type_cible=Promotion.TypeCible.TOUS,
            date_debut=maintenant - timedelta(days=1),
            date_fin=maintenant + timedelta(days=30),
            statut=True,
            priorite=1,
        )
        promotion.produits.add(*[produits[n] for n in cibles_produits])
        promotion.categories.add(*[categories[n] for n in cibles_categories])

    print(
        f"Terminé : {len(produits)} produits, {len(categories)} catégories, "
        f"{len(PROMOTIONS)} promotions actives."
    )


if __name__ == '__main__':
    run_seed_catalogue()