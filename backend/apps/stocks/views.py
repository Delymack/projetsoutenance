from rest_framework import viewsets, permissions
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
