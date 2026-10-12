# Conception et réalisation d'une application de gestion de vente et promotion du vin (Backend)

Ce projet est le backend d'une application professionnelle de gestion de vente de vins, développée dans le cadre d'un mémoire de fin d'études (Licence 3 Informatique). 
Il expose une API RESTful sécurisée destinée à être consommée par un frontend (ex: Angular).

## Fonctionnalités

- **Authentification & Autorisations :** Système de connexion via JWT avec gestion de rôles (Administrateur / Gestionnaire / Vendeur).
- **Vérification par Code :** Système complet d'inscription et connexion par code à 6 chiffres envoyé par email (Brevo) ou SMS (Textbee).
- **Gestion des Produits et Stocks :** Catalogue des vins avec gestion rigoureuse des stocks (alertes, ruptures, décrémentation automatique).
- **Distribution professionnelle :** Tarifs détaillant et consommateur distincts, avec prix professionnel appliqué automatiquement aux revendeurs, restaurants et hôtels.
- **Gestion des Ventes :** Processus transactionnel pour les ventes (création, annulation avec restauration du stock).
- **Promotions :** Application automatique de réductions (pourcentage ou montant fixe) selon des dates de validité.
- **Tableau de Bord :** Indicateurs de performance (Chiffre d'affaires, meilleures ventes, stocks faibles).
- **Gestionnaire :** rôle de gestion avec accès au back-office et aux opérations métier, au même niveau que l'Administrateur.
- **Fournisseurs & approvisionnements :** registre des fournisseurs (coopérative, viticulteur, producteur, grossiste), bons de commande, réceptions partielles et mise à stock.
- **Rapports & statistiques :** ventes par jour, semaine, mois, année, vin, catégorie ou vendeur ; efficacité des promotions ; stock restant et valorisation au coût effectif ; exports CSV, Excel et PDF ; impression depuis la page dédiée `/admin/rapports/`.
- **Interface Admin :** Espace d'administration Django complet pour la gestion métier manuelle.

## Technologies

- **Python 3**
- **Django 6.x** / **Django REST Framework**
- **PostgreSQL** (Base de données relationnelle principale)
- **SimpleJWT** (Authentification sécurisée par token)
- **Django-Filter** (Recherche, filtres, tri)
- **drf-spectacular** (Génération de la documentation Swagger/OpenAPI)
- **openpyxl / reportlab** (exports Excel et PDF)
- **Pytest** (Tests unitaires automatisés)

## Architecture

```text
wine-management-backend/
├── config/              # Configuration globale (settings, urls, renderers d'export)
├── apps/                # Applications Django modulaires
│   ├── accounts/        # Utilisateurs, rôles et authentification
│   ├── categories/      # Catégories de vin
│   ├── clients/         # Base de données clients + fidélité
│   ├── dashboard/       # Logique du tableau de bord (statistiques)
│   ├── parametres/      # Paramètres, accueil API, sauvegardes
│   ├── produits/        # Catalogue des vins
│   ├── promotions/      # Système de promotions appliquées aux produits
│   ├── stocks/          # Suivi quantitatif, valorisation et alertes de stock
│   └── ventes/          # Ventes, caisse, commandes clients et réservations
├── media/               # Fichiers uploadés (Images des produits)
├── plans/               # Spécifications fonctionnelles et charte graphique
├── static/
│   ├── css/
│   │   └── wineadmin-design.css  # Charte et composants partagés de l'admin
│   ├── js/               # Scripts de l'interface (POS, filtres, KPI)
│   ├── img/              # Images statiques (logo)
│   └── vendor/           # Bibliothèques tierces (Jazzmin, plugins)
└── tests/               # Tests unitaires
```

## Charte graphique de l'interface

L'apparence de l'admin repose sur une feuille de style unique,
`static/css/wineadmin-design.css`, chargée par `templates/admin/base.html`. Elle définit les
jetons de couleur, les composants (`.lb-hero`, `.lb-kpis`, `.lb-panel`, `.lb-badge`, `.lb-bar`,
`.lb-segment`, `.lb-grid`) et la variante sombre.

La palette est limitée à **trois couleurs** — grenat `#641b2c`, or `#c99b3b`, sage `#2f6b4f` —
plus une échelle neutre. N'ajoutez pas de couleur en dur dans un gabarit ou un `ModelAdmin` :
utilisez les classes sémantiques. Le test `tests/test_design_system.py` vérifie ce point.
Le champ `prix_revendeur` (libellé « Prix détaillant par bouteille ») est un tarif unitaire ; les lignes vendues en pack ou en carton
multiplient ce prix par la contenance. Un tarif à zéro conserve le tarif public existant.
Les factures enregistrent également le taux de TVA, le mode de prix HT/TTC et
la date d’échéance applicables au moment de la vente. Les valeurs de démonstration
sont 20 % et 60 jours, inspirées de pièces historiques : confirmez leur
applicabilité actuelle avant tout usage comptable réel. Le mode TTC est retenu
par défaut ; le mode HT ajoute la TVA au prix payé.

Le détail des règles d'emploi se trouve dans `plans/DESIGN_PAGES.md`.

## Installation

### 1. Cloner le projet et créer un environnement virtuel
```bash
git clone <votre-depot>
cd wine-management-backend
python -m venv venv
source venv/bin/activate  # (Sous Windows : venv\Scripts\activate)
```

### 2. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 3. Configuration de la base de données PostgreSQL
Assurez-vous que PostgreSQL est installé et créez la base de données :
```sql
CREATE DATABASE wine_db;
CREATE USER postgres WITH PASSWORD 'postgres';
GRANT ALL PRIVILEGES ON DATABASE wine_db TO postgres;
```

### 4. Configuration des variables d'environnement (`.env`)
Créez un fichier `.env` à la racine du projet (un fichier `.env.example` est fourni) :
```ini
DB_NAME=wine_db
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=127.0.0.1
DB_PORT=5432
SECRET_KEY=votre_cle_secrete_django
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

En développement, si aucun serveur SMTP n'est configuré, Django écrit les
e-mails dans la console. Pour la production, configurez un serveur SMTP afin
que les codes OTP, liens de connexion et alertes puissent réellement être
envoyés :

```ini
EMAIL_HOST=
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=no-reply@votre-domaine.mg
```

Renseignez les identifiants fournis par votre service e-mail sans les ajouter
au dépôt. Le contrôle `python manage.py check --deploy` signale le backend
console tant qu'aucun backend de production n'est configuré.

### 5. Migrations
Générez et appliquez les schémas dans la base de données :
```bash
python manage.py makemigrations
python manage.py migrate
```

### 6. Création du superutilisateur
```bash
python manage.py createsuperuser
# Suivez les instructions (username, email, password)
```

### 7. Données de démonstration (optionnel)
```bash
python seed.py
```
Crée 3 exemples par table : 3 cuvées de Fianarantsoa, 3 fournisseurs, un bon de
commande réceptionné, 3 ventes et des clôtures de caisse. Le script refuse
désormais d'effacer des données métier existantes. Pour réinitialiser
explicitement une base de démonstration uniquement :
```bash
python seed.py --reset-demo-data
```
Ne lancez jamais cette option sur une base d'exploitation : elle supprime les
données métier avant de recréer les exemples.

### 8. Lancement du serveur
```bash
python manage.py runserver
```

### 9. Configuration de Redis et Celery (pour l'envoi asynchrone de codes)

Pour le système de vérification par code, vous devez installer et configurer Redis :

```bash
# Installer Redis (Ubuntu/Debian)
sudo apt-get install redis-server

# Démarrer Redis
redis-server
```

Lancer le worker Celery dans un terminal séparé :

```bash
source venv/bin/activate
celery -A config worker -l info
```

### 10. Configuration des API Resend et eSMS Africa

Le système utilise **Resend** pour les emails et **eSMS Africa** (`sms.esmsafrica.io`) pour les SMS.
Configurez les clés dans `.env` (ne commitez jamais vos vraies clés) :

```ini
# Resend API (Email, clé send-only)
RESEND_API_KEY=re_change-me
# Domaine à vérifier sur https://resend.com/domains (sinon repli automatique
# sur RESEND_SANDBOX_SENDER — bac à sable limité à l'adresse du compte Resend).
RESEND_SENDER_EMAIL=noreply@lazanibetsileo.mg
RESEND_SANDBOX_SENDER=onboarding@resend.dev

# eSMS Africa API (SMS)
ESMS_API_KEY=esms_live_change-me
# Sender ID approuvé via /sender-ids (par défaut route Madagascar = eSMS).
ESMS_SENDER_ID=eSMS

# Envoi réel des codes OTP même en DEBUG (désactivé automatiquement en tests).
OTP_ENVOI_REEL=True
```

**Déploiements à faire une fois (côté fournisseurs) :**

1. **Email** : vérifier le domaine `lazanibetsileo.mg` sur https://resend.com/domains
   (enregistrements DNS) pour pouvoir envoyer à n'importe quel destinataire depuis
   `noreply@lazanibetsileo.mg`. Sans cela, seul le bac à sable `onboarding@resend.dev`
   fonctionne (uniquement vers l'adresse du compte Resend + `delivered@resend.dev`).
2. **SMS** : recharger le solde du compte eSMS Africa (Billing → Top Up ; ~0.07 USD/SMS
   vers Madagascar, route `ESMS_MG`) et, si besoin, faire approuver un sender ID
   personnalisé (ex. `Lazan`) sur https://auth.esmsafrica.io/sender-ids.

Sans `OTP_ENVOI_REEL=True` (et hors tests), `DEBUG=True` affiche les codes dans la
console au lieu de les envoyer réellement.

## Documentation de l'API (Swagger)

Une fois le serveur lancé, accédez à la documentation générée automatiquement :
- **Swagger UI** : `http://127.0.0.1:8000/api/docs/`
- **ReDoc** : `http://127.0.0.1:8000/api/redoc/`
- **Schéma brut (YAML/JSON)** : `http://127.0.0.1:8000/api/schema/`

### Rapports de ventes

Les rapports nécessitent un utilisateur authentifié. La période est limitée à
366 jours et les ventes annulées sont exclues.

```http
GET /api/rapports/ventes/?debut=2026-01-01&fin=2026-01-31&par=jour
```

Le paramètre `par` accepte `jour`, `semaine`, `mois`, `annee`, `vin`,
`categorie` et `vendeur`. Pour télécharger le rapport, ajoutez `format=csv`,
`format=xlsx` ou `format=pdf`. Les exports comprennent une synthèse, les
ventes regroupées, le rendement des promotions et la valorisation du stock.
La page `/admin/rapports/` fournit les filtres de période et de regroupement,
les indicateurs de ventes, de promotions et de stock, les exports et
l'impression navigateur. Les rapports sont réservés aux comptes de gestion.

## Lancement des tests

Les tests ont été rédigés à l'aide de Pytest et de la classe APITestCase de Django.
```bash
pytest
```
*Si pytest n'est pas détecté, vous pouvez aussi lancer :*
```bash
python manage.py test tests/ --settings=config.settings_test
```

## Exemples d'API

### Authentification par Code (Système Lazan'i Betsileo)

**Inscription - Envoi du code :**
```http
POST /api/auth/signup/send-code/
{
  "nom": "Jean Dupont",
  "email": "jean.dupont@example.com",
  "telephone": "+261340000000",
  "password": "MotDePasse123",
  "contact_type": "email"
}
```
*Réponse :* `{"message": "Code envoyé", "expires_in": 600}`

**Inscription - Vérification du code :**
```http
POST /api/auth/signup/verify/
{
  "contact": "jean.dupont@example.com",
  "code": "123456"
}
```
*Réponse :* `{"message": "Inscription réussie", "access": "eyJ...", "refresh": "eyJ..."}`

**Connexion - Envoi du code :**
```http
POST /api/auth/login/send-code/
{
  "contact": "jean.dupont@example.com",
  "contact_type": "email"
}
```

**Connexion - Vérification du code :**
```http
POST /api/auth/login/verify/
{
  "contact": "jean.dupont@example.com",
  "code": "123456"
}
```

Pour plus de détails sur le système de vérification par code, consultez le fichier `../README_AUTH.md`.

### Authentification Classique

**Obtenir un token d'accès :**
```http
POST /api/auth/login/
{
  "username": "admin",
  "password": "password123"
}
```
*Réponse :* `{"access": "eyJ...", "refresh": "eyJ..."}`

**Créer une Vente :** (nécessite le header `Authorization: Bearer <votre_token>`)
```http
POST /api/ventes/
{
  "client": 1,
  "mode_paiement": "ESPECES",
  "lignes": [
    {
      "produit_id": 1,
      "quantite": 3
    }
  ]
}
```
*En interne : Vérifie les stocks, applique les promotions éventuelles, déduit la quantité, et sauvegarde par transaction de manière atomique.*
