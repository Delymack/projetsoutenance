# Lazan'i Betsileo - Application de Gestion de Vente et Promotion du Vin

Application web complète pour la gestion de vente et promotion des vins produits à Isaha, Fianarantsoa, Madagascar.

## 📋 Table des matières

- [Vue d'ensemble](#vue-densemble)
- [Architecture du projet](#architecture-du-projet)
- [Prérequis](#prérequis)
- [Installation rapide](#installation-rapide)
- [Système d'authentification](#système-dauthentification)
- [Lancement de l'application](#lancement-de-lapplication)
- [Structure du projet](#structure-du-projet)
- [Technologies utilisées](#technologies-utilisées)
- [Documentation détaillée](#documentation-détaillée)

## 🎯 Vue d'ensemble

Lazan'i Betsileo est une application professionnelle qui permet :

- ✅ Gestion complète du catalogue de vins
- ✅ Suivi rigoureux des stocks avec alertes
- ✅ Gestion des ventes avec caisse intégrée
- ✅ Système de promotions automatiques
- ✅ Tableau de bord avec indicateurs de performance
- ✅ Gestion des fournisseurs et approvisionnements
- ✅ Rapports et statistiques avancés
- ✅ **Système d'authentification par code à 6 chiffres (Email/SMS)**

## 🏗️ Architecture du projet

```
projet_soutenance/
├── backend/                      # Backend Django REST Framework
│   ├── apps/                    # Applications Django
│   │   ├── accounts/           # Authentification & utilisateurs
│   │   ├── categories/         # Catégories de vin
│   │   ├── clients/            # Base clients + fidélité
│   │   ├── dashboard/          # Tableau de bord
│   │   ├── parametres/         # Paramètres, accueil API, sauvegardes
│   │   ├── produits/           # Catalogue vins
│   │   ├── promotions/         # Promotions
│   │   ├── stocks/             # Gestion stocks
│   │   └── ventes/             # Ventes, caisse & commandes clients
│   ├── config/                 # Configuration Django
│   ├── static/                 # Fichiers statiques
│   ├── media/                  # Fichiers uploadés
│   └── README.md               # Documentation backend
│
├── frontend/                   # Frontend Angular
│   ├── src/
│   │   ├── app/
│   │   │   ├── core/       # Services, guards, intercepteurs
│   │   │   ├── features/   # Composants métier
│   │   │   │   └── auth/  # Authentification (login, inscription)
│   │   │   └── layout/     # Layout partagé
│   │   └── ...
│   └── README.md           # Documentation frontend
│
├── docs/                       # Documentation & MCD
└── README_AUTH.md              # Documentation système d'authentification
```

## 📦 Prérequis

- Python 3.10+
- Node.js 18+
- PostgreSQL 14+ (optionnel, SQLite en dev)
- Redis 7+ (pour le système d'authentification par code)

## 🚀 Installation rapide

### 1. Backend Django

```bash
cd backend

# Créer l'environnement virtuel
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Installer les dépendances
pip install -r requirements.txt

# Configurer l'environnement
cp .env.example .env
# Éditer .env avec vos configuration

# Exécuter les migrations
python manage.py makemigrations
python manage.py migrate

# Créer un superutilisateur
python manage.py createsuperuser

# Charger les données de démonstration (optionnel)
python seed.py
```

### 2. Frontend Angular

```bash
cd ../frontend

# Installer les dépendances
npm install

# Configurer l'URL de l'API
# Éditer src/environments/environment.ts
```

## 🔐 Système d'authentification

L'application dispose d'un **système complet de vérification par code à 6 chiffres** pour l'inscription et la connexion.

### Caractéristiques

- Code à 6 chiffres aléatoire
- Expiration après 10 minutes
- Maximum 5 tentatives avant blocage
- Délai de renvoi de 60 secondes
- Choix du mode de réception : **Email** (via Brevo) ou **SMS** (via Textbee)
- Tâches asynchrones via Celery + Redis
- Fallback console en mode DEBUG

### Documentation complète

Pour une documentation détaillée du système d'authentification, consultez :

📄 **[README_AUTH.md](./README_AUTH.md)**

Ce document contient :
- Architecture détaillée backend et frontend
- Configuration des API Brevo et Textbee
- Instructions de lancement de Redis et Celery
- Exemples de requêtes API (curl)
- Guide de dépannage
- Mesures de sécurité

## 🎮 Lancement de l'application

### 1. Démarrer Redis (pour l'authentification par code)

```bash
redis-server
```

### 2. Démarrer Celery Worker (Backend)

Dans un terminal (dossier backend) :
```bash
cd backend
source venv/bin/activate
celery -A config worker -l info
```

### 3. Démarrer Django Backend

Dans un terminal (dossier backend) :
```bash
cd backend
source venv/bin/activate
python manage.py runserver
```

Backend accessible sur : `http://localhost:8000`

### 4. Démarrer Angular Frontend

Dans un terminal (dossier frontend) :
```bash
cd frontend
ng serve
```

Frontend accessible sur : `http://localhost:4200`

## 📁 Structure du projet

### Backend Django

L'architecture backend suit les meilleures pratiques Django avec des applications modulaires :

- **accounts** : Gestion des utilisateurs et authentification
- **categories** : Catégories de vins (Rouge, Blanc, Rosé, etc.)
- **clients** : Base de données clients avec historique
- **commandes** : Bons de commande fournisseurs
- **dashboard** : Statistiques et KPIs
- **fournisseurs** : Registre des fournisseurs
- **produits** : Catalogue des vins avec photos
- **promotions** : Système de réductions automatiques
- **stocks** : Suivi quantitatif et valorisation
- **ventes** : Processus transactionnel des ventes

### Frontend Angular

L'architecture frontend utilise Angular 16+ avec :

- **Composants standalone** pour une meilleure performance
- **Reactive Forms** pour la gestion des formulaires
- **RxJS** pour la programmation réactive
- **Guards** pour la protection des routes
- **Intercepteurs** pour l'injection des tokens JWT
- **Lazy loading** pour le chargement à la demande

## 🛠️ Technologies utilisées

### Backend

- **Django 6.x** : Framework web Python
- **Django REST Framework** : API REST
- **PostgreSQL** : Base de données
- **SimpleJWT** : Authentification JWT
- **Celery** : Tâches asynchrones
- **Redis** : Broker de messages
- **Brevo API** : Envoi d'emails
- **Textbee API** : Envoi de SMS

### Frontend

- **Angular 16+** : Framework frontend
- **TypeScript** : Typage statique
- **Angular Material** : Composants UI
- **RxJS** : Programmation réactive
- **HttpClient** : Appels API

## 📚 Documentation détaillée

### Backend

- 📄 [backend/README.md](./backend/README.md) - Documentation complète du backend
- 🌐 Swagger UI : `http://localhost:8000/api/docs/`
- 📖 ReDoc : `http://localhost:8000/api/redoc/`

### Frontend

- 📄 [frontend/README.md](./frontend/README.md) - Documentation frontend

### Authentification

- 📄 [README_AUTH.md](./README_AUTH.md) - Documentation système de vérification par code

## 🎨 Charte graphique

L'application utilise les couleurs de Lazan'i Betsileo :

- **Vert foncé** : `#1B5E20` (Couleur principale)
- **Or** : `#FFC107` (Accent)
- **Blanc** : `#ffffff` (Fond)

## 📞 Support

Pour toute question ou problème technique :

1. Consultez la documentation appropriée (Backend, Frontend, Auth)
2. Vérifiez les logs dans les terminaux
3. Consultez le guide de dépannage dans README_AUTH.md

---

**Lazan'i Betsileo** - Vins des hautes terres de Madagascar  
Isaha, Fianarantsoa, Madagascar
