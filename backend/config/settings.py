"""
Django settings for config project.

Backend de gestion de vente et promotion du vin.
Projet de memoire - Licence 3 Informatique.
"""

from pathlib import Path
import environ
import os
import sys

from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Initialize environ
env = environ.Env()

# Read .env file
env_file = BASE_DIR / '.env'
if env_file.exists():
    environ.Env.read_env(env_file)

# SECURITY WARNING: keep the secret key used in production secret!
_INITIAL_SECRET_KEY = 'django-insecure-default-key-do-not-use-in-prod'
SECRET_KEY = env('SECRET_KEY', default=_INITIAL_SECRET_KEY)

# SECURITY WARNING: don't run with debug turned on in production!
# DEBUG vient du .env (True par défaut en développement local ; poser
# DEBUG=False en production pour activer le durcissement HTTPS ci-dessous).
DEBUG = env.bool('DEBUG', default=True)

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['127.0.0.1', 'localhost'])

# En production, la SECRET_KEY de secours (utilisée en dev) est interdite :
# sans clé forte dans le .env, Django refuse de démarrer.
if not DEBUG and (not SECRET_KEY or SECRET_KEY == _INITIAL_SECRET_KEY):
    raise ImproperlyConfigured(
        "La variable SECRET_KEY est absente du fichier .env. "
        "En production, définissez une clé secrète forte (ex: python -c \"import secrets; "
        "print(secrets.token_urlsafe(50))\") avant de démarrer le serveur."
    )

# ---- Durcissement HTTPS (actif uniquement hors DEBUG) ----
# Recommandé derrière un reverse proxy TLS (nginx/caddy). Aucun effet en
# développement local où l'on sert le site en HTTP sur 127.0.0.1.
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    CSRF_COOKIE_HTTPONLY = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# Application definition

DJANGO_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Requis par allauth (connexion Google).
    'django.contrib.sites',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'django_filters',
    'drf_spectacular',
    'corsheaders',
    # Authentification sociale (Google) + gestion de compte.
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
]

LOCAL_APPS = [
    'apps.accounts',
    'apps.clients',
    'apps.categories',
    'apps.produits',
    'apps.stocks',
    'apps.ventes',
    'apps.promotions',
    'apps.dashboard',
    'apps.parametres',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'config.middleware.SessionExpiryMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.parametres.middleware.MaintenanceMiddleware',
    'config.middleware.TwoFactorMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# CORS Configuration pour autoriser Angular
# Par défaut, on n'autorise que les origines explicitement listées (sécurisé).
# Pour le développement, définir CORS_ALLOW_ALL_ORIGINS=True dans le .env.
CORS_ALLOW_ALL_ORIGINS = env.bool('CORS_ALLOW_ALL_ORIGINS', default=False)
CORS_ALLOWED_ORIGINS = env.list(
    'CORS_ALLOWED_ORIGINS',
    default=['http://localhost:4200', 'http://127.0.0.1:4200']
)

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'config.context_processors.societe',
                'config.context_processors.demo_login',
                'config.context_processors.auth_status',
                'config.context_processors.login_greeting',
                'config.context_processors.sidebar_badges',
                'config.context_processors.notifications',
                'config.context_processors.site_config',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

AUTH_USER_MODEL = 'accounts.User'
SITE_ID = 1

# Authentification : backend unique « identifiant OU e-mail » avec verrouillage
# temporaire après échecs répétés. La suppression des backends allauth / ModelBackend
# garantit qu'aucun d'entre eux ne court-circuite le verrouillage. Allauth reste
# fonctionnel pour « Continuer avec Google » (login social, indépendant des mots de passe).
AUTHENTICATION_BACKENDS = [
    'apps.accounts.backends.EmailOrUsernameBackend',
]

# ---- Connexion Google (OAuth2) ----
# OAuth2 identifiants Google (optionnel) : sans GOOGLE_OAUTH2_CLIENT_ID,
# le bouton « Continuer avec Google » est masqué et l'API /api/auth/google/
# répond 503. Les Google Apps doivent ensuite être créées dans l'admin Django.
GOOGLE_OAUTH2_CLIENT_ID = env('GOOGLE_OAUTH2_CLIENT_ID', default='')
GOOGLE_OAUTH2_CLIENT_SECRET = env('GOOGLE_OAUTH2_CLIENT_SECRET', default='')
GOOGLE_ALLOWED_EMAILS = env.list('GOOGLE_ALLOWED_EMAILS', default=[])
GOOGLE_ALLOWED_DOMAINS = env.list('GOOGLE_ALLOWED_DOMAINS', default=[])

ACCOUNT_LOGIN_METHODS = {'username'}
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_UNIQUE_EMAIL = True
SOCIALACCOUNT_AUTO_SIGNUP = True
# Le bouton « Continuer avec Google » envoie directement l'utilisateur chez
# Google (pas d'écran de confirmation intermédiaire d'allauth).
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_ADAPTER = 'apps.accounts.adapters.GoogleSocialAdapter'
LOGIN_REDIRECT_URL = '/admin/'
LOGIN_URL = '/accounts/login/'
LOGOUT_REDIRECT_URL = '/admin/login/'

# ---- Renforcement : inscription, OTP, lien magique, 2FA, verrouillage ----
# Pile d'authentification « au-delà de l'imagination » : chaque option peut
# être désactivée via le .env sans toucher au code.
# L'inscription est ouverte par défaut en développement (DEBUG) et fermée en
# production (sauf AUTH_SIGNUP_ENABLED=True explicite).
AUTH_SIGNUP_ENABLED = env.bool('AUTH_SIGNUP_ENABLED', default=DEBUG)
# Les comptes créés par inscription ont-ils accès au back-office Django
# (is_staff=True) ? SÉCURITÉ : désactivé par défaut — un vendeur auto-inscrit
# reste utilisable sur la caisse (POS) et l'API, mais ne reçoit PAS les
# privilèges admin complets. L'administrateur promeut explicitement les comptes.
SIGNUP_STAFF = env.bool('SIGNUP_STAFF', default=False)
# Idem pour les comptes créés via « Continuer avec Google ».
GOOGLE_STAFF = env.bool('GOOGLE_STAFF', default=False)
AUTH_2FA_ENABLED = env.bool('AUTH_2FA_ENABLED', default=True)
AUTH_OTP_TTL = env.int('AUTH_OTP_TTL', default=600)            # 10 min
AUTH_OTP_RESEND_SECONDS = env.int('AUTH_OTP_RESEND_SECONDS', default=90)
AUTH_MAGIC_LINK_TTL = env.int('AUTH_MAGIC_LINK_TTL', default=600)  # 10 min
AUTH_LOGIN_ALERT_EMAIL = env.bool('AUTH_LOGIN_ALERT_EMAIL', default=True)
LOGIN_MAX_ATTEMPTS = env.int('LOGIN_MAX_ATTEMPTS', default=5)
LOGIN_LOCKOUT_MINUTES = env.int('LOGIN_LOCKOUT_MINUTES', default=15)

# ---- Envoi réel des codes de vérification (e-mail Resend / SMS eSMS Africa) ----
# En DEBUG, les codes ne sont normalement qu'affichés dans la console. Poser
# OTP_ENVOI_REEL=True (dans .env) pour qu'ils soient VRAIMENT envoyés aussi en
# développement. Les tests unitaires restent toujours offline (console).
OTP_ENVOI_REEL = env.bool('OTP_ENVOI_REEL', default=False)
TESTING = 'test' in sys.argv

# ---- Envoi d'e-mails (OTP, lien magique, alertes) ----
# Django 6.1 remplace EMAIL_BACKEND / EMAIL_* par MAILERS (removal prévu en 7.0).
# Sans SMTP configuré, les e-mails sont écrits dans la console (développement).
if env('EMAIL_HOST', default=''):
    MAILERS = {
        'default': {
            'BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
            'OPTIONS': {
                'host': env('EMAIL_HOST'),
                'port': env.int('EMAIL_PORT', default=587),
                'username': env('EMAIL_HOST_USER', default=''),
                'password': env('EMAIL_HOST_PASSWORD', default=''),
                'use_tls': env.bool('EMAIL_USE_TLS', default=True),
            },
        },
    }
else:
    # Développement sans SMTP : par défaut on capture les e-mails dans des
    # fichiers ``.eml`` (backend filebased maison), plus pratique qu'un simple
    # défilement console pour les démos. Remplaçable par EMAIL_BACKEND.
    _backend_dev = env(
        'EMAIL_BACKEND', default='config.mail_backends.EmlFileBackend'
    )
    MAILERS = {'default': {'BACKEND': _backend_dev}}
    if _backend_dev.endswith(('filebased.EmailBackend', 'EmlFileBackend')):
        MAILERS['default']['OPTIONS'] = {
            'file_path': env('EMAIL_FILE_PATH', default=str(BASE_DIR / 'var' / 'mail')),
        }
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default="LAZAN'I BETSILEO <no-reply@lazani-betsileo.mg>")

if GOOGLE_OAUTH2_CLIENT_ID:
    SOCIALACCOUNT_PROVIDERS = {
        'google': {
            'APP': {
                'client_id': GOOGLE_OAUTH2_CLIENT_ID,
                'secret': GOOGLE_OAUTH2_CLIENT_SECRET,
                'key': '',
            },
            'SCOPE': ['profile', 'email'],
            'AUTH_PARAMS': {'access_type': 'online'},
        }
    }

# Database
# Configuration PostgreSQL via variables d'environnement, avec repli automatique
# sur SQLite si PostgreSQL n'est pas configuré OU n'est pas joignable.
# Cela évite de casser le projet lorsque la base PostgreSQL n'existe pas encore.
SQLITE_FALLBACK = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Contrôle du ping PostgreSQL effectué au chargement (permet de gagner du temps
# au démarrage / en CI / pendant les tests).
DB_CONNECT_TIMEOUT = env.float('DB_CONNECT_TIMEOUT', default=2)
DB_SKIP_FALLBACK_PING = env.bool('DB_SKIP_FALLBACK_PING', default=False)


def _postgres_reachable(config):
    """Teste la connectivité PostgreSQL (court-circuitable via DB_SKIP_FALLBACK_PING)."""
    if DB_SKIP_FALLBACK_PING:
        return True
    try:
        import psycopg2
        conn = psycopg2.connect(
            dbname=config['NAME'],
            user=config['USER'],
            password=config['PASSWORD'],
            host=config['HOST'],
            port=config['PORT'],
            connect_timeout=DB_CONNECT_TIMEOUT,
        )
        conn.close()
        return True
    except Exception:
        return False


if env('DB_NAME', default=None):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': env('DB_NAME'),
            'USER': env('DB_USER', default='postgres'),
            'PASSWORD': env('DB_PASSWORD', default=''),
            'HOST': env('DB_HOST', default='127.0.0.1'),
            'PORT': env('DB_PORT', default='5432'),
        }
    }
    if not _postgres_reachable(DATABASES['default']):
        DATABASES = SQLITE_FALLBACK
else:
    DATABASES = SQLITE_FALLBACK

# REST Framework Configuration
REST_FRAMEWORK = {
    # SessionAuthentication : permet aux pages de l'admin (caisse POS) d'appeler
    # l'API avec la session Django, sans JWT côté JS. JWT reste la voie normale
    # pour le frontend Angular.
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_RATES': {
        'reservation_site': '10/hour',
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # Exports tabulaires : `?format=csv` et `?format=xlsx` sur les rapports.
    # Le renderer admin par défaut reste le premier : sans `format`, la réponse
    # JSON est inchangée et rien ne change pour le frontend Angular.
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
        'config.renderers.CSVRenderer',
        'config.renderers.XLSXRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ),
}

from datetime import timedelta
SIMPLE_JWT = {
    # Session longue : le client reste connecté très longtemps sans se
    # reconnecter. Le front renouvelle l'access token via /auth/refresh/ dès
    # qu'il expire, la déconnexion n'a lieu qu'à la demande de l'utilisateur.
    'ACCESS_TOKEN_LIFETIME': timedelta(days=7),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=365),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Wine Management API',
    'DESCRIPTION': 'API RESTful pour la gestion de la vente et de la promotion du vin (Projet de mémoire L3).',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
}


# Identité de la société (affichée sur les factures et l'interface admin).
# Toute la production est faite à Isaha, Fianarantsoa (Madagascar) : le vin
# sort des parcelles du domaine.
SOCIETE = {
    'nom': env('SOCIETE_NOM', default="LAZAN'I BETSILEO"),
    'slogan': env('SOCIETE_SLOGAN', default="Vins des hautes terres de Madagascar"),
    'adresse': env('SOCIETE_ADRESSE', default='Rue Alphonse Rakotozafy, Isaha, Fianarantsoa 301 — BP 1496, Madagascar'),
    'telephone': env('SOCIETE_TELEPHONE', default='+261 20 75 901 27'),
    'email': env('SOCIETE_EMAIL', default='lazatana@yahoo.fr'),
    'siret': env('SOCIETE_SIRET', default='NIF 4001234567'),
    'devise': env('SOCIETE_DEVISE', default='Ar'),
    'fonds_caisse': env.float('SOCIETE_FONDS_CAISSE', default=0),
    # Fidélité : 1 point par tranche de points_regle d'achat (toutes ventes payées).
    'points_regle': env.int('SOCIETE_POINTS_REGLE', default=1000),
    # Couverture de stock cible avant de ré-embouteiller (en jours de ventes).
    'jours_couverture': env.int('SOCIETE_JOURS_COUVERTURE', default=30),
    # Objectif de CA mensuel affiché sur le tableau de bord (en devise locale).
    # 0 = objectif « auto » : 2 x CA du mois précédent.
    'objectif_mensuel': env.float('SOCIETE_OBJECTIF_MENSUEL', default=0),
    # Plafond de remise manuelle accordé d'office à un vendeur, en % du brut.
    # Un administrateur n'est pas plafonné. 0 = la remise manuelle est réservée
    # aux administrateurs.
    'remise_max_vendeur_pct': env.float('SOCIETE_REMISE_MAX_VENDEUR_PCT', default=5.0),
    # Oblige le caissier à ouvrir sa caisse (fonds déclaré) avant d'encaisser.
    'caisse_session_requise': env.bool('SOCIETE_CAISSE_SESSION_REQUISE', default=True),
    # Durée de validité d'une réservation sans acompte (jours).
    'reservation_validite_jours': env.int('SOCIETE_RESERVATION_VALIDITE_JOURS', default=7),
    # Plafond de crédit accordé d'office par l'action « Autoriser un plafond »
    # de la page Clients. Les clients disposant déjà d'un plafond ne sont pas
    # modifiés : ce n'est pas une augmentation de plafond.
    'credit_plafond_defaut': env('SOCIETE_CREDIT_PLAFOND_DEFAUT', default=100000),
}

# Aide à la connexion : identifiants de démonstration affichés sur la page de
# login, uniquement en DEBUG. À définir dans .env pour correspondre à un vrai
# compte local (ex. DEMO_LOGIN_USERNAME / DEMO_LOGIN_PASSWORD).
DEMO_LOGIN = None
if env.bool('DEMO_LOGIN_ENABLED', default=False):
    DEMO_LOGIN = {
        'username': env('DEMO_LOGIN_USERNAME', default='admin'),
        'password': env('DEMO_LOGIN_PASSWORD', default=''),
    }



# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'fr-fr'

TIME_ZONE = 'Indian/Antananarivo'

USE_I18N = True

USE_TZ = True


# Static & Media files
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = '/static/'
# Ensure the static directory exists before adding it to STATICFILES_DIRS
static_dir = BASE_DIR / 'static'
if not static_dir.exists():
    os.makedirs(static_dir, exist_ok=True)
STATICFILES_DIRS = [
    static_dir,
    # Icônes PNG du menu latéral (source : templates/admin/icone/)
    ('icone', BASE_DIR / 'templates' / 'admin' / 'icone'),
]
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Le « / » initial est obligatoire : sans lui, `produit.image.url` vaut
# `media/…` (relatif) et la boutique le colle après `/catalogue/…`, ce qui
# casse l'affichage des photos.
MEDIA_URL = '/media/'
media_dir = BASE_DIR / 'media'
if not media_dir.exists():
    os.makedirs(media_dir, exist_ok=True)
MEDIA_ROOT = media_dir

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# JAZZMIN CONFIGURATION (VERSION AMÉLIORÉE)
JAZZMIN_SETTINGS = {
    "site_title": "LAZAN'I BETSILEO",
    "site_header": "LAZAN'I BETSILEO",
    "site_brand": "\U0001F377 LAZAN'I BETSILEO",
    "welcome_sign": "Bienvenue",
    "copyright": "LAZAN'I BETSILEO — Isaha, Fianarantsoa",
    "user_avatar": "avatar_url",
    "search_model": [],
    "related_modal_active": True,
    "show_ui_builder": False,
    "custom_css": "css/wineadmin.css",
    "custom_js": ["js/wineadmin.js", "js/wineadmin-sidebar.js", "js/wineadmin-actions.js", "js/wineadmin-globalsearch.js"],
    # ============ SIDEBAR : seuls les inlines + internes sont masqués ============
    "hide_models": [
        # Internes Django
        "auth.Group",
        # Inlines (accessibles depuis le formulaire parent)
        "ventes.LigneVente",
        # Encaissements : indispensables au POS et au rapprochement de caisse, mais saisis
        # directement sur la fiche client (encours, timeline, formulaire
        # d'encaissement). Une section « Règlements clients » à part ne
        # ferait que dupliquer l'information et casser le fil de la lecture.
        "clients.ReglementClient",
        # Sessions de caisse : la journée se suit et se clôture depuis la
        # caisse. Une section à part ne ferait que dupliquer cette interface.
        "ventes.SessionCaisse",
        # Ventes : le journal ET la caisse sont un seul onglet (/admin/caisse/),
        # atteint depuis la sidebar. Laisser l'app « Ventes » vide sur la page
        # d'accueil de l'admin : la caisse y est déjà, une fois pour toutes.
        "ventes.Vente",
        # Commandes clients : même raison, elles se gèrent depuis l'onglet
        # « Commandes clients » de la page Caisse, qui renvoie vers cette liste.
        "ventes.Reservation",
        # Mouvements de stock : c'est l'historique d'un stock, pas une tâche.
        # Le bouton « Mouvements » de la page Stocks y mène directement.
        "stocks.MouvementStock",
        # Catégories : le catalogue se pilote depuis les Produits (filtre par
        # catégorie + bouton dans l'en-tête), une section de plus n'apporte rien.
        "categories.Categorie",
        # Paramètres : la vraie interface est /admin/parametres/ ; le modèle
        # n'est qu'un support de stockage, sa liste n'est jamais consultée.
        "parametres.Parametre",
        # Comptes : la gestion des utilisateurs est un onglet de la console
        # « Paramètres & Utilisateurs » (/admin/parametres/?onglet=utilisateurs).
        # La fiche d'un compte reste accessible par son URL (profil, édition,
        # mot de passe) ; la liste, elle, n'a pas sa place dans la navigation :
        # deux entrées pour le même travail obligeraient à choisir où aller.
        "accounts.User",
        # Traçabilité (accès via API ou pages dédiées)
        "accounts.LoginEvent",
        # Internes allauth
        "socialaccount.SocialAccount",
        "socialaccount.SocialApp",
        "socialaccount.SocialToken",
    ],
    # Menu supérieur : raccourcis rapides (quotidiens).
    # La Caisse et les Rapports ont leur propre entrée dans la navigation.
    "topmenu_links": [
        {"name": "Dashboard", "url": "admin:index", "icon": "fas fa-home"},
    ],
    # Icônes par modèle — premium icons
    "icons": {
        "accounts.User": "fas fa-user-crown",
        "clients.Client": "fas fa-address-card",
        "clients.ReglementClient": "fas fa-money-check-alt",
        "produits.Produit": "fas fa-wine-bottle",
        "stocks.Stock": "fas fa-warehouse",
        "ventes.Vente": "fas fa-receipt",
        "ventes.SessionCaisse": "fas fa-cash-register",
        "promotions.Promotion": "fas fa-tags",
        "categories.Categorie": "fas fa-layer-group",
    },
    "default_icon_parents": "fas fa-folder",
    "default_icon_children": "fas fa-circle",
    # Ordre du menu latéral — du plus au moins utilisé
    "order_with_respect_to": [
        "ventes",
        "clients",
        "produits",
        "stocks",
        "promotions",
        "categories",
        "accounts",
    ],
    "changeform_format": "horizontal_tabs",
}

JAZZMIN_UI_TWEAKS = {
    "navbar": "navbar-white navbar-light",
    "theme": "lux",  # Thème "Luxury" : typo fine, grands espaces, style très haut de gamme
    "sidebar": "sidebar-dark-warning",
    "sidebar_fixed": True,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": True,
    "default_theme_mode": "light",
    "button_classes": {
        "primary": "btn-dark", # Boutons principaux en noir
        "secondary": "btn-outline-dark", # Boutons secondaires contour noir
        "info": "btn-info",
        "warning": "btn-warning", # Boutons d'action en Or/Doré
        "danger": "btn-danger",
        "success": "btn-success"
    },
    "actions_sticky_top": True
}
