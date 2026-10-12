import django_filters
from apps.ventes.models import Vente

class VenteFilter(django_filters.FilterSet):
    date_debut = django_filters.DateFilter(field_name="date_vente", lookup_expr='gte')
    date_fin = django_filters.DateFilter(field_name="date_vente", lookup_expr='lte')
    
    class Meta:
        model = Vente
        fields = ['client', 'statut', 'mode_paiement']
