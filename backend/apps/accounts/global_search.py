"""Recherche globale — parcourt les principaux modèles commerciaux.

Montée sous /admin/recherche/ (JSON), consommée par le champ de recherche
de la barre supérieure. Accessible aux membres du personnel uniquement.
"""
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse


def _entrees(queryset, champ_titre, champ_sous=None, url_base=None, champ_lien='pk', maxi=6):
    """Construit la liste d'entrées {titre, sous, url} à partir d'un queryset."""
    entrees = []
    for obj in queryset[:maxi]:
        titre = getattr(obj, champ_titre)
        if callable(titre):
            titre = titre()
        val_sous = ''
        if champ_sous:
            val_sous = getattr(obj, champ_sous, '')
            val_sous = val_sous() if callable(val_sous) else val_sous
        entrees.append({
            'titre': str(titre) if titre else '(sans nom)',
            'sous': str(val_sous) if val_sous else '',
            'url': reverse(url_base, args=[getattr(obj, champ_lien)]) if url_base else '',
        })
    return entrees


@staff_member_required
def recherche_globale_view(request):
    q = (request.GET.get('q') or '').strip()
    groupes = []
    if len(q) >= 2:
        from apps.produits.models import Produit
        from apps.clients.models import Client
        from apps.ventes.models import Vente

        produits = Produit.objects.filter(
            Q(nom__icontains=q) | Q(marque__icontains=q) | Q(appellation__icontains=q)
            | Q(cepage__icontains=q) | Q(categorie__nom__icontains=q)
        ).select_related('categorie')
        if produits.exists():
            groupes.append({
                'groupe': 'Produits',
                'icone': 'fas fa-wine-bottle',
                'items': _entrees(produits, 'nom', 'categorie', 'admin:produits_produit_change'),
            })

        clients = Client.objects.filter(
            Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(telephone__icontains=q)
        )
        if clients.exists():
            groupes.append({
                'groupe': 'Clients',
                'icone': 'fas fa-address-card',
                'items': _entrees(clients, '__str__', 'telephone', 'admin:clients_client_change'),
            })

        ventes = Vente.objects.filter(
            Q(reference__icontains=q) | Q(client__nom__icontains=q) | Q(client__prenom__icontains=q)
        ).select_related('client')
        if ventes.exists():
            groupes.append({
                'groupe': 'Ventes',
                'icone': 'fas fa-receipt',
                'items': _entrees(ventes, 'reference', 'client', 'admin:ventes_vente_change'),
            })

    return JsonResponse({'q': q, 'groupes': groupes})
