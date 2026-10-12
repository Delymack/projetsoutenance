from django import template
from django.conf import settings
from django.templatetags.static import static as static_url

register = template.Library()

# ------------------------------------------------------------------
# Icônes PNG du menu latéral (dossier « icone » de STATICFILES_DIRS).
# Chaque app_label métier est associé à une icône PNG dédiée.
# ------------------------------------------------------------------
SIDEBAR_PNG = {
    'dashboard': 'dashboard-256.png',
    'caisse': 'caisse-256.png',
    'rapports': 'statistiques-256.png',
    'ventes': 'ventes-256.png',
    'clients': 'clients-256.png',
    'reglements': 'reglements-256.png',
    'produits': 'produits-256.png',
    'stocks': 'stocks-256.png',
    'mouvements': 'mouvements-256.png',
    'promotions': 'promotions-256.png',
    'categories': 'categories-256.png',
    'commandes': 'shopping-cart-add-button_icon-icons.com_56132.png',
    'accounts': 'comptes-256.png',
    'parametres': 'parametres-256.png',
    'securite': 'securite-256.png',
    'objectif': 'objectif-256.png',
    'facture': 'facture-256.png',
    'qr': 'qr-code-256.png',
    'paiement': 'paiement-mobile-256.png',
    'journal': 'mouvements-256.png',
}

# Couleur d'accent (classe CSS) par app_label — pastille teintée.
SIDEBAR_TINT = {
    'dashboard': 'nav-icon-dashboard',
    'caisse': 'nav-icon-caisse',
    'rapports': 'nav-icon-rapports',
    'ventes': 'nav-icon-ventes',
    'clients': 'nav-icon-clients',
    'reglements': 'nav-icon-clients',
    'produits': 'nav-icon-produits',
    'stocks': 'nav-icon-stocks',
    'mouvements': 'nav-icon-stocks',
    'promotions': 'nav-icon-promotions',
    'categories': 'nav-icon-categories',
    'accounts': 'nav-icon-comptes',
    'parametres': 'nav-icon-parametres',
    'securite': 'nav-icon-parametres',
    'journal': 'nav-icon-journal',
}

# Libellé épuré (sans emoji) par app_label.
SIDEBAR_LABEL = {
    'ventes': 'Ventes',
    'clients': 'Clients',
    'reglements': 'Règlements',
    'produits': 'Vins & Produits',
    'stocks': 'Stocks',
    'mouvements': 'Mouvements',
    'promotions': 'Promotions',
    'categories': 'Catégories',
    'accounts': 'Comptes & Sécurité',
    'parametres': 'Paramètres',
}


@register.simple_tag
def sidebar_icon(app_key):
    """URL statique de l'icône PNG pour un app_label / raccourci."""
    name = SIDEBAR_PNG.get(app_key, '')
    return static_url('icone/' + name) if name else ''


@register.filter
def sidebar_tint(app_key):
    """Classe CSS d'accent couleur pour la pastille de l'icône PNG."""
    return SIDEBAR_TINT.get(app_key, 'nav-icon-comptes')


@register.filter
def sidebar_label(app_key):
    """Libellé épuré du menu (sans emoji des verbose_name)."""
    return SIDEBAR_LABEL.get(app_key, app_key.title())


@register.simple_tag
def google_configured():
    """Vrai si l'OAuth Google est paramétré (client id présent)."""
    return bool(settings.GOOGLE_OAUTH2_CLIENT_ID)


@register.simple_tag(takes_context=True)
def google_login_url(context, next_url='/admin/'):
    """URL de connexion Google (allauth) avec redirection demandée."""
    request = context.get('request')
    next = getattr(request, 'GET', None)  # noqa: A001
    if next:
        redirect = ((next.get('next')) or next_url)
    else:
        redirect = next_url
    return f'/accounts/google/login/?process=login&next={redirect}'


@register.filter
def to_list(value):
    """Convertit une valeur en liste (une chaîne devient une liste d'un élément).

    `JAZZMIN_SETTINGS.custom_js` est indifféremment une chaîne ou une liste :
    ce filtre permet de toujours itérer proprement, sans dépendre des
    comparaisons de types du langage de template.
    """
    if isinstance(value, str):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]