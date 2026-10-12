import json
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from django import template

from apps.dashboard.stats import stats_completes

register = template.Library()


# Icônes par label d'application pour le menu latéral de l'admin.
APP_ICONS = {
    'ventes': 'fas fa-receipt',
    'clients': 'fas fa-users',
    'produits': 'fas fa-wine-bottle',
    'stocks': 'fas fa-boxes-stacked',
    'categories': 'fas fa-tags',
    'promotions': 'fas fa-percent',
    'accounts': 'fas fa-user-shield',
    'auth': 'fas fa-user-cog',
}


@register.filter
def dget(d, key):
    """Accès dict sécurisé depuis un template (retourne None si absent)."""
    return d.get(key) if isinstance(d, dict) else None


@register.filter
def app_icon(app_label):
    """Icône FA du groupe d'application (défaut : dossier)."""
    return APP_ICONS.get(app_label, 'fas fa-folder')


# Icônes PNG par modèle (source templates/admin/icone/), pour le menu latéral.
MODEL_ICON_PNG = {
    'ventes.Vente': 'ventes-256.png',
    'ventes.SessionCaisse': 'caisse-256.png',
    'clients.Client': 'clients-256.png',
    'clients.ReglementClient': 'reglements-256.png',
    'produits.Produit': 'produits-256.png',
    'stocks.Stock': 'stocks-256.png',
    'stocks.MouvementStock': 'mouvements-256.png',
    'promotions.Promotion': 'promotions-256.png',
    'categories.Categorie': 'categories-256.png',
    'accounts.User': 'comptes-256.png',
}


@register.filter
def icon_png(model_key):
    """Nom de fichier PNG pour un modèle (templates/admin/icone/), sinon None."""
    return MODEL_ICON_PNG.get(model_key)


@register.filter
def sub(value, arg):
    """Soustraction sûre pour les templates (retourne 0 si non numérique)."""
    try:
        return value - arg
    except (TypeError, ValueError):
        return 0


# Ordre métier du menu latéral (du plus utilisé au moins utilisé).
APP_ORDER = [
    'ventes',
    'clients',
    'produits',
    'stocks',
    'promotions',
    'categories',
    'accounts',
]


@register.filter
def order_apps(apps):
    """Trie les applications ADMIN selon APP_ORDER (les inconnues restent à la fin)."""
    apps = list(apps or [])
    by_label = {app.get('app_label'): app for app in apps}
    ordered = [by_label[label] for label in APP_ORDER if label in by_label]
    tail = [app for app in apps if app.get('app_label') not in APP_ORDER]
    return ordered + tail


@register.simple_tag(takes_context=True)
def app_models_visibles(context, app):
    """Modèles d'une application réellement affichables dans le menu.

    Sans cela, une application dont tous les modèles sont masqués
    (catégories, par exemple) laisserait un intitulé de section orphelin
    au-dessus d'un menu vide.
    """
    from django.conf import settings as dj_settings

    jazzmin = getattr(dj_settings, 'JAZZMIN_SETTINGS', {}) or {}
    masquees = {m.lower() for m in jazzmin.get('hide_models', [])}
    visibles = []
    for model in app.get('models') or []:
        cle = f"{app.get('app_label')}.{model.get('object_name')}".lower()
        if model.get('admin_url') and cle not in masquees:
            visibles.append(model)
    return visibles


@register.simple_tag
def get_dashboard_stats():
    """Toutes les agrégations du tableau de bord (voir apps.dashboard.stats)."""
    return stats_completes()


_UNITES = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf",
           "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize",
           "dix-sept", "dix-huit", "dix-neuf"]
_DIZAINES = ["", "dix", "vingt", "trente", "quarante", "cinquante", "soixante"]


def _petit_mot(n):
    """0..999 en toutes lettres (français)."""
    if n < 20:
        return _UNITES[n]
    if n < 70:
        d, u = divmod(n, 10)
        base = _DIZAINES[d]
        if u == 0:
            return base
        if u == 1:
            return base + "-et-un"
        return base + "-" + _UNITES[u]
    if n < 80:
        if n == 71:
            return "soixante-et-onze"
        return "soixante-" + _petit_mot(n - 60)
    if n < 90:
        return "quatre-vingts" if n == 80 else "quatre-vingt-" + _petit_mot(n - 80)
    if n < 100:
        return "quatre-vingt-" + _petit_mot(n - 80)
    c, r = divmod(n, 100)
    if c == 1:
        return "cent" if r == 0 else "cent " + _petit_mot(r)
    if r == 0:
        return _petit_mot(c) + " cents"
    return _petit_mot(c) + " cent " + _petit_mot(r)


def _int_en_lettres(n):
    """Entier non négatif en toutes lettres."""
    if n == 0:
        return "zéro"
    groupes = []
    while n > 0:
        groupes.append(n % 1000)
        n //= 1000
    parties = []
    for i in range(len(groupes) - 1, -1, -1):
        g = groupes[i]
        if g == 0:
            continue
        if i == 0:
            base = _petit_mot(g)
        elif i == 1:
            base = "mille" if g == 1 else _petit_mot(g) + " mille"
        elif i == 2:
            base = "un million" if g == 1 else _petit_mot(g) + " millions"
        else:
            base = "un milliard" if g == 1 else _petit_mot(g) + " milliards"
        parties.append(base)
    return " ".join(parties)


def montant_en_lettres(montant):
    """Montant décimal en toutes lettres : 'x ariary et y iraimbilanja'."""
    montant = Decimal(str(montant))
    partie_entiere = int(montant.to_integral_value(rounding=ROUND_DOWN))
    centimes = int((montant * 100).to_integral_value(rounding=ROUND_DOWN) % 100)
    entiers = _int_en_lettres(partie_entiere)
    if centimes:
        return f"{entiers} ariary et {_int_en_lettres(centimes)} iraimbilanja"
    return f"{entiers} ariary"


@register.filter
def en_lettres(value):
    """Filtre template : convertit un montant en toutes lettres (français)."""
    return montant_en_lettres(value)

@register.filter
def intcomma(value):
    """Sépare les milliers par des espaces (équivalent local de humanize).

    Évite une dépendance à django-humanize pour deux gabarits.
    """
    try:
        nombre = int(value)
    except (TypeError, ValueError):
        return value
    signe = '-' if nombre < 0 else ''
    return f"{signe}{abs(nombre):,}".replace(',', '\u202f')
