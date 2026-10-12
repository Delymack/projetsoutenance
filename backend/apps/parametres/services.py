"""Service central des paramètres : lecture typée (cache), écriture, journal."""

import json
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.utils import timezone

from apps.parametres.defaults import DEFAULTS, SECTIONS
from apps.parametres.models import EntreeJournal, Parametre

CACHE_KEY = 'wineadmin:config:v2'
CACHE_TTL = 300

_META = {d[1]: d for d in DEFAULTS}  # clé -> (section, cle, libelle, type, defaut, options, aide, ordre)


def _to_bool(raw):
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ('1', 'true', 'oui', 'on', 'yes')


def split_list(raw):
    """Décompose une valeur texte en liste de codes, sans vide ni doublon."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        items = [str(x).strip() for x in raw]
    else:
        items = [x.strip() for x in str(raw).split(',')]
    seen, out = set(), []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _ordered(values, options):
    """Classe les codes selon l'ordre déclaré dans ``options['choix']``."""
    ordre = [c[0] for c in (options or {}).get('choix', [])]
    values = [v for v in split_list(values) if v in ordre or not ordre]
    if not ordre:
        return values
    return sorted(set(values), key=ordre.index)


def _to_decimal(raw):
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0')


def _typed(raw, type_, options):
    if type_ == 'MULTI':
        # La valeur par défaut d'un MULTI est une liste vide : « non
        # renseigné » ne doit pas se confondre avec « vide ».
        return _ordered(raw or '', options)
    if raw is None or raw == '':
        return None
    if type_ == 'INT':
        try:
            return int(str(raw))
        except (ValueError, TypeError):
            return 0
    if type_ == 'DECIMAL':
        return _to_decimal(raw)
    if type_ == 'BOOL':
        return _to_bool(raw)
    return str(raw)


def _to_store(type_, value):
    """Convertit une valeur typée en texte stable pour la base."""
    if type_ == 'MULTI':
        return ','.join(split_list(value))
    if value is None:
        return ''
    if type_ == 'BOOL':
        return '1' if _to_bool(value) else '0'
    if type_ == 'INT':
        try:
            return str(int(value))
        except (ValueError, TypeError):
            return '0'
    if type_ == 'DECIMAL':
        try:
            # `normalize()` retire les zéros de la partie décimale sans toucher
            # à ceux de la partie entière : un simple rstrip('0') transformerait
            # « 20 » en « 2 » (le taux de TVA devenait 2 %).
            return format(_to_decimal(value).normalize(), 'f')
        except Exception:
            return '0'
    return str(value)


def _query_all():
    return {p.cle: p for p in Parametre.objects.all()}


def get_config():
    """Config plate typée : {'cle': valeur_typée} (cache 5 min)."""
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached
    cfg = {}
    rows = _query_all()
    for d in DEFAULTS:
        cle = d[1]
        row = rows.get(cle)
        raw = row.valeur if row else d[4]
        cfg[cle] = _typed(raw, d[3], d[5])
    cache.set(CACHE_KEY, cfg, CACHE_TTL)
    return cfg


def get_param(cle, default=None):
    return get_config().get(cle, default)


def erreur_entries(entries):
    """Contrôle avant écriture : renvoie une liste de messages en français."""
    if not isinstance(entries, dict):
        return ['Paramètres invalides.']
    erreurs = []
    for d in DEFAULTS:
        cle, type_, options = d[1], d[3], d[5] or {}
        if cle not in entries:
            continue
        valeur = entries[cle]
        if type_ == 'MULTI':
            codes = _ordered(valeur, options)
            inconnus = [c for c in split_list(valeur) if c not in {x[0] for x in options.get('choix', [])}]
            if inconnus:
                erreurs.append(f'« {d[2]} » : valeur inconnue ({", ".join(inconnus)}).')
            minimum = int(options.get('minimum') or 0)
            if len(codes) < minimum:
                erreurs.append(f'« {d[2]} » : sélectionnez au moins {minimum} élément.')
            continue
        if options.get('json') and str(valeur).strip():
            # Champ libre censé contenir du JSON (textes de l'accueil, par ex.).
            charge = valeur
            if isinstance(valeur, str):
                try:
                    charge = json.loads(valeur)
                except (TypeError, ValueError):
                    charge = None
            if not isinstance(charge, (dict, list)):
                erreurs.append(f'« {d[2]} » : JSON valide attendu.')
            continue
        if type_ in ('DECIMAL', 'INT') and str(valeur).strip() != '':
            try:
                nombre = Decimal(str(valeur)) if type_ == 'DECIMAL' else int(valeur)
            except (ValueError, TypeError):
                erreurs.append(
                    f'« {d[2]} » : '
                    f'{"nombre décimal" if type_ == "DECIMAL" else "nombre entier"} attendu.'
                )
                continue
            except InvalidOperation:
                erreurs.append(f'« {d[2]} » : nombre décimal attendu.')
                continue

            if type_ == 'DECIMAL' and not nombre.is_finite():
                erreurs.append(f'« {d[2]} » : nombre décimal fini attendu.')
                continue
            if 'min' in options and nombre < options['min']:
                erreurs.append(f'« {d[2]} » : la valeur minimale est {options["min"]}.')
            if 'max' in options and nombre > options['max']:
                erreurs.append(f'« {d[2]} » : la valeur maximale est {options["max"]}.')
    return erreurs


def _normalize(cle, value):
    """Normalise la valeur d'un MULTI avant écriture (ordre des options)."""
    meta = _META.get(cle)
    if meta and meta[3] == 'MULTI':
        return _ordered(value, meta[5])
    return value


def invalidate():
    cache.delete(CACHE_KEY)


def build_sections():
    """Structure pour la console d'administration (valeurs sous forme texte)."""
    rows = _query_all()
    by_section = {s['code']: [] for s in SECTIONS}
    for d in DEFAULTS:
        section, cle, libelle, type_, defaut, options, aide, ordre = d
        row = rows.get(cle)
        valeur = row.valeur if row else defaut
        lisible = valeur
        if type_ == 'MULTI':
            # « ESPECES,MVOLA » se lit mal à l'impression : on montre les
            # libellés, dans l'ordre des options, ceux qui sont cochés.
            labels = dict((options or {}).get('choix', []))
            lisible = ', '.join(labels.get(code, code) for code in _ordered(valeur, options))
        by_section[section].append({
            'cle': cle,
            'libelle': libelle,
            'type': type_,
            'valeur': valeur,
            'valeur_lisible': lisible,
            'options': options or {},
            'aide': aide,
            'ordre': ordre,
            'defaut': defaut,
        })
    for s in SECTIONS:
        s['params'] = sorted(by_section[s['code']], key=lambda p: (p['ordre'], p['cle']))
    return SECTIONS


def save_config(entries, user=None, ip=''):
    """Enregistre un dictionnaire {clé: valeur texte} et journalise les écarts."""
    if not isinstance(entries, dict):
        raise ValueError('Entries must be a mapping')
    rows = _query_all()
    log = []
    for d in DEFAULTS:
        cle = d[1]
        if cle not in entries:
            continue
        new_raw = _to_store(d[3], _normalize(cle, entries[cle]))
        row = rows.get(cle)
        old_raw = row.valeur if row else d[4]
        if old_raw == new_raw:
            continue
        if row:
            row.valeur = new_raw
            row.save(update_fields=['valeur', 'modifie_le'])
        else:
            Parametre.objects.create(
                section=d[0], cle=cle, libelle=d[2], type=d[3], valeur=new_raw,
                options=d[5] or {}, aide=d[6], ordre=d[7],
            )
        log.append((cle, old_raw, new_raw))
    invalidate()
    for cle, old, new in log:
        meta = _META.get(cle)
        EntreeJournal.objects.create(
            action=EntreeJournal.Action.MODIF,
            section=meta[0] if meta else '',
            cle=cle,
            libelle=meta[2] if meta else cle,
            avant=old or '—',
            apres=new or '—',
            utilisateur=user,
            ip=ip or None,
        )
    return len(log)


def import_config(data, user=None, ip=''):
    """Import de masse : fusionne les clés connues présentes dans ``data``."""
    if not isinstance(data, dict):
        raise ValueError('Import invalide : objet JSON attendu')
    known = {d[1]: d for d in DEFAULTS}
    entries = {cle: value for cle, value in data.items() if cle in known}
    nb = save_config(entries, user=user, ip=ip)
    if nb:
        EntreeJournal.objects.create(
            action=EntreeJournal.Action.IMPORT,
            section='SYSTEME',
            cle='_masse',
            libelle='Import de configuration',
            avant=f'{len(entries)} clé(s) reçues',
            apres=f'{nb} valeur(s) appliquée(s)',
            utilisateur=user,
            ip=ip or None,
        )
    return nb


def export_dict():
    rows = _query_all()
    return {d[1]: (rows[d[1]].valeur if d[1] in rows else d[4]) for d in DEFAULTS}


def purge_journal(limit=None):
    """Purge le journal au-delà de la rétention configurée (jours)."""
    days = limit if limit is not None else get_param('systeme_journal_retention', 90)
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(days=int(days))
    return EntreeJournal.objects.filter(date__lt=cutoff).delete()[0]


def json_config_for_js():
    return json.dumps(get_config(), default=str)