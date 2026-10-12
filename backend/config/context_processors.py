from django.conf import settings
from django.db.models import F
from django.utils import timezone

from apps.accounts.services import lockout_info
from apps.parametres.services import get_config, get_param


def societe(request):
    """Expose les coordonnées de la société à toutes les vues (facture, admin).

    Les paramètres (console « Paramètres ») priment sur les valeurs statiques
    ``settings.SOCIETE`` : la devise, le contact… se règlent désormais dans
    l'interface sans toucher au code.
    """
    cfg = get_config()
    base = dict(getattr(settings, 'SOCIETE', {}))
    mapping = {
        'nom': 'societe_nom',
        'slogan': 'societe_slogan',
        'adresse': 'societe_adresse',
        'telephone': 'societe_telephone',
        'email': 'societe_email',
        'siret': 'societe_siret',
        'devise': 'societe_devise',
        'fonds_caisse': 'societe_fonds_caisse',
        'objectif_mensuel': 'societe_objectif_mensuel',
    }
    for key, parametre in mapping.items():
        value = cfg.get(parametre)
        if value is not None and str(value) != '':
            base[key] = value
    return {'societe': base}


def site_config(request):
    """Configuration globale exposée aux templates et aux JS du back-office."""
    cfg = get_config()
    from apps.parametres.services import json_config_for_js
    return {'site_config': cfg, 'site_config_json': json_config_for_js()}


def demo_login(request):
    """Aide à la connexion : identifiants de démonstration (actif uniquement en DEBUG et si renseignés)."""
    demo = getattr(settings, 'DEMO_LOGIN', None)
    return {'demo_login': demo if (settings.DEBUG and demo) else None}


def auth_status(request):
    """État d'authentification exposé aux templates.

    * ``auth__signup_enabled`` : autorise l'inscription locale ;
    * ``auth__2fa_enabled`` : la double authentification est active ;
    * ``auth__lockout`` : verrouillage éventuel (identifiant saisi au POST).
    """
    return {
        'auth__signup_enabled': getattr(settings, 'AUTH_SIGNUP_ENABLED', True),
        'auth__2fa_enabled': getattr(settings, 'AUTH_2FA_ENABLED', True),
        'auth__lockout': lockout_info(
            getattr(request, 'POST', None).get('username') if getattr(request, 'method', '') == 'POST' else ''
        ) if getattr(request, 'method', '') == 'POST' else {'locked': False},
    }


def login_greeting(request):
    """Greeting dynamique selon l'heure + dernières infos de connexion.

    Expose :
    * ``greeting_text`` : « Bonjour » / « Bon après-midi » / « Bonsoir »
    * ``greeting_icon`` : icône Font Awesome correspondante
    * ``greeting_hour`` : heure actuelle (format HH:MM)
    * ``last_login_info`` : dict avec device, ip, date de la dernière connexion connue
    """
    now = timezone.localtime(timezone.now())
    hour = now.hour
    if hour < 6:
        greeting_text = 'Bonne nuit'
        greeting_icon = 'fa-moon'
    elif hour < 12:
        greeting_text = 'Bonjour'
        greeting_icon = 'fa-sun'
    elif hour < 18:
        greeting_text = 'Bon après-midi'
        greeting_icon = 'fa-cloud-sun'
    else:
        greeting_text = 'Bonsoir'
        greeting_icon = 'fa-moon-stars'

    last_login_info = None
    session = getattr(request, 'session', None)
    if session:
        last_device = session.get('last_login_device', '')
        last_ip = session.get('last_login_ip', '')
        last_date = session.get('last_login_date', '')
        if last_device or last_ip:
            last_login_info = {
                'device': last_device or 'Appareil inconnu',
                'ip': last_ip or '—',
                'date': last_date or '',
            }

    return {
        'greeting_text': greeting_text,
        'greeting_icon': greeting_icon,
        'greeting_hour': now.strftime('%H:%M'),
        'last_login_info': last_login_info,
    }


def sidebar_badges(request):
    """Indicateurs « live » injectés dans le menu latéral admin (sidebar).

    Reste inerte hors de l'espace authentifié pour ne pas alourdir la connexion.
    Expose ``sb_badges`` : dict de compteurs utilisés par ``base_site.html``.

    * ``ventes_jour``  : ventes payées depuis minuit (badge vert sur « Caisse »)
    * ``commandes_attente`` : commandes clients du site à traiter (badge or)
    * ``stock_alerte`` : nombre de références en rupture OU sous le seuil (badge Stocks)
    * ``promos_actives`` : promotions en cours à cet instant (badge or)
    """
    user = getattr(request, 'user', None)
    if not (user and user.is_authenticated):
        return {'sb_badges': {}}

    from apps.promotions.models import Promotion
    from apps.stocks.models import Stock
    from apps.ventes.models import Reservation, Vente

    now = timezone.now()
    today_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)

    return {
        'sb_badges': {
            'ventes_jour': Vente.objects.filter(date_vente__gte=today_start, statut=Vente.Statut.PAYEE).count(),
            'commandes_attente': Reservation.objects.filter(
                source=Reservation.Source.SITE, statut=Reservation.Statut.EN_ATTENTE
            ).count(),
            'stock_alerte': Stock.objects.filter(
                quantite__lte=F('seuil_alerte')
            ).exclude(quantite=0).count() + Stock.objects.filter(quantite=0).count(),
            'stock_ruptures': Stock.objects.filter(quantite=0).count(),
            'promos_actives': Promotion.objects.filter(
                statut=True, date_debut__lte=now, date_fin__gte=now
            ).count(),
        }
    }


def notifications(request):
    """Expose les alertes opérationnelles et leur état personnel de lecture."""
    from apps.accounts.notifications import (
        active_notifications,
        notifications_pour_utilisateur,
    )

    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        visible_items = notifications_pour_utilisateur(user)
        return {
            'admin_notifications': visible_items,
            'admin_notification_count': sum(item['non_lue'] for item in visible_items),
        }

    return {
        'admin_notifications': [],
        'admin_notification_count': len(active_notifications()),
    }