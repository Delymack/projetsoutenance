from django.contrib import admin
from django.db.models import Count
from apps.categories.models import Categorie
from config.admin_mixins import ActionsColonneMixin

@admin.register(Categorie)
class CategorieAdmin(ActionsColonneMixin, admin.ModelAdmin):
    change_list_template = 'admin/categories/categorie/change_list.html'
    list_display = ('nom', 'produits_count', 'statut', 'date_creation')
    search_fields = ('nom',)
    list_filter = ('statut',)
    ordering = ('nom',)
    readonly_fields = ('date_creation', 'updated_at')

    # Formulaire d'ajout : uniquement les champs essentiels.
    add_fieldsets = (
        ('Nouvelle catégorie', {
            'fields': ('nom', 'description', 'statut'),
        }),
    )

    fieldsets = (
        ('Catégorie', {'fields': ('nom', 'description')}),
        ('Paramètre', {'fields': ('statut',)}),
        ('Dates', {'fields': ('date_creation', 'updated_at'), 'classes': ('collapse',)}),
    )

    def get_fieldsets(self, request, obj=None):
        """Ajout : formulaire réduit. Modification : fiche complète."""
        if obj is None:
            return self.add_fieldsets
        return self.fieldsets

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['categories_kpis'] = {
            'total': Categorie.objects.count(),
            'actives': Categorie.objects.filter(statut=True).count(),
            'avec_produits': Categorie.objects.filter(produits__isnull=False).distinct().count(),
            'produits': Categorie.objects.aggregate(n=Count('produits'))['n'] or 0,
        }
        return super().changelist_view(request, extra_context=extra_context)

    @admin.display(description='Produits')
    def produits_count(self, obj):
        return obj.produits.count()
