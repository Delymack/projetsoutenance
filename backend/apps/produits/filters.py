import django_filters
from django.db.models import F, Q
from apps.produits.models import Produit
from apps.stocks.models import Stock
from apps.promotions.services import promotions_actives_qs


class ProduitFilter(django_filters.FilterSet):
    prix_min = django_filters.NumberFilter(field_name="prix_vente", lookup_expr='gte')
    prix_max = django_filters.NumberFilter(field_name="prix_vente", lookup_expr='lte')
    cout_revenir_min = django_filters.NumberFilter(field_name="cout_revenir", lookup_expr='gte')
    cout_revenir_max = django_filters.NumberFilter(field_name="cout_revenir", lookup_expr='lte')
    nom = django_filters.CharFilter(field_name="nom", lookup_expr='icontains')
    marque = django_filters.CharFilter(field_name="marque", lookup_expr='icontains')
    appellation = django_filters.CharFilter(field_name="appellation", lookup_expr='icontains')
    cepage = django_filters.CharFilter(field_name="cepage", lookup_expr='icontains')
    type_vin_exact = django_filters.CharFilter(field_name="type_vin", lookup_expr='exact')
    en_promo = django_filters.BooleanFilter(method='filter_en_promo')
    en_stock = django_filters.BooleanFilter(method='filter_en_stock')
    rupture = django_filters.BooleanFilter(method='filter_rupture')
    stock_faible = django_filters.BooleanFilter(method='filter_stock_faible')

    class Meta:
        model = Produit
        fields = ['categorie', 'type_vin', 'marque', 'statut', 'volume']

    def filter_en_promo(self, queryset, name, value):
        """Vins en promotion, ciblés directement ou via leur catégorie."""
        if value:
            actives = promotions_actives_qs()
            return queryset.filter(
                Q(promotions__in=actives) | Q(categorie__promotions__in=actives)
            ).distinct()
        return queryset

    def filter_en_stock(self, queryset, name, value):
        if value:
            return queryset.filter(stock__quantite__gt=0)
        return queryset

    def filter_rupture(self, queryset, name, value):
        if value:
            return queryset.filter(stock__quantite__lte=0)
        return queryset

    def filter_stock_faible(self, queryset, name, value):
        if value:
            return queryset.filter(stock__quantite__gt=0, stock__quantite__lte=F('stock__seuil_alerte'))
        return queryset
