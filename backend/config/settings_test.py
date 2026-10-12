"""Paramètres dédiés à pytest : SQLite rapide et aucun ping réseau.

Importe la configuration normale puis force DEBUG et bascule sur SQLite,
et neutralise la vérification PostgreSQL effectuée au chargement — pour que
la suite de tests soit rapide et déterministe, sans dépendre d'un serveur
PostgreSQL local.
"""
import os

# À positionner AVANT l'import de config.settings :
# - DEBUG actif (AUTH_SIGNUP_ENABLED, DEMO_LOGIN, etc.) comme en dev ;
# - aucun ping PostgreSQL au chargement (variable DB_SKIP_FALLBACK_PING).
os.environ['DB_SKIP_FALLBACK_PING'] = '1'
# `setdefault` ne suffit pas : le poste peut déjà exporter DEBUG (ex.
# `DEBUG=release` dans le shell), auquel cas config.settings lit cette valeur,
# passe en production et active SECURE_SSL_REDIRECT — chaque appel de test est
# alors redirigé en 301 vers https et la suite entière échoue.
os.environ['DEBUG'] = 'True'

from config.settings import *  # noqa: E402,F401,F403

# Ceinture et bretelles : même si un autre module d'environnement repassait
# DEBUG à False, les tests s'exécutent en HTTP local.
DEBUG = True
SECURE_SSL_REDIRECT = False

# Base de test isolée : SQLite en mémoire (aucune dépendance à PostgreSQL,
# aucun accès disque pendant l'exécution de la suite).
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
}

# `settings.TESTING` (détecté via sys.argv) est faux sous pytest : sans ce
# drapeau, les services OTP partent en envoi réel (Resend / eSMS Africa)
# pendant la suite. En test, les codes vont uniquement en console.
TESTING = True

# L'ouverture de caisse est une contrainte du poste de caisse, pas du
# domaine : les tests de vente doivent pouvoir créer des ventes sans ouvrir
# de session. Le comportement est couvert à part (tests/test_caisse_pos.py).
SOCIETE = {**SOCIETE, 'caisse_session_requise': False}