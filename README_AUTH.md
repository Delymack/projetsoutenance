# Système de Vérification par Code - Lazan'i Betsileo

Documentation complète du système d'authentification par code à 6 chiffres pour l'application Lazan'i Betsileo.

## 📋 Table des matières

- [Vue d'ensemble](#vue-densemble)
- [Architecture Backend Django](#architecture-backend-django)
- [Architecture Frontend Angular](#architecture-frontend-angular)
- [Installation et Configuration](#installation-et-configuration)
- [Lancement des Services](#lancement-des-services)
- [Test des Endpoints API](#test-des-endpoints-api)
- [Sécurité](#sécurité)
- [Dépannage](#dépannage)

## 🎯 Vue d'ensemble

Ce système permet aux utilisateurs de s'inscrire et de se connecter via un code de vérification à 6 chiffres envoyé par **email** (via Brevo) ou **SMS** (via Textbee).

### Caractéristiques

- ✅ Code à 6 chiffres aléatoire
- ✅ Expiration après 10 minutes
- ✅ Maximum 5 tentatives avant blocage
- ✅ Délai de renvoi de 60 secondes
- ✅ Choix du mode de réception (Email ou SMS)
- ✅ Hash sécurisé du code (make_password)
- ✅ Stockage des données temporaires (JSONField)
- ✅ Tâches asynchrones via Celery + Redis
- ✅ Fallback console en mode DEBUG

## 🏗️ Architecture Backend Django

### Structure de l'app `accounts`

```
backend/apps/accounts/
├── models.py              # Modèles User et VerificationCode
├── serializers.py        # Validateurs DRF
├── views.py              # Vues API REST
├── urls.py               # Routes /api/auth/
├── tasks.py              # Tâches Celery
├── utils.py              # Utilitaires (generate_code)
└── services/
    ├── email_service.py  # Envoi via Resend API
    └── sms_service.py    # Envoi via eSMS Afrique API
```

### Modèle VerificationCode

```python
class VerificationCode(models.Model):
    id = models.UUIDField(primary_key=True)
    contact = models.CharField(max_length=150)  # email ou téléphone
    contact_type = models.CharField(max_length=5)  # 'email' ou 'sms'
    code_hash = models.CharField(max_length=255)  # hashé avec make_password
    purpose = models.CharField(max_length=10)  # 'signup' ou 'login'
    expires_at = models.DateTimeField()  # created_at + 10 minutes
    attempts = models.PositiveIntegerField(default=0)  # max 5
    is_used = models.BooleanField(default=False)
    last_sent_at = models.DateTimeField()  # pour délai 60s
    user_data = models.JSONField()  # données temporaires d'inscription
```

### Endpoints API

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/api/auth/signup/send-code/` | Envoie code pour inscription |
| POST | `/api/auth/signup/verify/` | Vérifie code et crée compte |
| POST | `/api/auth/login/send-code/` | Envoie code pour connexion |
| POST | `/api/auth/login/verify/` | Vérifie code et connecte |
| POST | `/api/auth/resend-code/` | Renvoie un nouveau code |

## 🎨 Architecture Frontend Angular

### Structure des composants d'auth

```
frontend/src/app/
├── core/
│   ├── services/
│   │   └── auth.service.ts         # Service d'authentification
│   ├── interceptors/
│   │   └── auth.interceptor.ts     # Intercepteur JWT
│   └── guards/
│       └── auth.guard.ts           # Guard de protection
└── features/
    └── auth/
        ├── inscription.component.ts
        ├── inscription.component.html
        ├── inscription.component.scss
        ├── login.component.ts
        ├── login.component.html
        └── login.component.scss
```

### Flux utilisateur

#### Inscription (3 étapes)

1. **Étape 1** : Formulaire (nom, email/téléphone, password) + choix Email/SMS
2. **Étape 2** : Saisie du code à 6 chiffres avec timer 10:00
3. **Étape 3** : Redirection vers dashboard après succès

#### Connexion (2 étapes)

1. **Étape 1** : Saisie email/téléphone + choix Email/SMS
2. **Étape 2** : Saisie du code avec timer 10:00
3. **Étape 3** : Redirection vers dashboard après succès

## 🚀 Installation et Configuration

### Prérequis

- Python 3.10+
- Node.js 18+
- PostgreSQL 14+ (optionnel, SQLite en dev)
- Redis 7+

### Backend Django

1. **Cloner le projet**
```bash
cd backend
```

2. **Créer l'environnement virtuel**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows
```

3. **Installer les dépendances**
```bash
pip install -r requirements.txt
```

4. **Configurer les variables d'environnement**
```bash
cp .env.example .env
```

Éditer `.env` avec vos clés API :
```env
SECRET_KEY=votre-clé-secrète-django
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Base de données (optionnel, SQLite par défaut)
DB_NAME=lazanibetsileo
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432

# Resend API (Email)
RESEND_API_KEY=votre_clé_resend
RESEND_SENDER_EMAIL=noreply@lazanibetsileo.mg

# eSMS Afrique API (SMS)
ESMS_API_KEY=votre_clé_esms
ESMS_SENDER_ID=Lazan

# Redis pour Celery
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

5. **Exécuter les migrations**
```bash
python manage.py makemigrations
python manage.py migrate
```

6. **Créer un superutilisateur**
```bash
python manage.py createsuperuser
```

### Frontend Angular

1. **Naviguer vers le frontend**
```bash
cd ../frontend
```

2. **Installer les dépendances**
```bash
npm install
```

3. **Configurer l'URL de l'API**

Éditer `src/environments/environment.ts` :
```typescript
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8000/api'
};
```

## 🔄 Lancement des Services

### 1. Démarrer Redis

```bash
redis-server
```

### 2. Démarrer Celery (Worker)

Dans un nouveau terminal (dossier backend) :
```bash
source venv/bin/activate
celery -A config worker -l info
```

### 3. Démarrer Django

Dans un nouveau terminal (dossier backend) :
```bash
source venv/bin/activate
python manage.py runserver
```

### 4. Démarrer Angular

Dans un nouveau terminal (dossier frontend) :
```bash
ng serve
```

L'application sera accessible sur `http://localhost:4200`

## 🧪 Test des Endpoints API

### 1. Inscription - Envoi du code

```bash
curl -X POST http://localhost:8000/api/auth/signup/send-code/ \
  -H "Content-Type: application/json" \
  -d '{
    "nom": "Jean Dupont",
    "email": "jean.dupont@example.com",
    "telephone": "+261340000000",
    "password": "MotDePasse123",
    "contact_type": "email"
  }'
```

**Réponse attendue :**
```json
{
  "message": "Code envoyé",
  "expires_in": 600
}
```

En mode DEBUG, le code s'affiche dans la console Django :
```
[EMAIL DEBUG] À jean.dupont@example.com | Code: 123456 | Objectif: signup
```

### 2. Inscription - Vérification du code

```bash
curl -X POST http://localhost:8000/api/auth/signup/verify/ \
  -H "Content-Type: application/json" \
  -d '{
    "contact": "jean.dupont@example.com",
    "code": "123456"
  }'
```

**Réponse attendue :**
```json
{
  "message": "Inscription réussie",
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

### 3. Connexion - Envoi du code

```bash
curl -X POST http://localhost:8000/api/auth/login/send-code/ \
  -H "Content-Type: application/json" \
  -d '{
    "contact": "jean.dupont@example.com",
    "contact_type": "email"
  }'
```

### 4. Connexion - Vérification du code

```bash
curl -X POST http://localhost:8000/api/auth/login/verify/ \
  -H "Content-Type: application/json" \
  -d '{
    "contact": "jean.dupont@example.com",
    "code": "123456"
  }'
```

### 5. Renvoyer le code

```bash
curl -X POST http://localhost:8000/api/auth/resend-code/ \
  -H "Content-Type: application/json" \
  -d '{
    "contact": "jean.dupont@example.com"
  }'
```

## 🔒 Sécurité

### Mesures de sécurité implémentées

1. **Hash du code** : Utilisation de `make_password` de Django
2. **Vérification sécurisée** : Utilisation de `check_password`
3. **Rate limiting** : Maximum 5 tentatives par code
4. **Expiration** : Code invalide après 10 minutes
5. **Délai de renvoi** : 60 secondes minimum entre deux envois
6. **Validation stricte** :
   - Email avec `EmailValidator`
   - Téléphone avec regex format international
7. **CORS configuré** : Autorise uniquement `localhost:4200` en dev
8. **JWT** : Tokens avec expiration (60 min access, 7 jours refresh)

### Bonnes pratiques

- ✅ JAMAIS de clés en dur dans le code
- ✅ Variables d'environnement pour toutes les clés API
- ✅ Fallback console en mode DEBUG uniquement
- ✅ Suppression des anciens codes non utilisés
- ✅ Marquage `is_used` après vérification réussie

## 🐛 Dépannage

### Problème : Celery ne se connecte pas à Redis

**Solution :**
```bash
# Vérifier que Redis tourne
redis-cli ping
# Doit répondre : PONG
```

### Problème : Email/SMS non envoyés en production

**Solution :**
- Vérifier les clés API dans `.env`
- Tester les API manuellement :
  - Resend : https://api.resend.com/emails
  - eSMS Afrique : https://api.esmsafrica.com/api/v1/sms/send

### Problème : Code expiré trop rapidement

**Solution :**
Vérifier le fuseau horaire du serveur Django (doit être `Indian/Antananarivo` dans `settings.py`).

### Problème : Frontend ne peut pas contacter l'API

**Solution :**
- Vérifier que Django tourne sur le port 8000
- Vérifier la configuration CORS dans `settings.py`
- Vérifier l'URL API dans `environment.ts`

### Problème : Migration échoue

**Solution :**
```bash
# Supprimer la base de données et recréer
rm db.sqlite3
python manage.py migrate
```

## 📝 Notes de développement

### Mode DEBUG vs Production

En mode DEBUG (`DEBUG=True` dans `.env`) :
- ✅ Emails affichés dans la console
- ✅ SMS affichés dans la console
- ✅ Pas d'envoi réel via les API

En production (`DEBUG=False`) :
- ✅ Emails envoyés via Brevo API
- ✅ SMS envoyés via Textbee API
- ✅ Logs des erreurs dans la console

### Personnalisation

Pour modifier le temps d'expiration :
```python
# Dans accounts/models.py
expires_at = timezone.now() + timedelta(minutes=10)  # Modifier ici
```

Pour modifier le nombre maximum de tentatives :
```python
# Dans accounts/models.py
attempts = models.PositiveIntegerField(default=0)  # Max 5 par défaut
```

Pour modifier le délai de renvoi :
```python
# Dans accounts/views.py
if not vc.can_resend():  # can_resend() vérifie 60 secondes
```

## 📞 Support

Pour toute question ou problème, consultez :
- Documentation Django REST Framework : https://www.django-rest-framework.org/
- Documentation Celery : https://docs.celeryq.dev/
- Documentation Angular : https://angular.io/docs

---

**Lazan'i Betsileo** - Vins des hautes terres de Madagascar
