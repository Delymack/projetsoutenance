import django_filters
from django.contrib.admin import SimpleListFilter
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.promotions.models import Promotion
from apps.promotions.services import promotions_actives_q, happy_hour_active


class PromotionFilter(django_filters.FilterSet):
    active = django_filters.BooleanFilter(method='filter_active')
    date = django_filters.DateFilter(method='filter_date')
    categorie = django_filters.NumberFilter(field_name='categories__id')
    produit = django_filters.NumberFilter(field_name='produits__id')
    code = django_filters.CharFilter(field_name='code', lookup_expr='iexact')
    happy_hour = django_filters.BooleanFilter(method='filter_happy_hour')
    type_cible = django_filters.ChoiceFilter(field_name='type_cible')

    class Meta:
        model = Promotion
        fields = ['type_promotion', 'statut', 'type_cible']

    def filter_active(self, queryset, name, value):
        if value:
            return queryset.filter(promotions_actives_q())
        return queryset.exclude(promotions_actives_q())

    def filter_date(self, queryset, name, value):
        return queryset.filter(date_debut__lte=value, date_fin__gte=value)

    def filter_happy_hour(self, queryset, name, value):
        """Promotions à créneau horaire dont le créneau est ouvert maintenant."""
        if value is None:
            return queryset
        if value:
            a_creneau = [p.id for p in queryset if p.a_un_creneau and happy_hour_active(p)]
            return queryset.filter(id__in=a_creneau)
        return queryset.exclude(
            id__in=[p.id for p in queryset if p.a_un_creneau and happy_hour_active(p)]
        )


class EtatPromotionFilter(SimpleListFilter):
    """Filtre admin : état calculé d'une promotion (actif, à venir, expirée, désactivée)."""

    title = _('État')
    parameter_name = 'etat'

    def lookups(self, request, model_admin):
        return [
            ('actives', _('Actives')),
            ('a_venir', _('À venir')),
            ('expirees', _('Expirées')),
            ('desactivees', _('Désactivées')),
        ]

    def queryset(self, request, queryset):
        now = timezone.now()
        valeur = self.value()
        if valeur == 'actives':
            return queryset.filter(promotions_actives_q())
        if valeur == 'a_venir':
            return queryset.filter(statut=True, date_debut__gt=now)
        if valeur == 'expirees':
            return queryset.filter(statut=True, date_fin__lt=now)
        if valeur == 'desactivees':
            return queryset.filter(statut=False)
        return queryset


class CreneauFilter(SimpleListFilter):
    """Filtre admin : promotions à créneau happy hour, ouvert ou fermé."""

    title = _('Happy hour')
    parameter_name = 'creneau'

    def lookups(self, request, model_admin):
        return [
            ('ouvert', _('Créneau ouvert')),
            ('ferme', _('Créneau fermé')),
            ('defini', _('Avec créneau')),
            ('sans', _('Sans créneau')),
        ]

    def queryset(self, request, queryset):
        valeur = self.value()
        promos = [p for p in queryset if p.a_un_creneau]
        if valeur == 'sans':
            return queryset.exclude(id__in=[p.id for p in promos])
        if valeur == 'defini':
            return queryset.filter(id__in=[p.id for p in promos])
        if valeur == 'ouvert':
            return queryset.filter(id__in=[p.id for p in promos if happy_hour_active(p)])
        if valeur == 'ferme':
            return queryset.filter(id__in=[p.id for p in promos if not happy_hour_active(p)])
        return queryset


