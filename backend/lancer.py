clear
#!/usr/bin/env python
"""Lanceur de l'application installée (exécutable autonome Windows).

Au double-clic, ce script :

1. prépare le dossier de données (base, ``.env``, photos) ;
2. applique les migrations de la base ;
3. démarre le back-office Django sur ``127.0.0.1`` ;
4. ouvre le navigateur sur la page de connexion.

En développement, il se comporte comme ``manage.py runserver`` : c'est le
même point d'entrée, ce qui évite deux chemins de code qui divergeraient./

Options :
    --port 8000        port d'écoute
    --no-browser       ne pas ouvrir le navigateuro
    --seed             remplir la base avec le jeu de démonstration
    --diagnostic       afficher la configuration et sortir (sans démarrer)
    --version          afficher la version et sortir
    --reset-migrations repartir de zéro (base neuve)
    --admin <mdp>      mot de passe du compte administrateur créé au premier
                       lancement (sinon il est généré et affiché)
"""
import argparse
import os
import sys
import webbrowser
from pathlib import Path

#.doit précéder l'import de Django : les réglages lisent les chemins.
if __package__ in (None, ''):  # exécution directe (exécutable figé)
    sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


def _analyser_arguments():
    analyseur = argparse.ArgumentParser(
        prog='lazanibetsileo',
        description="Back-office Lazan'i Betsileo (application locale).",
    )
    analyseur.add_argument('--port', type=int, default=None, help="port d'écoute")
    analyseur.add_argument('--no-browser', action='store_true', help="ne pas ouvrir le navigateur")
    analyseur.add_argument('--seed', action='store_true', help="remplir la base de démonstration")
    analyseur.add_argument('--diagnostic', action='store_true', help="afficher la configuration et sortir")
    analyseur.add_argument('--version', action='store_true', help="afficher la version et sortir")
    analyseur.add_argument(
        '--reset-migrations',
        action='store_true',
        help="repartir de zéro (base neuve) : la base existante est effacée",
    )
    analyseur.add_argument(
        '--admin',
        metavar='MOT_DE_PASSE',
        default=None,
        help="mot de passe du compte administrateur créé au premier lancement",
    )
    return analyseur.parse_args()


def _version() -> str:
    from config import __version__

    return __version__


def _diagnostic() -> None:
    """Affiche où vivent les données et si tout est en place."""
    import django

    django.setup()
    from django.conf import settings

    from config.chemins import BASE_DIR, DATA_DIR, INSTALLE

    print(f"Application installée : {'oui' if INSTALLE else 'non'}")
    print(f"Code       : {BASE_DIR}")
    print(f"Données    : {DATA_DIR}")
    print(f"Base       : {settings.DATABASES['default']['NAME']}")
    print(f"Photos     : {settings.MEDIA_ROOT}")
    print(f"Statique   : {settings.STATIC_ROOT}")
    print(f"Mode debug : {settings.DEBUG}")
    print(f"Hôtes      : {', '.join(settings.ALLOWED_HOSTS)}")
    print(f"Port       : {os.environ.get('LAZANI_PORT', '8000')}")


def _appliquer_migrations() -> None:
    from django.core.management import call_command

    call_command('migrate', interactive=False, verbosity=1)


def _reinitialiser_base() -> None:
    """Efface la base existante et repart de zéro.

    On supprime le fichier SQLite (le mode installé utilise SQLite) puis on
    réapplique toutes les migrations. Les données de l'utilisateur sont
    perdues : l'option est explicite, jamais automatique.
    """
    from django.conf import settings

    from config.chemins import INSTALLE

    if not INSTALLE:
        print(
            "Attention : « --reset-migrations » est réservé à l'application "
            "installée. En développement, utilisez la gestion des migrations "
            "de Django (makemigrations / migrate)."
        )
        return

    # Django tient en cache la connexion : on la referme d'abord, sinon le
    # fichier reste ouvert et sa suppression peut échouer sous Windows.
    from django.db import connections

    for connexion in connections.all():
        connexion.close()

    chemin = settings.DATABASES['default'].get('NAME')
    if chemin:
        fichier = Path(chemin)
        if fichier.exists():
            fichier.unlink()
            print(f'Base effacée : {fichier}')


def _creer_administrateur(mot_de_passe: str | None = None) -> None:
    """Crée le compte administrateur s'il n'existe aucun accès au back-office.

    Une application installée démarre avec une base vide : sans ce compte,
    personne ne peut se connecter. Le mot de passe est soit fourni par
    l'utilisateur (``--admin``), soit généré puis affiché une seule fois.
    """
    from apps.accounts.models import User

    if User.objects.filter(is_superuser=True).exists():
        return

    if User.objects.filter(is_staff=True).exists():
        # Un accès au back-office existe déjà (base restaurée, jeu de
        # démonstration…) : on ne crée pas de compte concurrent.
        return

    genere = mot_de_passe is None
    if genere:
        import secrets

        mot_de_passe = secrets.token_urlsafe(12)

    admin = User(
        username='admin',
        email=None,
        first_name="Lazan'i",
        last_name='Betsileo',
        role=User.Role.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    admin.set_password(mot_de_passe)
    admin.save()

    print('=' * 64)
    print('  Compte administrateur créé')
    print('=' * 64)
    print('  Identifiant : admin')
    if genere:
        print(f'  Mot de passe : {mot_de_passe}')
        print('  (à noter : il ne sera plus affiché)')
    else:
        print('  Mot de passe : celui que vous avez choisi')
    print('=' * 64)
    # Le mot de passe ne s'affiche qu'une fois : on force l'écriture dans la
    # console (la sortie est bufferisée quand elle n'est pas un terminal).
    sys.stdout.flush()


def _installer_images_produits() -> None:
    """Copie les photos du catalogue dans le dossier de données.

    Les images sont servies depuis ``MEDIA_ROOT`` (dossier de données en
    application installée). Elles sont donc copiées au premier lancement,
    et à chaque lancement si l'utilisateur en a supprimé une.

    La source est ``photos_catalogue`` : ce sont les photos allégées
    embarquées avec le programme (cf. ``scripts/preparer_photos_catalogue.py``).
    En développement, on préfère le dossier ``media/produits``, qui contient
    les fichiers d'origine.
    """
    import shutil

    from django.conf import settings

    from config.chemins import BASE_DIR, INSTALLE

    if not INSTALLE:
        return

    sources = [BASE_DIR / 'photos_catalogue']
    if (BASE_DIR / 'media' / 'produits').is_dir():
        sources.insert(0, BASE_DIR / 'media' / 'produits')

    destination = Path(settings.MEDIA_ROOT) / 'produits'
    destination.mkdir(parents=True, exist_ok=True)

    for source in sources:
        if not source.is_dir():
            continue
        for image in source.iterdir():
            if not image.is_file():
                continue
            cible = destination / image.name
            if not cible.exists():
                shutil.copy2(image, cible)


def _semer() -> None:
    """Charge le jeu de démonstration.

    Le script est idempotent : il met à jour les objets existants par leur
    nom plutôt que de les dupliquer. On l'exécute dans le même processus
    (il appelle lui-même ``django.setup()``).
    """
    import runpy

    from config.chemins import BASE_DIR

    script = BASE_DIR / 'seed_soutenance.py'
    if not script.exists():
        print("Le jeu de démonstration n'est pas présent dans cette version.")
        return
    print('Chargement des données de démonstration…')
    runpy.run_path(str(script), run_name='__main__')


def _ouvrir_navigateur(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001 — l'absence de navigateur n'est pas bloquante
        pass


def main() -> int:
    arguments = _analyser_arguments()

    if arguments.version:
        print(_version())
        return 0
    if arguments.diagnostic:
        _diagnostic()
        return 0

    import django

    django.setup()

    from django.conf import settings

    port = arguments.port or int(os.environ.get('LAZANI_PORT', '8000'))
    url = f'http://127.0.0.1:{port}/admin/login/'

    print('=' * 64)
    print("  Lazan'i Betsileo — back-office local")
    print('=' * 64)
    print(f'  Données   : {settings.MEDIA_ROOT.parent}')
    print(f'  Ouverture : {url}')
    print('  Arrêt     : Ctrl+C')
    print('=' * 64)

    if arguments.reset_migrations:
        _reinitialiser_base()

    _appliquer_migrations()
    _installer_images_produits()
    _creer_administrateur(arguments.admin)
    if arguments.seed:
        _semer()

    if not arguments.no_browser:
        # Laisse le serveur démarrer avant d'ouvrir le navigateur.
        import threading

        def _ouvrir_plus_tard():
            import time

            time.sleep(2.5)
            _ouvrir_navigateur(url)

        threading.Thread(target=_ouvrir_plus_tard, daemon=True).start()

    _servir(port, arguments)
    return 0


def _servir(port, arguments) -> None:
    """Démarre le serveur HTTP local.

    ``waitress`` est utilisé s'il est présent : c'est un serveur WSGI
    multi-plateforme (Windows compris), sans l'avertissement « serveur de
    développement ». À défaut, on retombe sur le serveur de Django.
    """
    try:
        from waitress import serve
    except ImportError:
        from django.core.management import call_command

        call_command(
            'runserver',
            f'127.0.0.1:{port}',
            use_reloader=False,
            skip_checks=True,
        )
        return

    from django.core.wsgi import get_wsgi_application

    application = get_wsgi_application()
    print(f'  Serveur local démarré sur http://127.0.0.1:{port}/admin/')
    try:
        serve(application, host='127.0.0.1', port=port, threads=8)
    except KeyboardInterrupt:
        print('\n  Arrêt du serveur.')


if __name__ == '__main__':
    sys.exit(main())
