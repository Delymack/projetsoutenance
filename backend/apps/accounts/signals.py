"""Signaux d'authentification : historique de connexion, alerte et 2FA.

* ``user_logged_in`` : enregistre l'événement (SUCCESS), stocke l'appareil /
  l'IP dans la session, signale la double authentification en attente et
  envoie une alerte e-mail en cas d'appareil inconnu.
* ``user_login_failed`` : enregistre l'événement (FAILED) pour la traçabilité
  (le verrouillage, lui, est géré dans le backend — il couvre aussi l'API).
"""
from time import time as _timestamp

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.accounts.models import LoginEvent, User
from apps.accounts.services import (
    client_ip,
    device_label,
    send_new_device_alert,
)

#: Périmètre de gestion accordé automatiquement au rôle Gestionnaire à la
#: création : le catalogue, le stock, les promotions, les clients et les ventes.
#: La console « Utilisateurs & paramètres » reste un accès ADMIN ; les comptes
#: et les réglages ne sont pas couverts par ce mécanisme.
MODELES_GESTION = {
    ('produits', 'produit'),
    ('produits', 'categorie'),
    ('stocks', 'stock'),
    ('promotions', 'promotion'),
    ('clients', 'client'),
    ('ventes', 'vente'),
}
ACTIONS_GESTION = ('view', 'add', 'change', 'delete')


def _accorder_permissions_gestion(user):
    if user.is_superuser:
        return
    for app_label, modele in MODELES_GESTION:
        try:
            content_type = ContentType.objects.get_by_natural_key(app_label, modele)
        except ContentType.DoesNotExist:
            continue
        for action in ACTIONS_GESTION:
            try:
                permission = Permission.objects.get(
                    codename=f'{action}_{modele}', content_type=content_type,
                )
            except Permission.DoesNotExist:
                continue
            user.user_permissions.add(permission)


@receiver(post_save, sender=User)
def ouvrir_les_droits_de_gestion(sender, instance, created, **kwargs):
    """Un compte créé avec le rôle Gestionnaire reçoit ses droits de gestion.

    L'octroi se fait à la création uniquement : les droits restent ensuite
    modulables à la main dans le back-office, sans être réimposés à chaque
    sauvegarde.
    """
    if created and instance.role == User.Role.GESTIONNAIRE:
        _accorder_permissions_gestion(instance)


def _device_context(request):
    ua = (request.META.get('HTTP_USER_AGENT', '') if request else '')[:2000]
    return client_ip(request), ua, device_label(ua)


@receiver(user_logged_in)
def on_logged_in(sender, request, user, **kwargs):
    if not request or not user or not user.pk:
        return None

    ip, _, appareil = _device_context(request)

    # Avant d'écraser, sauvegarder les infos de la connexion précédente
    prev_device = request.session.get('device', '')
    prev_ip = request.session.get('ip', '')
    prev_date = request.session.get('login_at', '')
    if prev_device or prev_ip:
        request.session['last_login_device'] = prev_device
        request.session['last_login_ip'] = prev_ip
        if prev_date:
            from datetime import datetime
            request.session['last_login_date'] = datetime.fromtimestamp(prev_date).strftime('%d/%m/%Y à %H:%M')
        else:
            request.session['last_login_date'] = ''

    request.session.setdefault('device', appareil)
    request.session['ip'] = ip
    request.session['login_at'] = int(_timestamp())

    event = LoginEvent.objects.create(
        user=user, statut=LoginEvent.Statut.SUCCESS, ip=ip,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:2000],
        appareil=appareil,
    )

    # Double authentification obligatoire pour ce compte ?
    if getattr(user, 'totp_enabled', False):
        request.session['twofa_pending'] = True

    if getattr(settings, 'AUTH_LOGIN_ALERT_EMAIL', True):
        try:
            send_new_device_alert(user, request, appareil, event)
        except Exception:  # noqa: BLE001 — une alerte ne bloque jamais le login
            pass
    return None


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request, **kwargs):
    if not request or not credentials or not credentials.get('username'):
        return None
    user = User.objects.filter(
        username__iexact=credentials['username']
    ).first() or User.objects.filter(email__iexact=credentials['username']).first()
    if user is None:
        return None
    ip, _, appareil = _device_context(request)
    LoginEvent.objects.create(
        user=user, statut=LoginEvent.Statut.FAILED, ip=ip,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:2000],
        appareil=appareil,
    )
    return None