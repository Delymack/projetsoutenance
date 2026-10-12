"""Sauvegarde de la base de données.

Trois niveaux, du meilleur au moins bon :

* **SQLite** — copie à chaud via l'API ``sqlite3.Connection.backup()``.
  Aucun arrêt de service, aucune dépendance externe.
* **PostgreSQL** — ``pg_dump -Fc`` quand le binaire est présent. Le fichier
  est restituable par ``pg_restore``.
* **JSON compressé** — filet de sécurité si ``pg_dump`` manque : on exporte
  le contenu de toutes les tables. C'est lisible par un humain et restaurable
  par un script, mais ce n'est pas un dump natif.

Aucune restauration n'est exposée dans l'interface : remplacer la base
courante depuis une page web est le moyen le plus sûr de tout perdre. Le
préfixe de date dans le nom du fichier limite le risque de restauration
trompeuse.
"""

import gzip
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.parametres.models import Sauvegarde

#: Nombre de sauvegardes conservées au-delà de la rétention en jours.
GARDER = 5


def moteur():
    """Nom court du moteur de la base par défaut."""
    engine = settings.DATABASES['default']['ENGINE']
    if 'sqlite' in engine:
        return 'sqlite3'
    if 'postgres' in engine:
        return 'postgresql'
    return engine.rsplit('.', 1)[-1]


def horodatage():
    return timezone.localtime().strftime('%Y%m%d-%H%M%S')


def _json_safe(valeur):
    if isinstance(valeur, (datetime, date, time)):
        return valeur.isoformat()
    if isinstance(valeur, Decimal):
        return str(valeur)
    if isinstance(valeur, (bytes, bytearray, memoryview)):
        return bytes(valeur).hex()
    if hasattr(valeur, 'isoformat'):
        return valeur.isoformat()
    return valeur


def _compter():
    with connection.cursor() as curseur:
        tables = connection.introspection.table_names()
        total = 0
        for table in tables:
            try:
                curseur.execute(f'SELECT COUNT(*) FROM "{table}"')
                total += curseur.fetchone()[0]
            except Exception:  # table sans lecture (vue, extension)
                continue
    return len(tables), total


def _sauvegarde_sqlite(cible: Path):
    source = settings.DATABASES['default'].get('NAME')
    if not source or not Path(source).exists():
        raise RuntimeError(f'Base SQLite introuvable : {source!r}')
    # L'API backup copie page par page : la base reste utilisable pendant
    # l'opération, contrairement à un simple shutil.copy sur un fichier
    # pendant qu'une écriture a lieu.
    src = sqlite3.connect(f'file:{source}?mode=ro', uri=True, timeout=30)
    try:
        dst = sqlite3.connect(str(cible))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return 'sqlite3'


def _sauvegarde_pgdump(cible: Path):
    conf = settings.DATABASES['default']
    if shutil.which('pg_dump') is None:
        raise FileNotFoundError('pg_dump absent du système')
    env = dict(os.environ)
    for cle, attr in (('PGPASSWORD', 'PASSWORD'), ('PGUSER', 'USER'), ('PGHOST', 'HOST'), ('PGPORT', 'PORT')):
        if conf.get(attr):
            env[cle] = str(conf[attr])
    commande = [
        'pg_dump', '--format=custom', '--no-owner', '--no-privileges',
        '--file', str(cible),
    ]
    if conf.get('HOST'):
        commande += ['--host', str(conf['HOST'])]
    if conf.get('PORT'):
        commande += ['--port', str(conf['PORT'])]
    if conf.get('USER'):
        commande += ['--username', str(conf['USER'])]
    commande.append(str(conf['NAME']))
    resultat = subprocess.run(
        commande, env=env, capture_output=True, text=True, timeout=600,
    )
    if resultat.returncode != 0:
        raise RuntimeError((resultat.stderr or 'pg_dump a échoué').strip()[:500])
    return 'pgdump'


def _sauvegarde_json(cible: Path):
    """Export logique de toutes les tables, compressé en gzip."""
    dump = {'moteur': moteur(), 'genere_le': timezone.localtime().isoformat(), 'tables': {}}
    tables = set(connection.introspection.table_names())
    nb = 0
    for model in apps.get_models():
        table = model._meta.db_table
        if table not in tables:
            continue
        lignes = []
        try:
            for objet in model.objects.all().iterator(chunk_size=1000):
                lignes.append({
                    champ.name: _json_safe(getattr(objet, champ.attname))
                    for champ in model._meta.concrete_fields
                })
        except Exception:
            continue
        nb += len(lignes)
        dump['tables'][table] = lignes
    # On écrit dans un fichier temporaire puis on renomme : un téléchargement
    # ne peut pas tomber sur un fichier à moitié écrit.
    tmp = cible.with_suffix('.tmp')
    with gzip.open(tmp, 'wt', encoding='utf-8') as flux:
        json.dump(dump, flux, ensure_ascii=False, default=str)
    tmp.replace(cible)
    return 'json', nb


def creer(utilisateur=None, purger=True):
    """Crée une sauvegarde et renvoie la ligne ``Sauvegarde`` correspondante."""
    from apps.parametres.models import EntreeJournal

    ligne = Sauvegarde.objects.create(
        format=Sauvegarde.Format.SQLITE, engine=moteur(), utilisateur=utilisateur,
    )
    # Le dossier daté est ajouté par ``upload_to`` : on ne lui passe que le nom.
    nom = f'sauvegarde-{moteur()}-{horodatage()}'
    try:
        nb_tables, nb_lignes = _compter()
        ligne.nb_tables, ligne.nb_lignes = nb_tables, nb_lignes
        with tempfile.TemporaryDirectory() as dossier:
                brut = Path(dossier) / 'dump'
                format_ = moteur()
                nb = 0
                motif_repli = ''
                try:
                    if format_ == 'sqlite3':
                        _sauvegarde_sqlite(brut)
                        nom += '.sqlite3'
                    elif format_ == 'postgresql':
                        _sauvegarde_pgdump(brut)
                        nom += '.dump'
                    else:
                        raise RuntimeError(f'Base {format_} : sauvegarde native non gérée.')
                except (FileNotFoundError, RuntimeError, subprocess.SubprocessError, OSError) as exc:
                    # Sans base sur disque (SQLite en mémoire), sans binaire
                    # pg_dump, ou si le dump est refusé : l'export logique est
                    # moins faithful mais toujours bien plus utile qu'un échec.
                    motif_repli = str(exc)[:300]
                    format_, nb = _sauvegarde_json(brut)
                    nom += '.json.gz'
                taille = brut.stat().st_size
                with open(brut, 'rb') as flux:
                    ligne.fichier.save(nom, ContentFile(flux.read()), save=False)

        ligne.format = format_
        ligne.taille = taille
        ligne.statut = Sauvegarde.Statut.REUSSIE
        if nb:
            ligne.nb_lignes = nb
        ligne.erreur = motif_repli
        ligne.save()
        EntreeJournal.objects.create(
            action=EntreeJournal.Action.MODIF, section='SYSTEME', cle='_sauvegarde',
            libelle=_('Sauvegarde de la base de données'),
            avant='—', apres=f'{ligne.get_format_display()} · {ligne.taille_lisible}',
            utilisateur=utilisateur,
        )
    except Exception as exc:  # la trace reste consultable dans l'onglet
        ligne.statut = Sauvegarde.Statut.ECHEC
        ligne.erreur = str(exc)[:1000]
        ligne.save(update_fields=['statut', 'erreur'])
    if purger:
        purger_anciennes()
    return ligne


def chemin(ligne):
    """Chemin disque d'une sauvegarde, ``None`` si le fichier a disparu.

    On passe par le stockage Django plutôt que par ``MEDIA_ROOT`` assemblé à la
    main : c'est le même endroit que celui qui a écrit le fichier, y compris
    quand ``MEDIA_ROOT`` est redéfini (tests, environnement).
    """
    if not ligne.fichier:
        return None
    try:
        chemin_ = Path(default_storage.path(ligne.fichier.name))
    except (NotImplementedError, SuspiciousFileOperation, ValueError):
        return None
    return chemin_ if chemin_.is_file() else None


def purger_anciennes(garder=GARDER, jours=None):
    """Supprime les sauvegardes au-delà de ``garder`` pièces et de l'âge."""
    from apps.parametres.services import get_param

    if jours is None:
        jours = get_param('systeme_sauvegarde_retention', 30)
    limite = timezone.now() - timedelta(days=int(jours or 30))
    restantes = list(Sauvegarde.objects.filter(statut=Sauvegarde.Statut.REUSSIE).order_by('-date'))
    a_supprimer = restantes[garder:]
    for ligne in a_supprimer:
        if ligne.date > limite:
            continue
        fichier = chemin(ligne)
        if fichier:
            fichier.unlink(missing_ok=True)
        ligne.fichier.delete(save=False)
        ligne.delete()
    # Les échecs n'ont pas de fichier à purger : on n'en garde que 10.
    echecs = Sauvegarde.objects.filter(statut=Sauvegarde.Statut.ECHEC).order_by('-date')
    ids = list(echecs.values_list('id', flat=True)[10:])
    Sauvegarde.objects.filter(id__in=ids).delete()
    return len(a_supprimer)


def resume():
    """``(lignes, volume_total)`` pour l'onglet Sauvegarde."""
    lignes = list(Sauvegarde.objects.select_related('utilisateur')[:20])
    return lignes, sum(l.taille or 0 for l in lignes)
