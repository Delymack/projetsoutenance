from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import (
    Avg, Case, Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value, When,
)
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek, TruncYear
from django.contrib import admin
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer

from apps.produits.models import Produit
from apps.clients.models import Client
from apps.ventes.models import Vente, LigneVente
from apps.stocks.models import Stock, MouvementStock
from apps.stocks.valorisation import cout_unitaire_expression
from apps.promotions.models import Promotion
from apps.promotions.services import promotions_actives_q
from apps.ventes.serializers import VenteSerializer
from apps.accounts.permissions import IsAdmin
from config.renderers import CSVRenderer, PDFRenderer, XLSXRenderer

from apps.dashboard.stats import apercu


def _format_montant(montant):
    return f"{Decimal(montant or 0):.2f}"


class ApercuView(APIView):
    """
    GET /api/dashboard/apercu/

    Données légères pour le rafraîchissement « live » du tableau de bord :
    KPI du jour avec tendance, objectif mensuel, moyens de paiement (30 j)
    et crédits clients.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(apercu())


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()

        # Statistiques globales
        total_produits = Produit.objects.count()
        total_clients = Client.objects.count()
        
        ventes_payees = Vente.objects.filter(statut=Vente.Statut.PAYEE)
        total_ventes = ventes_payees.count()
        chiffre_affaires = ventes_payees.aggregate(total=Sum('total'))['total'] or 0

        # Stocks
        stock_faible = Stock.objects.filter(quantite__lte=F('seuil_alerte'), quantite__gt=0).count()
        rupture = Stock.objects.filter(quantite__lte=0).count()

        # Ventes récentes (les 5 dernières)
        ventes_recentes_qs = Vente.objects.select_related('client').order_by('-date_vente')[:5]
        
        # Pour les ventes récentes, on peut utiliser le serializer pour avoir un format propre
        ventes_recentes = []
        for v in ventes_recentes_qs:
            ventes_recentes.append({
                "reference": v.reference,
                "client": v.nom_client,
                "total": v.total,
                "date": v.date_vente,
                "statut": v.statut
            })

        # Meilleures ventes (Top 5 produits les plus vendus)
        meilleures_ventes_qs = LigneVente.objects.filter(
            vente__statut=Vente.Statut.PAYEE
        ).values(
            'produit__id', 'produit__nom'
        ).annotate(
            total_vendu=Sum('quantite')
        ).order_by('-total_vendu')[:5]

        # Promotions actives
        promotions_actives = Promotion.objects.filter(promotions_actives_q()).count()

        # Mouvements de stock récents
        mouvements_recents_qs = MouvementStock.objects.select_related('produit').order_by('-date_mouvement')[:5]
        mouvements_recents = []
        for m in mouvements_recents_qs:
            mouvements_recents.append({
                "produit": m.produit.nom,
                "quantite": m.quantite,
                "type": m.get_type_mouvement_display(),
                "date": m.date_mouvement,
                "ref": m.reference_id
            })

        return Response({
            "total_produits": total_produits,
            "total_clients": total_clients,
            "total_ventes": total_ventes,
            "chiffre_affaires": chiffre_affaires,
            "stock_faible": stock_faible,
            "produits_rupture": rupture,
            "promotions_actives": promotions_actives,
            "ventes_recentes": ventes_recentes,
            "meilleures_ventes": list(meilleures_ventes_qs),
            "mouvements_recents": mouvements_recents
        })


class VentesParJourView(APIView):
    """
    GET /api/dashboard/ventes-par-jour/

    Série temporelle du chiffre d'affaires et du nombre de ventes par jour,
    sur les N derniers jours (par défaut 30, max 366).

    Paramètres de requête :
    - jours (int, défaut 30)  : taille de la fenêtre glissante
    - debut / fin (AAAA-MM-JJ): bornes explicites, prioritaires sur "jours"

    Les jours sans vente sont remplis à zéro pour un tracé de graphique sans trous.
    Seules les ventes PAYEES sont comptabilisées.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.localtime()
        today = now.date()

        # 1. Déterminer la fenêtre temporelle
        debut_param = request.query_params.get('debut')
        fin_param = request.query_params.get('fin')

        if debut_param and fin_param:
            try:
                debut = datetime.strptime(debut_param, '%Y-%m-%d').date()
                fin = datetime.strptime(fin_param, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {"erreur": "Format de date invalide. Utilisez AAAA-MM-JJ."},
                    status=400,
                )
            if debut > fin:
                return Response(
                    {"erreur": "La date de début doit être antérieure ou égale à la date de fin."},
                    status=400,
                )
            if (fin - debut).days > 366:
                return Response(
                    {"erreur": "La période ne peut pas dépasser 366 jours."},
                    status=400,
                )
        else:
            try:
                nb_jours = int(request.query_params.get('jours', 30))
            except (TypeError, ValueError):
                return Response(
                    {"erreur": "Le paramètre 'jours' doit être un entier."},
                    status=400,
                )
            if nb_jours < 1 or nb_jours > 366:
                return Response(
                    {"erreur": "Le paramètre 'jours' doit être compris entre 1 et 366."},
                    status=400,
                )
            fin = today
            debut = fin - timedelta(days=nb_jours - 1)

        # 2. Agrégation SQL des ventes payées, groupées par jour (heure locale)
        debut_dt = timezone.make_aware(datetime.combine(debut, datetime.min.time()))
        fin_dt = timezone.make_aware(datetime.combine(fin + timedelta(days=1), datetime.min.time()))

        stats = (
            Vente.objects.filter(
                statut=Vente.Statut.PAYEE,
                date_vente__gte=debut_dt,
                date_vente__lt=fin_dt,
            )
            .annotate(jour=TruncDate('date_vente'))
            .values('jour')
            .annotate(nb_ventes=Count('id'), chiffre_affaires=Sum('total'))
            .order_by('jour')
        )

        stats_par_jour = {s['jour']: s for s in stats}

        # 3. Remplissage des jours sans vente (zéro) pour un graphique continu
        resultats = []
        jour_courant = debut
        while jour_courant <= fin:
            ligne = stats_par_jour.get(jour_courant)
            resultats.append({
                'date': jour_courant.isoformat(),
                'nb_ventes': ligne['nb_ventes'] if ligne else 0,
                'chiffre_affaires': ligne['chiffre_affaires'] if ligne else Decimal('0.00'),
            })
            jour_courant += timedelta(days=1)

        total_ca = sum((r['chiffre_affaires'] for r in resultats), Decimal('0.00'))
        jours_avec_ventes = sum(1 for r in resultats if r['nb_ventes'] > 0)
        ca_moyen = (total_ca / jours_avec_ventes).quantize(Decimal('0.01')) if jours_avec_ventes else Decimal('0.00')

        return Response({
            'debut': debut.isoformat(),
            'fin': fin.isoformat(),
            'total_chiffre_affaires': total_ca,
            'ca_moyen_journalier': ca_moyen,
            'donnees': resultats,
        })


class RapportVentesView(APIView):
    """
    GET /api/rapports/ventes/?debut=AAAA-MM-JJ&fin=AAAA-MM-JJ&par=jour

    ``par`` accepte jour, semaine, mois, annee, vin, categorie ou vendeur.
    ``?format=csv``, ``?format=xlsx`` ou ``?format=pdf`` télécharge le rapport.ltats dans un
    tableur (voir ``config.renderers``) : le JSON reste la réponse par défaut.
    """
    permission_classes = [IsAdmin]
    renderer_classes = [
        JSONRenderer, CSVRenderer, XLSXRenderer, PDFRenderer, BrowsableAPIRenderer,
    ]
    REGROUPEMENTS_DATE = {
        'jour': TruncDate,
        'semaine': TruncWeek,
        'mois': TruncMonth,
        'annee': TruncYear,
    }
    REGROUPEMENTS_ENTITE = {
        'vin': ('lignes__produit_id', 'lignes__produit__nom'),
        'categorie': ('lignes__produit__categorie_id', 'lignes__produit__categorie__nom'),
        'vendeur': ('utilisateur_id', 'utilisateur__username'),
    }
    #: En-têtes d'export en français : le tableur est lu par le comptable, pas
    #: par un développeur. Les clés techniques restent en JSON.
    LIBELLES_EXPORT = {
        'periode': 'Période',
        'vin': 'Cuvée',
        'categorie': 'Catégorie',
        'vendeur': 'Vendeur',
        'ventes': 'Ventes',
        'quantite': 'Quantité',
        'chiffre_affaires': "Chiffre d'affaires",
        'panier_moyen': 'Panier moyen',
    }

    def get_export_entetes(self):
        """Clés des colonnes d'export, dans l'ordre d'affichage."""
        regroupement = (self.request.query_params.get('par', 'jour') or 'jour').strip().lower()
        if regroupement in self.REGROUPEMENTS_ENTITE:
            return [regroupement, 'ventes', 'quantite', 'chiffre_affaires']
        return ['periode', 'ventes', 'chiffre_affaires', 'panier_moyen']

    def get_export_libelles(self, cles):
        """Nom lisible de chaque colonne : le tableur est lu par un comptable."""
        return [self.LIBELLES_EXPORT.get(cle, cle) for cle in cles]

    def get_export_nom(self):
        """Nom de fichier parlant, avec la période : le rapport se retrouve
        dans le dossier Téléchargements six mois plus tard."""
        requete = self.request.query_params
        regroupement = (requete.get('par', 'jour') or 'jour').strip().lower()
        debut = requete.get('debut') or ''
        fin = requete.get('fin') or ''
        periode = f'-{debut}_{fin}' if debut and fin else ''
        return f'rapport-ventes-{regroupement}{periode}'

    def get(self, request):
        today = timezone.localdate()
        debut_str = request.query_params.get('debut')
        fin_str = request.query_params.get('fin')
        try:
            debut = datetime.strptime(debut_str, '%Y-%m-%d').date() if debut_str else today.replace(day=1)
            fin = datetime.strptime(fin_str, '%Y-%m-%d').date() if fin_str else today
        except ValueError:
            return Response({'erreur': 'Format de date invalide. Utilisez AAAA-MM-JJ.'}, status=400)
        if debut > fin:
            return Response({'erreur': 'La date de début doit précéder la date de fin.'}, status=400)
        if (fin - debut).days > 366:
            return Response({'erreur': 'La période ne peut pas dépasser 366 jours.'}, status=400)

        regroupement = request.query_params.get('par', 'jour').strip().lower()
        queryset = Vente.objects.filter(
            statut=Vente.Statut.PAYEE,
            date_vente__date__gte=debut,
            date_vente__date__lte=fin,
        )
        lignes = []
        if regroupement in self.REGROUPEMENTS_DATE:
            queryset = queryset.annotate(
                periode=self.REGROUPEMENTS_DATE[regroupement]('date_vente'),
            ).values('periode').annotate(
                ventes=Count('id', distinct=True),
                chiffre_affaires=Sum('total'),
                panier_moyen=Avg('total'),
            ).order_by('periode')
            lignes = [{
                'periode': item['periode'].isoformat() if item['periode'] else '',
                'ventes': item['ventes'],
                'chiffre_affaires': str(item['chiffre_affaires'] or Decimal('0.00')),
                'panier_moyen': str(item['panier_moyen'] or Decimal('0.00')),
            } for item in queryset]
        elif regroupement in self.REGROUPEMENTS_ENTITE:
            cle, libelle = self.REGROUPEMENTS_ENTITE[regroupement]
            queryset = queryset.values(cle, libelle).annotate(
                ventes=Count('id', distinct=True),
                chiffre_affaires=Sum('lignes__sous_total'),
                quantite=Sum('lignes__quantite'),
            ).order_by('-chiffre_affaires', libelle)
            lignes = [{
                regroupement: item[libelle] or 'Sans catégorie',
                'ventes': item['ventes'],
                'quantite': item['quantite'] or 0,
                'chiffre_affaires': _format_montant(item['chiffre_affaires']),
            } for item in queryset]
        else:
            return Response({
                'erreur': "Regroupement invalide. Choisissez jour, semaine, mois, annee, vin, categorie ou vendeur."
            }, status=400)

        aggregate = Vente.objects.filter(
            statut=Vente.Statut.PAYEE,
            date_vente__date__gte=debut,
            date_vente__date__lte=fin,
        ).aggregate(
            chiffre_affaires=Sum('total'),
            ventes=Count('id'),
            panier_moyen=Avg('total'),
        )
        stocks = Stock.objects.aggregate(
            total_quantite=Sum('quantite'),
            valeur=Sum(F('quantite') * cout_unitaire_expression()),
        )
        donnees = {
            'debut': debut.isoformat(),
            'fin': fin.isoformat(),
            'par': regroupement,
            'ventes': aggregate['ventes'],
            'chiffre_affaires': _format_montant(aggregate['chiffre_affaires']),
            'panier_moyen': _format_montant(aggregate['panier_moyen']),
            'stock_unites': stocks['total_quantite'] or 0,
            'valeur_stock': _format_montant(stocks['valeur']),
            'donnees': lignes,
        }
        lignes_promo = LigneVente.objects.filter(
            vente__statut=Vente.Statut.PAYEE,
            vente__date_vente__date__gte=debut,
            vente__date_vente__date__lte=fin,
            promotion__isnull=False,
        )
        remise_promotion_brute = ExpressionWrapper(
            F('remise') - F('remise_manuelle'),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        remise_promotion_expression = Case(
            When(remise__gt=F('remise_manuelle'), then=remise_promotion_brute),
            default=Value(
                Decimal('0.00'),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        statistiques_promo = lignes_promo.aggregate(
            ventes=Count('vente_id', distinct=True),
            lignes=Count('id'),
            remise_accordee=Sum(remise_promotion_expression),
            chiffre_affaires_net=Sum('sous_total'),
        )
        promotions = lignes_promo.values(
            'promotion_id', 'promotion__nom',
        ).annotate(
            ventes=Count('vente_id', distinct=True),
            lignes=Count('id'),
            remise_accordee=Sum(remise_promotion_expression),
            chiffre_affaires_net=Sum('sous_total'),
        ).order_by('-remise_accordee', 'promotion__nom')
        total_remises_promo = statistiques_promo['remise_accordee'] or Decimal('0.00')
        ca_net_promo = statistiques_promo['chiffre_affaires_net'] or Decimal('0.00')
        base_ca_promo = ca_net_promo + total_remises_promo
        donnees['promotions'] = {
            'ventes': statistiques_promo['ventes'],
            'lignes': statistiques_promo['lignes'],
            'remise_accordee': _format_montant(total_remises_promo),
            'chiffre_affaires_net': _format_montant(ca_net_promo),
            'taux_remise_pct': _format_montant(
                total_remises_promo * 100 / base_ca_promo if base_ca_promo else 0
            ),
            'donnees': [{
                'promotion': item['promotion__nom'],
                'ventes': item['ventes'],
                'lignes': item['lignes'],
                'remise_accordee': _format_montant(item['remise_accordee']),
                'chiffre_affaires_net': _format_montant(item['chiffre_affaires_net']),
            } for item in promotions],
        }
        # Les exports tabulaires sont gérés par DRF : `?format=csv` ou
        # `?format=xlsx`. On renvoie donc systématiquement le JSON et on laisse
        # le renderer positionner le type MIME et le nom du fichier, qu'il
        # demande à la vue via `get_export_nom()`.
        return Response(donnees)


class RapportsView(View):
    """Page de consultation, d'export et d'impression des rapports."""

    template_name = 'admin/rapports.html'

    def get(self, request):
        return render(request, self.template_name, admin.site.each_context(request))
