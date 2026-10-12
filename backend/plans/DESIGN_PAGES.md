# Design des pages backend — Wine Management

> Spécification du design optimal et des fonctionnalités de chaque page de l'interface backend (admin Django + Jazzmin).
> Thème : « lux » — élégance, noir profond, accents or/doré.

---

## 1. Charte graphique globale

> **Implémenté dans `static/css/wineadmin-design.css`** (chargé par `templates/admin/base.html`).
> Ce fichier est la **source de vérité unique** : plus de `<style>` inline ni de couleur
> en dur dans les gabarits ou les `ModelAdmin`.

| Élément | Valeur |
|---|---|
| Thème | `lux` (Jazzmin) |
| Sidebar | sombre bordeaux, icônes en 3 teintes |
| Police | Fine, grands espaces (style haut de gamme) |
| Icône marque | 🍷 WineAdmin |
| Palette | **3 couleurs maximum** + échelle neutre |

**Palette — 3 couleurs de marque (norme stricte)**

| # | Teinte | Rôle | Code |
|---|---|---|---|
| 1 | **GRENAT** | primaire, action, danger, encours | `#641b2c` |
| 2 | **OR** | accent, attention, fidélité, action principale | `#c99b3b` |
| 3 | **SAGE** | succès, disponible, stock normal | `#2f6b4f` |

L'échelle **neutre** (encre `#2b1b20` et ses déclinaisons) couvre fonds, bordures et
textes secondaires sans introduire de 4e teinte.

**Règles d'emploi**

| Besoin | Classe CSS | Rendu |
|---|---|---|
| En-tête de section | `.lb-hero` | dégradé grenat + bouton or |
| Tuile d'indicateur | `.lb-kpi` + `lb-kpi-ok` / `-warn` / `-danger` / `-neutral` | filet coloré à gauche |
| Pastille / badge | `.lb-badge` + `lb-badge-wine` / `-gold` / `-sage` / `-muted` | |
| Valeur colorée | `.lb-val-wine` / `.lb-val-gold` / `.lb-val-sage` / `.lb-val-muted` | |
| Barre (crédit, fidélité, rendement) | `.lb-bar` + `is-warn` / `is-danger` | |
| Filtre rapide | `.lb-segment` | |
| Fiche 360° | `.lb-grid`, `.lb-col-*`, `.lb-timeline`, `.lb-facts` | |
| Encart | `.lb-hint` + `-wine` / `-sage` | |

**Garde-fous** : `tests/test_design_system.py` échoue si une couleur hors palette
réapparaît dans un `change_list.html` ou si les trois teintes de marque disparaissent
des tokens.

---

## 2. Page de connexion

**Objectif** : accès sécurisé, image de marque premium.

**Design**
- Fond dégradé sombre avec motif discret de bouteilles/vignes.
- Carte centrale blanche, coins arrondis, ombre portée.
- Logo 🍷 + « WineAdmin » en en-tête.
- Champs : identifiant, mot de passe (avec icône œil pour afficher/masquer).
- Bouton « Se connecter » noir avec survol doré.
- Lien « Mot de passe oublié ».

**Fonctionnalités**
- Validation côté client (champs requis).
- Message d'erreur clair en cas d'échec.
- Case « Se souvenir de moi ».
- Redirection automatique selon le rôle (Admin → dashboard, Vendeur → POS).

---

## 3. Dashboard (page d'accueil admin)

**Fichier actuel** : [`templates/admin/index.html`](templates/admin/index.html:1)

**Objectif** : vue synthétique de l'activité en un coup d'œil.

### Design actuel (à conserver)
- **4 cartes KPI** en dégradé : CA, Ventes, Produits, Ruptures.
- **Graphique** des ventes des 7 derniers jours (Chart.js, courbe remplie).
- **2 tableaux** : 5 dernières ventes + alertes stocks faibles.
- **Menu des apps** en cartes avec boutons Ajouter/Liste.

### Améliorations recommandées
| Amélioration | Bénéfice |
|---|---|
| Ajouter un **sélecteur de période** (7j / 30j / année) | Analyse flexible |
| Ajouter un **graphique en donut** (répartition par catégorie) | Vision produit |
| Ajouter une **carte « Panier moyen »** | Indicateur commercial clé |
| Ajouter un **top 5 clients** | Fidélisation |
| Rendre les KPI **cliquables** vers les listes filtrées | Navigation rapide |
| Ajouter un **badge de tendance** (▲/▼ vs période précédente) | Lecture immédiate |
| **Actualisation auto** toutes les 60 s | Suivi temps réel |

### Fonctionnalités optimales
- Export PDF du dashboard.
- Filtre par vendeur.
- Alerte visuelle si rupture > seuil critique.

---

## 4. POS — Caisse enregistreuse

**Fichier actuel** : [`templates/admin/pos.html`](templates/admin/pos.html:1)
**URL** : `/admin/caisse/`

**Objectif** : encaisser une vente rapidement, en quelques clics.

### Design actuel (à conserver)
- **Grille de produits** (cartes cliquables avec icône bouteille, nom, prix).
- **Panneau panier** à droite : sélection client, liste des articles, total, mode de paiement, bouton « Encaisser ».
- Survol des cartes produit → bordure rouge.

### Améliorations recommandées
| Amélioration | Bénéfice |
|---|---|
| **Barre de recherche** de produit | Trouver vite dans un grand catalogue |
| **Filtres par catégorie** (onglets) | Navigation rapide |
| **Affichage du stock restant** sur chaque carte | Éviter la vente en rupture |
| **Boutons +/− et suppression** dans le panier | Ajustement facile |
| **Affichage des promotions** (prix barré + prix remisé) | Transparence |
| **Création rapide de client** (modale) | Vente à un nouveau client |
| **Raccourcis clavier** (F2 = encaisser, Échap = vider) | Rapidité caissier |
| **Calcul du rendu de monnaie** (espèces) | Pratique comptoir |
| **Impression ticket** directe | Workflow complet |
| **Sauvegarde du panier** (localStorage) | Anti-perte de données |

### Fonctionnalités optimales
- Scanner code-barres (si équipement).
- Mise en attente / reprise de panier.
- Affichage du vendeur connecté.
- Confirmation avant validation.

---

## 5. Facture

**Fichier actuel** : [`templates/admin/facture.html`](templates/admin/facture.html:1)
**URL** : `/admin/ventes/vente/{id}/facture/`

**Objectif** : document imprimable professionnel.

### Design actuel (à conserver)
- En-tête « 🍷 La Cave » + numéro de facture + date + vendeur.
- Bloc coordonnées entreprise / client.
- Tableau des articles (prix U., qté, sous-total, remise affichée).
- Total en rouge, message de remerciement.
- Boutons Imprimer / Retour (masqués à l'impression).

### Améliorations recommandées
| Amélioration | Bénéfice |
|---|---|
| **Logo image** au lieu de l'emoji | Professionnalisme |
| **QR code** de vérification | Anti-fraude |
| **Mentions légales** (SIRET, TVA) | Conformité |
| **Détail TVA** (HT / TVA / TTC) | Comptabilité |
| **Pied de page** avec conditions | Cadre légal |
| **Export PDF** natif | Archivage |
| **Duplicata** en cas de perte | Service client |
| **Filigrane « ANNULÉE »** si vente annulée | Clarté |

### Fonctionnalités optimales
- Envoi par email au client.
- Numérotation séquentielle légale.
- Format A4 optimisé.

---

## 6. Pages CRUD (liste + formulaire)

Ces pages sont générées par l'admin Django/Jazzmin. Voici le design optimal par entité.

### 6.1 Produits

**Liste** ([`ProduitAdmin`](apps/produits/admin.py:13))
- Colonnes : aperçu image, nom, famille, marque, tarif détaillant, tarif consommateur,
  état (icône), statut, catégorie.
- Édition : tarifs visibles côte à côte pour limiter les erreurs de facturation ; le tarif
  appliqué reste déterminé côté serveur à partir du segment du client.
- Filtres : statut, type, catégorie, appellation.
- Recherche : nom, marque, type.
- Actions : rendre disponible / indisponible.

**Améliorations** : colonne **marge** (prix_vente − prix_achat), colonne **stock restant**,
action « dupliquer », export CSV, filtre « stock faible ».

**Formulaire** : fieldsets organisés (Général, Caractéristiques, Tarification, Relations, Système) — déjà bien structuré.

### 6.2 Clients — **réalisé**

**Liste** ([`ClientAdmin`](apps/clients/admin.py))
- Bandeau KPI : nombre de clients, encours total, CA encaissé (90 j), panier moyen, clients à risque, CA 30 j.
- Colonnes : identité (avatar + nom/prénom), contact, niveau (`lb-badge`), fidélité (points + barre de
  progression vers l'étape suivante), activité (dernier achat + nombre de ventes), encours, crédit
  disponible (barre), et `Contact rapide` (appel / WhatsApp).
- Colonnes standard maintenues : `Modifier / Supprimer / Voir` via `config/admin_mixins.ColumnActionsMixin`.
- Filtres : recherche, `type_client`, `niveau`, `date_creation`, `solde_due` (`EncoursFilter`).
- Segments rapides : tous, VIP, fidèles, argent, nouveaux, à risque, inactifs 90 j, endettés.
- Actions de masse : export CSV, ouvrir le téléphone, WhatsApp, libérer un plafond de crédit.

**Fiche Client 360°** (`templates/admin/clients/client/change_form.html` + `_historique.html`)
- Bandeau identité : avatar, niveau, points de fidélité, statut d'encours.
- Coordonnées avec liens `tel:` / `mailto:` / WhatsApp.
- Chiffres : CA total, CA encaissé, reste dû, crédit disponible, nombre de ventes, panier moyen.
- Chronologie des 10 dernières ventes (référence, montant, statut, articles) et des règlements.
- Tuile « À savoir » : ancienneté, prochain niveau de fidélité, points restants.
- Bloc en lecture seule : le readonly field `historique` est rendu via
  `render_to_string` (aucune migration nécessaire).

### 6.3 Stocks

**Liste** ([`StockAdmin`](apps/stocks/admin.py:5))
- Colonnes : produit, quantité, seuil, état (badge coloré), date de MAJ.
- Édition en ligne : quantité, seuil.
- Filtre : date de MAJ.

**Améliorations** : filtre **« état du stock »** (rupture/faible/normal), action « réapprovisionner » (modale quantité), colonne **valeur du stock** (quantité × prix_achat), alerte visuelle en rouge pour rupture, historique des mouvements.

### 6.4 Promotions

**Liste** ([`PromotionAdmin`](apps/promotions/admin.py:18))
- Colonnes : nom, type, valeur, dates, état (icône), statut.
- Édition en ligne : statut.
- Actions : activer / désactiver.
- Inline : produits associés.

**Améliorations** : colonne **« en cours »** (badge actif/à venir/expirée), action « prolonger de 7 jours », filtre par période, aperçu du prix remisé, compteur de produits liés.

### 6.5 Ventes

**Liste** ([`VenteAdmin`](apps/ventes/admin.py:58))
- Colonnes : référence, client, volume, total (badge), paiement (icône), statut (badge), date, bouton facture.
- Filtres : statut, mode de paiement, date (hiérarchie).
- Actions : annuler en masse, export CSV.
- Inline : lignes de vente (lecture seule).

**Améliorations** : colonne **vendeur**, filtre par vendeur, action « exporter PDF groupé », graphique de répartition, lien direct vers le client, indicateur de remise totale appliquée.

### 6.6 Catégories

**Liste** : nom, description, statut, date.
**Améliorations** : colonne **nombre de produits liés**, action « activer/désactiver », recherche.

### 6.7 Utilisateurs

**Liste** ([`CustomUserAdmin`](apps/accounts/admin.py:5))
- Colonnes : username, email, nom, rôle, actif.
- Filtres : rôle, actif, staff, superuser.

**Améliorations** : colonne **nombre de ventes réalisées**, action « activer/désactiver », réinitialisation de mot de passe en masse, filtre par date d'inscription.

---

## 7. Récapitulatif des fonctionnalités optimales

| Page | Fonctionnalités clés à ajouter |
|---|---|
| **Connexion** | Afficher/masquer mot de passe, redirection par rôle |
| **Dashboard** | Sélecteur de période, donut catégories, panier moyen, top clients, tendances |
| **POS** | Recherche, filtres catégorie, stock affiché, rendu de monnaie, raccourcis clavier, création client rapide |
| **Facture** | Logo, QR code, TVA, export PDF, filigrane annulée |
| **Produits** | Marge, stock restant, duplication, export |
| **Clients** | Historique achats, CA généré, export contacts |
| **Stocks** | Filtre état, réapprovisionnement, valeur stock, historique |
| **Promotions** | Badge « en cours », prolongation, aperçu prix remisé |
| **Ventes** | Filtre vendeur, export PDF, remise totale |
| **Catégories** | Compteur produits liés |
| **Utilisateurs** | Nombre de ventes, actions en masse |

---

## 8. Cohérence UX recommandée

1. **Navigation** : menu supérieur (Dashboard, POS, Nouveau Client, Catalogue, Ventes, API Docs) — déjà en place.
2. **Feedback** : messages de succès/erreur systématiques après chaque action.
3. **Confirmations** : demander confirmation avant toute action destructive (annulation, suppression).
4. **Responsive** : toutes les pages doivent fonctionner sur tablette (POS notamment).
5. **Performance** : `select_related`/`prefetch_related` sur toutes les listes (déjà partiellement fait).
6. **Accessibilité** : contrastes suffisants, libellés explicites, navigation clavier.

---

## 9. Résumé

Le backend dispose d'une base solide : dashboard riche, POS fonctionnel, facture imprimable et
admin Jazzmin soigné.

**Réalisé**
- Charte unique à 3 couleurs (grenat / or / sage) centralisée dans
  `static/css/wineadmin-design.css`, appliquée à toutes les listes CRUD, à la page Clients et à
  la fiche Client 360°.
- Page Clients : KPI, segments, filtres, recherche, actions de masse et raccourcis téléphone/WhatsApp.
- Garde-fous automatisés dans `tests/test_design_system.py` (palette, composants, features Client).

**À venir**
- Refonte dashboard, POS et facture sur la même palette.
- Enrichir le tableau de bord, accélérer la saisie POS et reprendre les documents imprimés.
