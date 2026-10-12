from django.db.models import Avg, Count, F, Prefetch, Q, Sum
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny

from apps.clients.models import Client
from apps.produits.models import Produit
from apps.produits.couts import cout_effectif_expression, marge_unitaire_expression
from apps.produits.serializers import (
    ProduitSerializer,
    ProduitDetailSerializer,
)
from apps.promotions.services import promotions_actives_qs
from apps.promotions.models import PromotionProduit
from apps.accounts.permissions import IsAdminOrReadOnly
from apps.produits.filters import ProduitFilter
from apps.stocks.models import Stock


class ProduitViewSet(viewsets.ModelViewSet):
    serializer_class = ProduitSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = ProduitFilter
    search_fields = [
        'nom', 'description', 'marque', 'appellation', 'cepage', 'type_vin', 'code_barre',
    ]
    ordering_fields = [
        'nom', 'prix_vente', 'cout_revenir', 'date_creation', 'millesime', 'degre_alcool',
    ]
    ordering = ['-date_creation']

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'scanner'):
            return [AllowAny()]
        return super().get_permissions()

    def get_queryset(self):
        """
        Queryset optimisé :
        - select_related pour categorie/stock (évite 1 requête par ligne)
        - Prefetch des promotions actives vers des attributs dédiés (évite 1
          requête par ligne dans ProduitDetailSerializer.get_promotion_active) :
          ciblage direct (M2M via PromotionProduit) et ciblage par catégorie.
        - Seules les actions list/retrieve surchargent le queryset de base.
        """
        qs = Produit.objects.select_related('categorie', 'stock').all()
        if self.action in ('list', 'retrieve'):
            qs = qs.prefetch_related(
                Prefetch(
                    'promotions',  # M2M Produit -> Promotion via PromotionProduit
                    queryset=promotions_actives_qs(),
                    to_attr='promotions_actives',
                ),
                Prefetch(
                    'categorie__promotions',  # promotions ciblant la catégorie
                    queryset=promotions_actives_qs(),
                    to_attr='promotions_actives_categorie',
                ),
            )
        return qs

    def get_serializer_class(self):
        if self.action in ['retrieve', 'list']:
            return ProduitDetailSerializer
        return ProduitSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        client_id = self.request.query_params.get('client')
        if client_id:
            context['type_client'] = Client.objects.filter(pk=client_id).values_list(
                'type_client', flat=True,
            ).first()
        return context

    @action(detail=False, methods=['get'], url_path='scanner')
    def scanner(self, request):
        """
        Résolution d'un code-barres lu par la douchette.

        Répond en un aller-retour, avec le prix promotionnel déjà calculé et le
        stock disponible : la caisse n'a rien à recalculer côté navigateur.
        """
        code = (request.query_params.get('code') or '').strip()
        if not code:
            return Response({'trouve': False, 'code': code}, status=status.HTTP_400_BAD_REQUEST)

        produit = Produit.objects.filter(code_barre=code).first()
        if produit is None:
            return Response({'trouve': False, 'code': code})

        serializer = ProduitDetailSerializer(produit, context=self.get_serializer_context())
        return Response({
            'trouve': True,
            'code': code,
            'produit': serializer.data,
            'stock': serializer.data.get('stock_quantite', 0),
            'vente_possible': produit.statut and serializer.data.get('stock_quantite', 0) > 0,
        })

    @action(detail=False, methods=['get'], url_path='statistiques')
    def statistiques(self, request):
        """
        Endpoint de statistiques pour le tableau de bord produits.
        Toutes les métriques sont calculées en SQL (agrégations), aucun
        chargement des lignes en mémoire Python.
        """
        now = timezone.now()

        # Un seul passage sur Produit : compteurs + moyenne + somme des marges.
        agg = Produit.objects.aggregate(
            total=Count('id'),
            actifs=Count('id', filter=Q(statut=True)),
            inactifs=Count('id', filter=Q(statut=False)),
            prix_moyen_vente=Avg('prix_vente'),
            marge_totale=Sum(marge_unitaire_expression()),
        )

        stocks = Stock.objects.aggregate(
            ruptures=Count('id', filter=Q(quantite__lte=0)),
            faibles=Count('id', filter=Q(quantite__gt=0, quantite__lte=F('seuil_alerte'))),
        )

        actives = promotions_actives_qs()
        produits_en_promo = set(
            PromotionProduit.objects.filter(promotion__in=actives)
            .values_list('produit_id', flat=True)
        )
        produits_en_promo |= set(
            Produit.objects.filter(categorie__promotions__in=actives)
            .values_list('id', flat=True)
        )

        qs = Produit.objects.all()
        data = {
            'total': agg['total'],
            'actifs': agg['actifs'],
            'inactifs': agg['inactifs'],
            'ruptures': stocks['ruptures'],
            'faibles': stocks['faibles'],
            'en_promo': len(produits_en_promo),
            'par_type': list(qs.values('type_vin').annotate(nb=Count('id')).order_by('-nb')),
            'par_categorie': list(qs.values('categorie__nom').annotate(nb=Count('id')).order_by('categorie__nom')),
            'prix_moyen_vente': round(agg['prix_moyen_vente'], 2) if agg['prix_moyen_vente'] is not None else 0,
            # Sum() renvoie Decimal ; conversion en float pour garder un JSON simple.
            'marge_totale': float(agg['marge_totale']) if agg['marge_totale'] is not None else 0,
        }
        return Response(data)

    @action(detail=False, methods=['post'], url_path='changer-statut')
    def changer_statut(self, request):
        """Action bulk pour changer le statut de plusieurs produits."""
        ids = request.data.get('ids', [])
        statut = request.data.get('statut', True)
        if not ids:
            return Response({'error': 'Aucun ID fourni.'}, status=status.HTTP_400_BAD_REQUEST)
        updated = Produit.objects.filter(id__in=ids).update(statut=statut)
        return Response({'updated': updated, 'statut': statut})

    @action(detail=False, methods=['get'], url_path='par-type')
    def par_type(self, request):
        """Liste des types de vin avec compteur."""
        data = list(
            Produit.objects.values('type_vin').annotate(nb=Count('id')).order_by('-nb')
        )
        return Response(data)

    @action(detail=False, methods=['get'], url_path='par-categorie')
    def par_categorie(self, request):
        """Liste des catégories avec compteur."""
        data = list(
            Produit.objects.values('categorie__nom').annotate(nb=Count('id')).order_by('categorie__nom')
        )
        return Response(data)
