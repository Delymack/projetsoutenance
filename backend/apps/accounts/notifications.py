from datetime import timedelta

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserNotification
from apps.promotions.models import Promotion
from apps.stocks.models import Stock
from apps.ventes.models import MessageClient, Reservation


def active_notifications():
    """Construit les alertes actives avec une identité stable par enregistrement."""
    items = []
    stock_url = reverse('admin:stocks_stock_changelist')
    for stock in Stock.objects.filter(produit__statut=True).select_related('produit'):
        if stock.quantite == 0:
            items.append({
                'key': f'stock:rupture:{stock.pk}',
                'title': f'Rupture de stock : {stock.produit.nom}',
                'summary': 'Produit indisponible — réapprovisionnement nécessaire.',
                'icon': 'fa-box-open',
                'level': 'danger',
                'category': 'stock',
                'url': stock_url,
            })
        elif stock.quantite <= stock.seuil_alerte:
            items.append({
                'key': f'stock:faible:{stock.pk}',
                'title': f'Stock faible : {stock.produit.nom}',
                'summary': f'{stock.quantite} unité(s) restante(s), seuil : {stock.seuil_alerte}.',
                'icon': 'fa-boxes-stacked',
                'level': 'warning',
                'category': 'stock',
                'url': stock_url,
            })

    for reservation in Reservation.objects.filter(
        source=Reservation.Source.SITE,
        statut=Reservation.Statut.EN_ATTENTE,
    ).select_related('client'):
        message = f' · {reservation.note}' if reservation.note else ''
        items.append({
            'key': f'commande-client:web:{reservation.pk}',
            'title': f'Nouvelle commande client : {reservation.reference}',
            'summary': ' · '.join(filter(None, [
                f'{reservation.client.prenom} {reservation.client.nom}',
                str(reservation.montant_total),
                reservation.get_mode_reception_display(),
                reservation.adresse_livraison,
                f'Retrait avant le {reservation.date_expiration:%d/%m/%Y}' if reservation.date_expiration else '',
                reservation.note,
            ])),
            'icon': 'fa-basket-shopping',
            'level': 'info',
            'category': 'commande',
            'url': reverse('admin:ventes_reservation_change', args=[reservation.pk]),
        })

    for message in MessageClient.objects.filter(statut=MessageClient.Statut.NOUVEAU):
        items.append({
            'key': f'message-client:{message.pk}',
            'title': f'Nouveau message client : {message.sujet}',
            'summary': ' · '.join(filter(None, [
                message.nom,
                message.email or message.telephone,
                message.message[:110],
            ])),
            'icon': 'fa-envelope',
            'level': 'info',
            'category': 'message',
            'url': f"{reverse('admin:ventes_messageclient_change', args=[message.pk])}?repondre=1",
            'action_label': 'Répondre',
        })

    now = timezone.now()
    bientot = now + timedelta(days=7)
    promo_url = reverse('admin:promotions_promotion_changelist')
    promotions = Promotion.objects.filter(statut=True).filter(
        Q(date_fin__lt=now) | Q(date_fin__gte=now, date_fin__lte=bientot)
    )
    for promotion in promotions:
        expiree = promotion.date_fin < now
        items.append({
            'key': f"promotion:{'expiree' if expiree else 'bientot-fin'}:{promotion.pk}",
            'title': (
                f'Promotion expirée : {promotion.nom}'
                if expiree else f'Promotion bientôt terminée : {promotion.nom}'
            ),
            'summary': (
                'La période est terminée, mais la promotion est toujours active.'
                if expiree else f'Fin prévue le {timezone.localtime(promotion.date_fin):%d/%m/%Y à %H:%M}.'
            ),
            'icon': 'fa-calendar-xmark' if expiree else 'fa-clock',
            'level': 'danger' if expiree else 'warning',
            'category': 'promotion',
            'url': promo_url,
        })

    return items


def notifications_pour_utilisateur(user):
    """Synchronise l'état personnel et renvoie uniquement les alertes autorisées."""
    all_items = active_notifications()
    all_keys = [item['key'] for item in all_items]
    UserNotification.objects.filter(user=user).exclude(key__in=all_keys).delete()

    permissions = {
        'stock:': ('stocks.view_stock', 'stocks.change_stock'),
        'commande-client:': ('ventes.view_reservation', 'ventes.change_reservation'),
        'message-client:': ('ventes.view_messageclient', 'ventes.change_messageclient'),
        'promotion:': ('promotions.view_promotion', 'promotions.change_promotion'),
    }
    visible = [
        item for item in all_items
        if any(
            user.has_perm(permission)
            for prefix, perms in permissions.items()
            if item['key'].startswith(prefix)
            for permission in perms
        )
    ]
    visible_keys = [item['key'] for item in visible]
    existing = {
        state.key: state
        for state in UserNotification.objects.filter(user=user, key__in=visible_keys)
    }
    UserNotification.objects.bulk_create(
        [
            UserNotification(user=user, key=key)
            for key in visible_keys if key not in existing
        ],
        ignore_conflicts=True,
    )
    states = {
        state.key: state
        for state in UserNotification.objects.filter(user=user, key__in=visible_keys)
    }
    result = []
    for item in visible:
        state = states[item['key']]
        if state.etat == UserNotification.Etat.MASQUEE:
            continue
        result.append({
            **item,
            'etat': state.etat,
            'non_lue': state.etat == UserNotification.Etat.NON_LUE,
        })
    return sorted(
        result,
        key=lambda item: (
            not item['non_lue'],
            {'message': 0, 'commande': 1, 'stock': 2, 'promotion': 3}.get(item['category'], 4),
            item['key'],
        ),
    )
