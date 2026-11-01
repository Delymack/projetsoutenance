from django.contrib import admin
from django.db.models import F

from django.utils.html import format_html

from apps.stocks.models import Stock, MouvementStock
from apps.stocks.valorisation import valeur_stock_totale
from config.admin_mixins import ActionsColonneMixin


@admin.register(Stock)
class StockAdmin(ActionsColonneMixin, admin.ModelAdmin):
    change_list_template = 'admin/stocks/stock/change_list.html'
    # La valeur totale est déjà visible dans les indicateurs du haut de page.
    list_display = ('image_tag', 'produit', 'quantite', 'seuil_alerte', 'etat_stock_display')
    list_editable = ('quantite', 'seuil_alerte')
    search_fields = ('produit__nom', 'produit__marque')
    list_filter = ('date_mise_a_jour',)
    ordering = ('produit__nom',)
    autocomplete_fields = ('produit',)
    list_per_page = 25
    # `date_mise_a_jour` est `auto_now` : non éditable, il doit être déclaré en
    # lecture seule. Sinon Django refuse de construire le formulaire (FieldError).
    readonly_fields = ('date_mise_a_jour',)

    fieldsets = (
        ('Stock', {'fields': ('produit', 'quantite', 'seuil_alerte')}),
        ('Mise à jour', {'fields': ('date_mise_a_jour',), 'classes': ('collapse',)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('produit')

    @admin.display(description='Photo')
    def image_tag(self, obj):
        if obj.produit.image:
            return format_html(
                '<img src="{}" alt="Photo de {}">',
                obj.produit.image.url,
                obj.produit.nom,
            )
        return format_html(
            '<span class="stock-product-placeholder" aria-hidden="true">'
            '<i class="fas fa-wine-bottle">{}</i></span>',
            '',
        )

    def changelist_view(self, request, extra_context=None):
        stocks = Stock.objects.all()
        extra_context = extra_context or {}
        extra_context['stocks_kpis'] = {
            'total': stocks.count(),
            'ruptures': stocks.filter(quantite__lte=0).count(),
            'faibles': stocks.filter(quantite__gt=0, quantite__lte=F('seuil_alerte')).count(),
            'valeur': valeur_stock_totale(),
        }
        return super().changelist_view(request, extra_context=extra_context)

    @admin.display(description='État du stock', ordering='quantite')
    def etat_stock_display(self, obj):
        etat = obj.etat_stock
        css = {
            'STOCK_NORMAL': 'lb-badge-sage',
            'STOCK_FAIBLE': 'lb-badge-gold',
        }.get(etat, 'lb-badge-wine')
        return format_html('<span class="lb-badge {}">{}</span>', css, etat.replace('_', ' '))

@admin.register(MouvementStock)
class MouvementStockAdmin(ActionsColonneMixin, admin.ModelAdmin):
    change_list_template = 'admin/stocks/mouvementstock/change_list.html'
    # La référence détaillée reste consultable sur la fiche du mouvement.
    list_display = ('date_mouvement', 'produit', 'type_badge', 'quantite_display')
    search_fields = ('produit__nom', 'reference_id', 'description')
    list_filter = ('type_mouvement', 'date_mouvement')
    ordering = ('-date_mouvement',)
    readonly_fields = ('produit', 'quantite', 'type_mouvement', 'description', 'reference_id', 'utilisateur', 'date_mouvement')
    date_hierarchy = 'date_mouvement'
    list_per_page = 30
    # Un mouvement : quand, sur quel vin, dans quel sens, de combien. La pièce
    # d'origine (vente, retour, référence) et le vendeur sont repliés.
    fieldsets = (
        ('Mouvement', {'fields': ('date_mouvement', 'produit', 'type_mouvement', 'quantite')}),
        ('Pièce d’origine', {
            'fields': ('reference_id', 'description', 'utilisateur'),
            'classes': ('collapse',),
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('produit', 'utilisateur')

    def changelist_view(self, request, extra_context=None):
        qs = MouvementStock.objects.all()
        extra_context = extra_context or {}
        extra_context['mouvements_kpis'] = {
            'total': qs.count(),
            'entrees': qs.filter(type_mouvement=MouvementStock.TypeMouvement.ENTREE).count(),
            'sorties': qs.filter(type_mouvement=MouvementStock.TypeMouvement.SORTIE).count(),
            'retours': qs.filter(type_mouvement=MouvementStock.TypeMouvement.RETOUR).count(),
        }
        return super().changelist_view(request, extra_context=extra_context)

    @admin.display(description='Type', ordering='type_mouvement')
    def type_badge(self, obj):
        css = {
            MouvementStock.TypeMouvement.ENTREE: 'lb-badge-sage',
            MouvementStock.TypeMouvement.SORTIE: 'lb-badge-wine',
            MouvementStock.TypeMouvement.RETOUR: 'lb-badge-gold',
            MouvementStock.TypeMouvement.AJUSTEMENT: 'lb-badge-muted',
        }.get(obj.type_mouvement, 'lb-badge-muted')
        icone = {
            MouvementStock.TypeMouvement.ENTREE: 'fa-arrow-down',
            MouvementStock.TypeMouvement.SORTIE: 'fa-arrow-up',
            MouvementStock.TypeMouvement.RETOUR: 'fa-undo',
        }.get(obj.type_mouvement, 'fa-sliders')
        return format_html(
            '<span class="lb-badge {}"><i class="fas {}"></i>{}</span>',
            css, icone, obj.get_type_mouvement_display(),
        )

    @admin.display(description='Quantité', ordering='quantite')
    def quantite_display(self, obj):
        signe = '+' if obj.quantite > 0 else ''
        css = 'lb-val-sage' if obj.quantite > 0 else 'lb-val-wine'
        return format_html('<strong class="{}">{}{}</strong>', css, signe, obj.quantite)
