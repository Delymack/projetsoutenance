"""
Statistiques du tableau de bord.

Regroupe les agrégats métier utilisés :
- par le template d'index de l'admin (templatetag get_dashboard_stats),
- par l'endpoint de rafraîchissement live GET /api/dashboard/apercu/.
"""

import json
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Avg, Count, F, Q, Sum

from apps.ventes.models import LigneVente, Vente
from apps.stocks.models import Stock
from apps.clients.models import Client
from apps.promotions.models import Promotion

# Fenêtre d'historique (jours) utilisée pour la vélocité des ventes.
VELOCITE_JOURS = 30
# Au-delà de cette couverture, un stock n'est plus considéré comme à risque.
SEUIL_COUVERTURE_JOURS = 30

LIBELLES_PAIEMENT = dict(Vente.ModePaiement.choices)
MOIS_COURTS = (
    'Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin',
    'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc',
)


def _proximite_risque(quantite, jours_restants):
    """
    Largeur de la barre de risque, en % : plus le stock est proche de la
    rupture, plus la barre est pleine. Rupture = 100 %, couverture >= au
    seuil = 0 %. Une couverture inconnue (aucune vente sur la période) n'est
    pas un risque mesuré : la barre reste vide.
    """
    if quantite <= 0:
        return 100
    if jours_restants is None:
        return 0
    ecart = 100 * (1 - jours_restants / SEUIL_COUVERTURE_JOURS)
    return max(0, min(100, round(ecart)))


def borne_jour(jour):
    """Renvoie (début, fin) de la journée donnée, en heure locale."""
    debut = jour.replace(hour=0, minute=0, second=0, microsecond=0)
    return debut, debut + timedelta(days=1)


def tendance(actuel, precedent):
    """Variation en % (entier arrondi), ou None si pas de base."""
    if not precedent:
        return None
    return round((actuel - precedent) / precedent * 100)


def objectif_mensuel(ventes_payees, aujourd_hui):
    """
    Objectif CA du mois :
    - SOCIETE.OBJECTIF_MENSUEL si renseigné,
    - sinon objectif « auto » = 2 x CA du mois précédent (si données).
    Renvoie (objectif, est_auto) avec objectif = None si non calculable.
    """
    try:
        objectif = Decimal(getattr(settings, 'SOCIETE', {}).get('objectif_mensuel') or 0)
    except (TypeError, ValueError):
        objectif = Decimal('0')
    est_auto = False
    if not objectif:
        debut_mois = aujourd_hui.replace(day=1)
        mois_precedent_debut = (debut_mois - timedelta(days=1)).replace(day=1)
        ca_precedent = ventes_payees.filter(
            date_vente__gte=mois_precedent_debut, date_vente__lt=debut_mois
        ).aggregate(ca=Sum('total'))['ca'] or 0
        if ca_precedent:
            objectif = ca_precedent * Decimal('2')
            est_auto = True
    return (objectif or None), est_auto


def stats_completes():
    """Toutes les données du tableau de bord (template d'index)."""
    now = timezone_locale()
    aujourd_hui, fin_jour = borne_jour(now)
    hier = aujourd_hui - timedelta(days=1)
    ventes_payees = Vente.objects.filter(statut=Vente.Statut.PAYEE)

    # --- Aujourd'hui vs hier : les KPI portent leur tendance -------------
    ventes_du_jour = ventes_payees.filter(date_vente__gte=aujourd_hui, date_vente__lt=fin_jour)
    ventes_hier = ventes_payees.filter(date_vente__gte=hier, date_vente__lt=aujourd_hui)
    ca_du_jour = ventes_du_jour.aggregate(ca=Sum('total'))['ca'] or 0
    ca_hier = ventes_hier.aggregate(ca=Sum('total'))['ca'] or 0
    panier_moyen = ventes_du_jour.aggregate(moyenne=Avg('total'))['moyenne'] or 0
    nb_ventes_hier = ventes_hier.count()

    # --- Mois en cours : CA et objectif ------------------------------------
    debut_mois = aujourd_hui.replace(day=1)
    fin_mois = (debut_mois + timedelta(days=32)).replace(day=1)
    ventes_mois = ventes_payees.filter(date_vente__gte=debut_mois, date_vente__lt=fin_mois)
    ca_mois = ventes_mois.aggregate(ca=Sum('total'))['ca'] or 0
    produits_vendus_mois = LigneVente.objects.filter(
        vente__in=ventes_mois,
    ).aggregate(total=Sum('quantite'))['total'] or 0
    debut_mois_precedent = (debut_mois - timedelta(days=1)).replace(day=1)
    ca_mois_precedent = ventes_payees.filter(
        date_vente__gte=debut_mois_precedent,
        date_vente__lt=debut_mois,
    ).aggregate(ca=Sum('total'))['ca'] or 0

    ventes_par_mois = []
    premier_mois = debut_mois
    for _ in range(5):
        premier_mois = (premier_mois - timedelta(days=1)).replace(day=1)
    for _ in range(6):
        fin_periode = (premier_mois + timedelta(days=32)).replace(day=1)
        chiffres = ventes_payees.filter(
            date_vente__gte=premier_mois,
            date_vente__lt=fin_periode,
        ).aggregate(ca=Sum('total'))
        ventes_par_mois.append({
            'label': MOIS_COURTS[premier_mois.month - 1],
            'ca': float(chiffres['ca'] or 0),
        })
        premier_mois = fin_periode
    chiffre_max = max((mois['ca'] for mois in ventes_par_mois), default=0)
    for mois in ventes_par_mois:
        mois['hauteur'] = max(round(mois['ca'] / chiffre_max * 100), 4) if chiffre_max else 4

    objectif, _ = objectif_mensuel(ventes_payees, aujourd_hui)
    progression_mois = round(float(ca_mois) / float(objectif) * 100) if objectif else None
    objectif_bar = min(progression_mois, 100) if progression_mois is not None else None
    objectif_atteint = bool(progression_mois is not None and progression_mois >= 100)

    # --- Série 14 jours : CA, ventes et variation jour à jour ------------
    ventes_par_jour = []
    for i in range(13, -1, -1):
        jour = aujourd_hui - timedelta(days=i)
        start, end = borne_jour(jour)
        agg = ventes_payees.filter(date_vente__gte=start, date_vente__lt=end).aggregate(
            total=Sum('total'), nb=Count('id')
        )
        ventes_par_jour.append({
            'label': jour.strftime('%d/%m'),
            'total': float(agg['total'] or 0),
            'nb': agg['nb'],
            'date': jour.date().isoformat(),
        })

    maximum = max((jour['total'] for jour in ventes_par_jour), default=0)
    for jour in ventes_par_jour:
        jour['height'] = round(jour['total'] / maximum * 100) if maximum else 0
        jour['actif'] = jour['date'] == aujourd_hui.date().isoformat()

    # --- Réassort suggéré : vélocité des ventes sur 30 jours -------------
    debut_velocite = aujourd_hui - timedelta(days=VELOCITE_JOURS)
    vendus = dict(
        LigneVente.objects.filter(
            vente__statut=Vente.Statut.PAYEE,
            vente__date_vente__gte=debut_velocite,
        ).values_list('produit_id').annotate(total=Sum('quantite'))
    )
    stocks = Stock.objects.select_related('produit').filter(quantite__lte=F('seuil_alerte')).order_by('quantite')

    a_surveiller = []
    for stock in stocks:
        vendu = vendus.get(stock.produit_id, 0)
        par_jour = vendu / VELOCITE_JOURS
        if par_jour > 0:
            jours_restants = round(stock.quantite / par_jour, 1)
            cible = max(int(round(par_jour * 14)), 6)  # cible 2 semaines
        else:
            jours_restants = None
            cible = 6
        a_surveiller.append({
            'produit': stock.produit,
            'quantite': stock.quantite,
            'seuil': stock.seuil_alerte,
            'vendu_30j': vendu,
            'jours_restants': jours_restants,
            'couverture_pct': _proximite_risque(stock.quantite, jours_restants),
            'a_embouteiller': cible,
            'urgence': 'ru' if stock.quantite <= 0 else (
                'urgent' if jours_restants is not None and jours_restants <= 7 else 'bientot'
            ),
        })
    a_surveiller.sort(key=lambda r: (r['quantite'], -(r['vendu_30j'])))
    a_surveiller = a_surveiller[:6]

    # --- Clients : meilleurs contributeurs et encours à surveiller --------
    # Les prédicats de segment viennent de l'admin Clients : une seule
    # définition, donc le dashboard et la page Clients ne peuvent pas diverger.
    # Import paresseux : apps.clients.admin charge django.contrib.admin.
    from apps.clients.admin import clients_a_risque

    debut_30j = aujourd_hui - timedelta(days=29)
    top_clients = list(
        ventes_payees.filter(date_vente__gte=debut_30j)
        .exclude(client__isnull=True)
        .values('client__id', 'client__nom', 'client__niveau')
        .annotate(ca=Sum('total'), achats=Count('id'))
        .order_by('-ca')[:5]
    )
    ca_clients = sum((c['ca'] or 0) for c in top_clients) or 1
    for ligne in top_clients:
        ligne['part'] = round(float(ligne['ca'] or 0) / float(ca_clients) * 100)

    clients_du_mois = Client.objects.all()
    createurs = list(
        clients_du_mois.filter(solde_du__gt=0)
        .order_by('-solde_du')
        .values('id', 'nom', 'solde_du', 'max_credit')[:5]
    )
    for ligne in createurs:
        plafond = ligne['max_credit'] or 0
        # Sans plafond, le crédit n'est pas plafonné : rien à récupérer.
        ligne['restant'] = max(plafond - ligne['solde_du'], 0) if plafond else None
    encours_total = clients_du_mois.aggregate(
        total=Sum('solde_du'), n=Count('id', filter=Q(solde_du__gt=0))
    )
    a_risque = clients_a_risque(clients_du_mois).count()

    # --- Ventes récentes -----------------------------------------------------
    ventes_recentes = list(
        ventes_payees.select_related('client', 'utilisateur').prefetch_related(
            'lignes__produit',
        ).order_by('-date_vente')[:6]
    )
    for vente in ventes_recentes:
        lignes = list(vente.lignes.all())
        vente.quantite_totale = sum(ligne.quantite for ligne in lignes)

    meilleures_ventes = list(
        LigneVente.objects.filter(
            vente__statut=Vente.Statut.PAYEE,
        ).values(
            'produit_id',
            'produit__nom',
            'produit__prix_vente',
            'produit__image',
        ).annotate(
            total_vendu=Sum('quantite'),
        ).order_by('-total_vendu')[:5]
    )

    ventes_par_appellation = [
        {
            'label': ligne['produit__appellation'] or 'Sans appellation',
            'ca': float(ligne['chiffre_affaires'] or 0),
        }
        for ligne in LigneVente.objects.filter(
            vente__statut=Vente.Statut.PAYEE,
            vente__date_vente__gte=debut_mois,
            vente__date_vente__lt=fin_mois,
        ).values(
            'produit__appellation',
        ).annotate(
            chiffre_affaires=Sum(F('sous_total') - F('remise')),
        ).order_by('-chiffre_affaires')
    ]
    if len(ventes_par_appellation) > 5:
        autres = sum(ligne['ca'] for ligne in ventes_par_appellation[5:])
        ventes_par_appellation = ventes_par_appellation[:5]
        ventes_par_appellation.append({'label': 'Autres', 'ca': autres})
    promotions_actives = list(
        Promotion.objects.filter(
            statut=True,
            date_debut__lte=now,
            date_fin__gte=now,
        ).prefetch_related('produits', 'categories').order_by('date_fin')[:5]
    )
    nombre_promotions_actives = Promotion.objects.filter(
        statut=True,
        date_debut__lte=now,
        date_fin__gte=now,
    ).count()

    # --- Répartition des moyens de paiement (30 j) -------------------------
    paiements_qs = (
        ventes_payees.filter(date_vente__gte=debut_30j)
        .values('mode_paiement')
        .annotate(montant=Sum('total'))
        .order_by('-montant')
    )
    paiements_30j = [{'code': p['mode_paiement'], 'montant': float(p['montant'])} for p in paiements_qs]
    total_paiements = sum(p['montant'] for p in paiements_30j) or 1
    for p in paiements_30j:
        p['part'] = round(p['montant'] / total_paiements * 100, 1)
        p['mode'] = str(LIBELLES_PAIEMENT.get(p['code'], p['code']))

    return {
        'ca_du_jour': ca_du_jour,
        'ca_hier': ca_hier,
        'tendance_ca': tendance(float(ca_du_jour), float(ca_hier)),
        'ventes_du_jour': ventes_du_jour.count(),
        'ventes_hier': nb_ventes_hier,
        'tendance_ventes': tendance(ventes_du_jour.count(), nb_ventes_hier),
        'panier_moyen': panier_moyen,
        'ruptures': stocks.filter(quantite__lte=0).count(),
        'ventes_recentes': ventes_recentes,
        'ventes_par_jour_json': json.dumps([
            {'label': jour['label'], 'date': jour['date'], 'total': jour['total'], 'nb': jour['nb']}
            for jour in ventes_par_jour
        ], ensure_ascii=False),
        'reassort': a_surveiller,
        'top_clients': top_clients,
        'createurs': createurs,
        'encours_total': encours_total['total'] or 0,
        'nb_createurs': encours_total['n'],
        'nb_clients_a_risque': a_risque,
        'ca_mois': ca_mois,
        'tendance_ca_mois': tendance(float(ca_mois), float(ca_mois_precedent)),
        'nombre_clients': Client.objects.count(),
        'produits_vendus_mois': produits_vendus_mois,
        'nombre_promotions_actives': nombre_promotions_actives,
        'promotions_actives': promotions_actives,
        'meilleures_ventes': meilleures_ventes,
        'ventes_par_mois': ventes_par_mois,
        'ventes_par_appellation': ventes_par_appellation,
        'objectif_mensuel': objectif,
        'objectif_progression': progression_mois,
        'objectif_bar': objectif_bar,
        'objectif_atteint': objectif_atteint,
        'paiements_30j_json': json.dumps(paiements_30j, ensure_ascii=False),
    }


def timezone_locale(valeur=None):
    """Heure locale (avec fuseau) — centralise l'import timezone."""
    from django.utils import timezone
    return timezone.localtime(valeur)


def apercu():
    """
    Données « temps réel » pour le rafraîchissement du tableau de bord
    (GET /api/dashboard/apercu/). Légère et rapide.
    """
    from django.utils import timezone

    now = timezone.localtime()
    aujourd_hui, fin_jour = borne_jour(now)
    hier = aujourd_hui - timedelta(days=1)
    ventes_payees = Vente.objects.filter(statut=Vente.Statut.PAYEE)

    vd = ventes_payees.filter(date_vente__gte=aujourd_hui, date_vente__lt=fin_jour)
    vh = ventes_payees.filter(date_vente__gte=hier, date_vente__lt=aujourd_hui)
    ca_du_jour = vd.aggregate(ca=Sum('total'))['ca'] or 0
    ca_hier = vh.aggregate(ca=Sum('total'))['ca'] or 0
    panier_moyen = vd.aggregate(moyenne=Avg('total'))['moyenne'] or 0
    nb_ventes_hier = vh.count()
    nb_ventes = vd.count()

    debut_30j = aujourd_hui - timedelta(days=29)
    paiements = list(
        ventes_payees.filter(date_vente__gte=debut_30j)
        .values('mode_paiement')
        .annotate(montant=Sum('total'))
        .order_by('-montant')
    )
    total_paiements = sum((p['montant'] for p in paiements), Decimal('0.00')) or 1
    paiements_30j = [
        {
            'code': p['mode_paiement'],
            'mode': str(LIBELLES_PAIEMENT.get(p['mode_paiement'], p['mode_paiement'])),
            'montant': float(p['montant']),
            'part': round(float(p['montant']) / float(total_paiements) * 100, 1),
        }
        for p in paiements
    ]

    debut_mois = aujourd_hui.replace(day=1)
    fin_mois = (debut_mois + timedelta(days=32)).replace(day=1)
    ca_mois = ventes_payees.filter(date_vente__gte=debut_mois, date_vente__lt=fin_mois).aggregate(
        ca=Sum('total')
    )['ca'] or 0
    objectif, est_auto = objectif_mensuel(ventes_payees, aujourd_hui)
    jours_mois = (fin_mois - debut_mois).days
    progression = round(float(ca_mois) / float(objectif) * 100) if objectif else None

    jours_ecoules = aujourd_hui.day
    projection_mois = (ca_mois / Decimal(jours_ecoules)) * Decimal(jours_mois) if jours_ecoules else 0

    return {
        'ca_du_jour': ca_du_jour,
        'ca_hier': ca_hier,
        'tendance_ca': tendance(float(ca_du_jour), float(ca_hier)),
        'ventes_du_jour': nb_ventes,
        'ventes_hier': nb_ventes_hier,
        'tendance_ventes': tendance(nb_ventes, nb_ventes_hier),
        'panier_moyen': panier_moyen,
        'ruptures': Stock.objects.filter(quantite__lte=0).count(),
        'ca_mois': ca_mois,
        'objectif_mensuel': objectif,
        'objectif_auto': est_auto,
        'objectif_progression': progression,
        'jours_restants': jours_mois - aujourd_hui.day + 1,
        'projection_mois': projection_mois,
        'paiements_30j': paiements_30j,
    }