from django.db import transaction
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.stocks.models import Stock, MouvementStock
from apps.stocks.serializers import (
    StockSerializer,
    StockDetailSerializer,
    MouvementStockSerializer
)
from apps.accounts.permissions import IsAdminOrReadOnly

class StockViewSet(viewsets.ModelViewSet):
    queryset = Stock.objects.select_related('produit').all()
    permission_classes = [IsAdminOrReadOnly]

    def get_serializer_class(self):
        if self.action in ['retrieve', 'list']:
            return StockDetailSerializer
        return StockSerializer

    @action(detail=True, methods=['post'], url_path='modifier')
    def modifier(self, request, pk=None):
        """Ajuste manuellement la quantité et/ou le seuil d'alerte d'un stock.

        Chaque écart de quantité est enregistré dans l'historique : un
        MouvementStock AJUSTEMENT (Δ signé) lié à l'utilisateur qui saisit.
        Sans écart, seule la mise à jour de seuil est appliquée.
        """
        stock = self.get_object()
        serializer = StockSerializer(stock, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        donnees = serializer.validated_data
        nouvelle_quantite = donnees.get('quantite', stock.quantite)
        with transaction.atomic():
            stock = Stock.objects.select_for_update().get(pk=stock.pk)
            ecart = nouvelle_quantite - stock.quantite
            for champ in ('quantite', 'seuil_alerte'):
                if champ in donnees:
                    setattr(stock, champ, donnees[champ])
            stock.save(update_fields=['quantite', 'seuil_alerte'])
            if ecart:
                MouvementStock.objects.create(
                    produit=stock.produit,
                    quantite=ecart,
                    type_mouvement=MouvementStock.TypeMouvement.AJUSTEMENT,
                    description='Ajustement manuel via API',
                    reference_id=f'stock-{stock.pk}',
                    utilisateur=request.user if request.user.is_authenticated else None,
                )
        return Response(StockSerializer(stock).data, status=status.HTTP_200_OK)


class MouvementStockViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet pour consulter l'historique des mouvements de stock.
    Lecture seule car les mouvements sont créés par le système.
    """
    queryset = MouvementStock.objects.select_related('produit', 'utilisateur').all()
    serializer_class = MouvementStockSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['produit', 'type_mouvement', 'reference_id']
    search_fields = ['description', 'reference_id', 'produit__nom']
