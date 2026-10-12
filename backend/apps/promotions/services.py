"""Moteur des promotions : conditions d'application, remise et statistiques.

Point d'entrée unique de la règle « promotion applicable » (statut, fenêtre de
dates, créneau happy hour, quantité minimale, type de client, code promo) et du
calcul de la remise, utilisés par la vente, l'API, les filtres, l'admin et les
statistiques, afin d'éviter toute divergence entre les modules.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone


def promotions_actives_q():
    """Critère commun « promotion active » (statut + fenêtre de dates).

    Hors périmètre de la vente (happy hour, quantité, type de client, code) :
    ces conditions dépendent du contexte de la ligne et sont évaluées par
    :func:`promotion_applicable`.
    """
    now = timezone.now()
    return Q(
        statut=True,
        date_debut__lte=now,
        date_fin__gte=now,
    )


def promotions_actives_qs():
    """QuerySet des promotions actuellement actives (tri stable par id)."""
    from apps.promotions.models import Promotion
    return Promotion.objects.filter(promotions_actives_q()).order_by('id')


# ---------------------------------------------------------------------------
# Conditions d'application
# ---------------------------------------------------------------------------

def happy_hour_active(promo, moment=None):
    """
    Vrai si le créneau happy hour est ouvert à l'instant ``moment`` (heure
    locale par défaut). Sans créneau configuré, la promotion est toujours
    eligible. Un créneau nocturne (22:00 → 02:00) est géré via la comparaison
    heure_debut > heure_fin.
    """
    if not promo.a_un_creneau:
        return True
    moment = moment or timezone.localtime()
    heure = moment.time().replace(second=0, microsecond=0)
    if promo.jours_semaine_liste and str(moment.isoweekday()) not in promo.jours_semaine_liste:
        return False
    if promo.heure_debut <= promo.heure_fin:
        return promo.heure_debut <= heure <= promo.heure_fin
    # Créneau à cheval sur minuit.
    return heure >= promo.heure_debut or heure <= promo.heure_fin


def code_valide(promo, code=None):
    """
    Une promotion avec code n'est appliquée que si ce code est saisi à la
    caisse. La comparaison ignore la casse et les espaces.
    """
    if not promo.code:
        return True
    if not code:
        return False
    return str(code).strip().upper() == promo.code


def limite_atteinte(promo):
    """Vrai si le quota d'utilisations de la promotion est épuisé."""
    if promo.limite_utilisation is None:
        return False
    return promo.nb_utilisations >= promo.limite_utilisation


def promotion_applicable(promo, quantite=1, type_client=None, code=None):
    """
    Vérifie toutes les conditions non tarifaires d'une promotion pour une ligne
    de vente : fenêtre de dates, créneau happy hour, quantité minimale, segment
    de client, code saisi et quota d'utilisations.
    """
    if not promo.est_active:
        return False
    if not happy_hour_active(promo):
        return False
    if quantite < promo.quantite_min:
        return False
    if promo.type_cible != promo.TypeCible.TOUS:
        # Ciblage strict : sans fiche client (vente anonyme), une promotion
        # segmentée ne peut pas s'appliquer — on ne devine pas le segment.
        if not type_client or promo.type_cible != type_client:
            return False
    if not code_valide(promo, code):
        return False
    if limite_atteinte(promo):
        return False
    return True


def promotions_candidat_qs(produit, type_client=None, code=None, quantite=1):
    """
    Promotions actives ciblant ``produit``, soit explicitement, soit via une de
    ses catégories. Les conditions dépendantes du contexte (type de client,
    code, quantité) sont filtrées en Python par :func:`meilleure_promotion`.
    """
    critere = Q(produits=produit)
    # Un produit sans catégorie ne doit pas hériter des promotions « par
    # catégorie » : `categories=None` se traduirait en « promotions sans
    # catégorie ». Le critère n'est donc posé que si la catégorie existe.
    if produit.categorie_id:
        critere |= Q(categories=produit.categorie)
    return promotions_actives_qs().filter(critere).distinct()


# ---------------------------------------------------------------------------
# Calcul de la remise
# ---------------------------------------------------------------------------

def remise_promotion(promo, prix_unitaire, quantite=1):
    """
    Remise totale accordée par la promotion sur une ligne de ``quantite``
    unités à ``prix_unitaire``. La remise ne peut jamais dépasser le montant
    brut de la ligne.
    """
    prix_unitaire = Decimal(prix_unitaire)
    quantite = max(int(quantite or 1), 1)
    brut = prix_unitaire * quantite

    if promo.type_promotion == promo.TypePromotion.MONTANT_FIXE:
        remise = Decimal(promo.valeur) * quantite
    elif promo.type_promotion == promo.TypePromotion.PRIX_PROMO:
        cible = Decimal(promo.prix_promotionnel or 0)
        remise = max(prix_unitaire - cible, Decimal('0')) * quantite
    elif promo.type_promotion == promo.TypePromotion.LOT:
        # Lots complets atteignables : floor(qté / (achetées + offertes)).
        pas = max(int(promo.quantite_achetee) + int(promo.quantite_offerte), 1)
        lots = quantite // pas
        remise = prix_unitaire * lots * int(promo.quantite_offerte)
    else:  # POURCENTAGE
        remise = (brut * Decimal(promo.valeur)) / 100

    return min(max(remise, Decimal('0')), brut)


def lots_atteints(promo, quantite):
    """Nombre de lots complets obtenus pour ``quantite`` (type LOT)."""
    pas = max(int(promo.quantite_achetee) + int(promo.quantite_offerte), 1)
    return max(int(quantite or 0), 0) // pas


def prix_avec_promotion(promo, prix_unitaire, quantite=1):
    """Prix final de la ligne après application de la remise."""
    return Decimal(prix_unitaire) * quantite - remise_promotion(promo, prix_unitaire, quantite)


def meilleure_promotion(produit, prix_unitaire, quantite=1, type_client=None, code=None, promos=None):
    """
    Retourne ``(promotion, remise)`` la plus avantageuse parmi les promotions
    applicables au produit pour la ligne décrite. ``promos`` est un itérable de
    Promotion déjà filtré (prefetch, requête ciblée…) ; s'il vaut None, les
    promotions actives ciblant le produit sont chargées ici.

    Le départage se fait sur la remise obtenue, puis sur la ``priorite``, puis
    sur l'identifiant (ordre de saisie) pour rester déterministe.
    """
    if promos is None:
        promos = promotions_candidat_qs(produit, type_client=type_client, code=code, quantite=quantite)
    meilleure = None
    meilleure_remise = Decimal('0')
    for promo in promos:
        if not promotion_applicable(promo, quantite=quantite, type_client=type_client, code=code):
            continue
        remise = remise_promotion(promo, prix_unitaire, quantite)
        if remise > meilleure_remise:
            meilleure_remise = remise
            meilleure = promo
        elif remise == meilleure_remise and meilleure is not None and remise > 0:
            if (promo.priorite, promo.id) > (meilleure.priorite, meilleure.id):
                meilleure = promo
    return meilleure, meilleure_remise


def produits_cibles(promotion):
    """
    Queryset des produits visés par une promotion : sélection explicite
    enrichie de tous les vins des catégories ciblées.
    """
    from apps.produits.models import Produit
    produits = Produit.objects.filter(pk__in=promotion.produits.values('pk'))
    if promotion.categories.exists():
        produits = produits | Produit.objects.filter(categorie__in=promotion.categories.all())
    return produits.distinct()


def verifier_code(code, type_client=None, produits=None):
    """
    Contrôle un code promo saisi à la caisse.

    Retourne un dictionnaire ``{'valide': bool, 'promotion': Promotion|None,
    'message': str}`` : la promotion concernée, ou la raison du refus
    (inconnu, expirée, hors créneau, quota épuisé, mauvais segment client).
    """
    from apps.promotions.models import Promotion
    resultat = {'valide': False, 'promotion': None, 'message': ''}
    if not code or not str(code).strip():
        resultat['message'] = 'Aucun code promo saisi.'
        return resultat

    code = str(code).strip().upper()
    try:
        promo = Promotion.objects.prefetch_related('categories').get(code=code)
    except Promotion.DoesNotExist:
        resultat['message'] = f'Code promo « {code} » inconnu.'
        return resultat

    resultat['promotion'] = promo
    if not promo.statut:
        resultat['message'] = 'Cette promotion est désactivée.'
        return resultat
    now = timezone.now()
    if promo.date_debut > now:
        resultat['message'] = f'Code valide à partir du {promo.date_debut:%d/%m/%Y %H:%M}.'
        return resultat
    if promo.date_fin < now:
        resultat['message'] = f'Code expiré le {promo.date_fin:%d/%m/%Y %H:%M}.'
        return resultat
    if not happy_hour_active(promo):
        resultat['message'] = f'Code applicable uniquement de {promo.creneau_texte}.'
        return resultat
    if promo.type_cible != promo.TypeCible.TOUS and promo.type_cible != type_client:
        # Pas de fiche client = vente anonyme : le code segmenté ne s'applique pas.
        libelle = promo.get_type_cible_display() if type_client else 'clients identifiés'
        resultat['message'] = f'Code réservé au segment « {libelle} ».'
        return resultat
    if limite_atteinte(promo):
        resultat['message'] = 'Code épuisé : quota d\'utilisations atteint.'
        return resultat

    resultat['valide'] = True
    resultat['message'] = f'Code « {code} » accepté : {promo.regle_texte} sur {promo.nom}.'
    return resultat


# ---------------------------------------------------------------------------
# Statistiques et historique
# ---------------------------------------------------------------------------

def _lignes_avec_remise(jours=None, promos=None):
    """Lignes de vente payées ayant bénéficié d'une remise promotionnelle."""
    from apps.ventes.models import LigneVente, Vente
    qs = LigneVente.objects.filter(
        vente__statut=Vente.Statut.PAYEE,
        remise__gt=0,
        promotion__isnull=False,
    )
    if jours:
        qs = qs.filter(vente__date_vente__gte=timezone.now() - timedelta(days=jours))
    if promos is not None:
        qs = qs.filter(promotion__in=promos)
    return qs


def impact_promotions(jours=30):
    """
    KPIs d'impact des promotions sur les ``jours`` derniers jours :
    - Remises accordées
    - Nombre de ventes avec promotion
    - Taux d'utilisation (% des ventes payées avec promotion)
    - Impact sur le Chiffre d'Affaires :
      * CA total des ventes avec promotion
      * CA net des lignes promotionnées
      * CA brut avant remise
      * CA global de la boutique
      * Part du CA généré sous promotion
      * Panier moyen avec promotion
    """
    from apps.ventes.models import Vente
    depuis = timezone.now() - timedelta(days=jours) if jours else None
    lignes_promo = _lignes_avec_remise(jours=jours)
    
    aggs = lignes_promo.aggregate(
        total_remise=Sum('remise'),
        ca_lignes=Sum('sous_total'),
    )
    remises_accordees = aggs['total_remise'] or Decimal('0.00')
    ca_lignes_promo = aggs['ca_lignes'] or Decimal('0.00')
    ca_brut_lignes = ca_lignes_promo + remises_accordees

    ventes_promo_ids = list(lignes_promo.values_list('vente_id', flat=True).distinct())
    ventes_promo = len(ventes_promo_ids)

    ventes_qs = Vente.objects.filter(statut=Vente.Statut.PAYEE)
    if depuis:
        ventes_qs = ventes_qs.filter(date_vente__gte=depuis)

    nb_ventes = ventes_qs.count()
    ca_total_global = ventes_qs.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
    
    # CA des ventes comportant au moins une promo
    ca_ventes_promo = Vente.objects.filter(id__in=ventes_promo_ids).aggregate(total=Sum('total'))['total'] or Decimal('0.00')

    taux = round(ventes_promo / nb_ventes * 100) if nb_ventes else 0
    taux_ca = round(float(ca_ventes_promo / ca_total_global * 100), 1) if ca_total_global else 0.0
    panier_moyen = (ca_ventes_promo / Decimal(ventes_promo)) if ventes_promo else Decimal('0.00')

    return {
        'remises_30j': remises_accordees,
        'ventes_promo_30j': ventes_promo,
        'nb_ventes_30j': nb_ventes,
        'taux_promo_30j': taux,
        # Impact direct sur le Chiffre d'Affaires
        'ca_promo_30j': ca_ventes_promo,
        'ca_lignes_promo_30j': ca_lignes_promo,
        'ca_brut_promo_30j': ca_brut_lignes,
        'ca_total_30j': ca_total_global,
        'taux_ca_promo_30j': taux_ca,
        'panier_moyen_promo_30j': panier_moyen,
    }


def top_promos_impact(limit=5, jours=None):
    """Classement des promotions par remise réellement accordée (+ nb ventes et CA généré)."""
    qs = (
        _lignes_avec_remise(jours=jours)
        .values('promotion_id', 'promotion__nom', 'promotion__type_promotion')
        .annotate(
            remise=Sum('remise'),
            ca=Sum('sous_total'),
            nb_ventes=Count('vente', distinct=True)
        )
        .order_by('-remise')[:limit]
    )
    return list(qs)


def repartition_par_type(jours=None):
    """Répartition des lignes remisées par mécanique de réduction."""
    from apps.promotions.models import Promotion
    qs = _lignes_avec_remise(jours=jours)
    par_type = {
        ligne['promotion__type_promotion']: ligne
        for ligne in qs.values('promotion__type_promotion')
        .annotate(nb=Count('id'), remise=Sum('remise'))
    }
    resultat = []
    for valeur, libelle in Promotion.TypePromotion.choices:
        ligne = par_type.get(valeur) or {'nb': 0, 'remise': Decimal('0')}
        resultat.append({
            'type': valeur,
            'libelle': libelle,
            'nb_lignes': ligne['nb'],
            'remise': ligne['remise'] or Decimal('0'),
        })
    return resultat


def repartition_par_cible(jours=None):
    """Répartition des lignes remisées par segment de client ciblé."""
    from apps.promotions.models import Promotion
    qs = _lignes_avec_remise(jours=jours)
    par_cible = {
        ligne['promotion__type_cible']: ligne
        for ligne in qs.values('promotion__type_cible')
        .annotate(nb=Count('id'), remise=Sum('remise'))
    }
    resultat = []
    for valeur, libelle in Promotion.TypeCible.choices:
        ligne = par_cible.get(valeur) or {'nb': 0, 'remise': Decimal('0')}
        resultat.append({
            'type_cible': valeur,
            'libelle': libelle,
            'nb_lignes': ligne['nb'],
            'remise': ligne['remise'] or Decimal('0'),
        })
    return resultat


def historique_promotion(promotion, limite=20):
    """Dernières ventes ayant appliqué la promotion (lecture seule)."""
    from apps.ventes.models import LigneVente, Vente
    return list(
        LigneVente.objects.filter(promotion=promotion, vente__statut=Vente.Statut.PAYEE)
        .select_related('vente', 'vente__client', 'produit')
        .order_by('-vente__date_vente')[:limite]
    )


def statistiques_promotion(promotion, jours=None):
    """
    Synthèse chiffrée d'une promotion : ventes réalisées, articles vendus,
    remise totale, chiffre d'affaires encaissé et panier moyen.
    """
    from django.db.models import DecimalField, F, IntegerField
    from django.db.models.functions import Coalesce

    qs = _lignes_avec_remise(jours=jours, promos=[promotion])
    decimal_sortie = DecimalField(max_digits=14, decimal_places=2)
    aggs = qs.aggregate(
        nb_lignes=Count('id'),
        articles=Coalesce(Sum('quantite'), 0, output_field=IntegerField()),
        remise=Coalesce(Sum('remise'), 0, output_field=decimal_sortie),
        ca=Coalesce(Sum('sous_total'), 0, output_field=decimal_sortie),
        # Montant facturé avant remise : prix unitaire x quantité.
        brut=Coalesce(Sum(F('prix_unitaire') * F('quantite')), 0, output_field=decimal_sortie),
    )
    nb_ventes = qs.values('vente_id').distinct().count()
    remise_totale = aggs['remise']
    return {
        'nb_ventes': nb_ventes,
        'nb_lignes': aggs['nb_lignes'],
        'articles': aggs['articles'],
        'remise_totale': remise_totale,
        'ca': aggs['ca'],
        'panier_moyen': (aggs['ca'] / nb_ventes) if nb_ventes else Decimal('0.00'),
        'taux_remise': round(remise_totale / aggs['brut'] * 100, 1) if aggs['brut'] else 0,
    }


def promotions_avant_expiration(jours=7, limite=5):
    """Promotions actives dont l'échéance approche (relance à prévoir)."""
    now = timezone.now()
    return list(
        Promotion_queryset_actif()
        .filter(date_fin__lte=now + timedelta(days=jours))
        .order_by('date_fin')[:limite]
    )


def Promotion_queryset_actif():
    """Promotions actives, catégorie et produits préchargés."""
    from apps.promotions.models import Promotion
    return (
        Promotion.objects.filter(promotions_actives_q())
        .prefetch_related('categories', 'produits')
    )


def chevauchements(produits, date_debut, date_fin, type_promotion, valeur, prix_promotionnel=None,
                   quantite_achetee=2, quantite_offerte=1, exclure_id=None):
    """
    Promotions en conflit avec une nouvelle (ou modifiée) : même période
    (``date_debut`` → ``date_fin``) et au moins un produit commun.

    Pour chaque produit partagé, on compare la remise de la promotion en
    cours par rapport à celle déjà en place : ``nb_ecrases`` correspond aux
    produits où la promotion existante reste plus avantageuse (la nouvelle
    serait ignorée à la vente). ``exclure_id`` permet d'ignorer la promotion
    en cours d'édition.
    """
    from apps.promotions.models import Promotion, PromotionProduit
    if not produits or not date_debut or not date_fin:
        return []

    conflits = Promotion.objects.filter(
        statut=True,
        date_debut__lte=date_fin,
        date_fin__gte=date_debut,
    )
    if exclure_id:
        conflits = conflits.exclude(id=exclure_id)
    conflits = conflits.filter(produits__in=produits).distinct()

    resultats = []
    for promo in conflits:
        produits_communs = list(
            PromotionProduit.objects.filter(promotion=promo, produit__in=produits)
            .select_related('produit')
        )
        ecrases = []
        gagnes = []
        for pp in produits_communs:
            produit = pp.produit
            prix = produit.prix_vente
            self_remise = _remise_simulee(
                type_promotion, prix, 1, valeur,
                prix_promotionnel, quantite_achetee, quantite_offerte,
            )
            other_remise = remise_promotion(promo, prix, 1)
            if other_remise > self_remise:
                ecrases.append(produit.nom)
            else:
                gagnes.append(produit.nom)
        resultats.append({
            'id': promo.id,
            'nom': promo.nom,
            'type_promotion': promo.type_promotion,
            'valeur': promo.valeur,
            'regle_texte': promo.regle_texte,
            'date_debut': promo.date_debut,
            'date_fin': promo.date_fin,
            'nb_communs': len(produits_communs),
            'nb_ecrases': len(ecrases),
            'produits_ecrases': ecrases,
            'nb_gagnes': len(gagnes),
        })
    return sorted(resultats, key=lambda r: -r['nb_ecrases'])


def _remise_simulee(type_promotion, prix, quantite, valeur, prix_promotionnel, quantite_achetee,
                    quantite_offerte):
    """Remise d'une promotion *non enregistrée*, pour l'aperçu de chevauchement."""
    from apps.promotions.models import Promotion
    brut = prix * quantite
    if type_promotion == Promotion.TypePromotion.MONTANT_FIXE:
        remise = Decimal(str(valeur or 0)) * quantite
    elif type_promotion == Promotion.TypePromotion.PRIX_PROMO:
        cible = Decimal(str(prix_promotionnel or 0))
        remise = max(prix - cible, Decimal('0')) * quantite
    elif type_promotion == Promotion.TypePromotion.LOT:
        pas = max(int(quantite_achetee or 0) + int(quantite_offerte or 0), 1)
        remise = prix * (quantite // pas) * int(quantite_offerte or 0)
    else:
        remise = (brut * Decimal(str(valeur or 0))) / 100
    return min(max(remise, Decimal('0')), brut)


def calculer_apercu_prix(promo, produit, quantite=1, type_client=None, code=None):
    """
    Simule l'application d'une promotion sur un produit avec tous les détails :
    prix unitaire de base, quantité, brut, remise unitaire/totale, net unitaire/total,
    éligibilité détaillée et motifs clairs si inéligible.
    """
    quantite = max(int(quantite or 1), 1)
    prix_unitaire = Decimal(str(produit.prix_vente or 0))
    total_brut = prix_unitaire * quantite

    ineligible_reasons = []
    if not promo.statut:
        ineligible_reasons.append("Promotion désactivée")
    now = timezone.now()
    if promo.date_debut and promo.date_debut > now:
        ineligible_reasons.append(f"Non commencée (débute le {promo.date_debut.strftime('%d/%m/%Y %H:%M')})")
    if promo.date_fin and promo.date_fin < now:
        ineligible_reasons.append(f"Expirée depuis le {promo.date_fin.strftime('%d/%m/%Y %H:%M')}")
    if not happy_hour_active(promo):
        ineligible_reasons.append(f"Hors créneau Happy Hour ({promo.creneau_texte or 'créneau restreint'})")
    if quantite < promo.quantite_min:
        ineligible_reasons.append(f"Quantité minimale requise non atteinte ({promo.quantite_min} requis, {quantite} simulé)")
    if promo.type_cible != promo.TypeCible.TOUS:
        if not type_client or promo.type_cible != type_client:
            ineligible_reasons.append(f"Réservée au segment client « {promo.get_type_cible_display()} »")
    if promo.code and not code_valide(promo, code):
        ineligible_reasons.append(f"Code promo « {promo.code} » obligatoire ou incorrect")
    if limite_atteinte(promo):
        ineligible_reasons.append("Quota maximal d'utilisations atteint")

    # Périmètre ciblé
    produits_promo_ids = set(promo.produits.values_list('id', flat=True))
    categories_promo_ids = set(promo.categories.values_list('id', flat=True))
    cible_specifique = bool(produits_promo_ids or categories_promo_ids)
    if cible_specifique:
        est_cible = (produit.id in produits_promo_ids) or (produit.categorie_id in categories_promo_ids)
        if not est_cible:
            ineligible_reasons.append("Ce vin n'appartient pas au périmètre ciblé de cette promotion")

    eligible = (len(ineligible_reasons) == 0)
    remise_totale = remise_promotion(promo, prix_unitaire, quantite) if eligible else Decimal('0.00')
    total_net = max(total_brut - remise_totale, Decimal('0.00'))
    prix_unitaire_final = (total_net / Decimal(quantite)) if quantite else prix_unitaire
    pct_remise = round(float((remise_totale / total_brut) * 100), 1) if total_brut > 0 else 0.0

    return {
        'eligible': eligible,
        'motifs_ineligibilite': ineligible_reasons,
        'motif': ineligible_reasons[0] if ineligible_reasons else '',
        'produit_id': produit.id,
        'produit_nom': produit.nom,
        'quantite': quantite,
        'prix_unitaire_base': prix_unitaire,
        'total_brut': total_brut,
        'remise_totale': remise_totale,
        'remise_unitaire': (remise_totale / Decimal(quantite)) if quantite else Decimal('0.00'),
        'total_net': total_net,
        'prix_unitaire_final': prix_unitaire_final,
        'pourcentage_remise': pct_remise,
        'regle_texte': promo.regle_texte,
        'type_promotion': promo.type_promotion,
    }
