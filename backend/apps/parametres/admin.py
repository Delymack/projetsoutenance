from django.contrib import admin

from apps.parametres.models import EntreeJournal, Parametre
from config.admin_mixins import ActionsColonneMixin


@admin.register(Parametre)
class ParametreAdmin(ActionsColonneMixin, admin.ModelAdmin):
    list_display = ('cle', 'section', 'libelle', 'type', 'valeur', 'modifie_le')
    list_filter = ('section', 'type')
    search_fields = ('cle', 'libelle', 'valeur')
    ordering = ('section', 'ordre', 'cle')
    readonly_fields = ('cle', 'section', 'type', 'libelle', 'options', 'aide', 'ordre', 'modifie_le')
    # Un réglage : ce qu'il est, puis sa valeur — le seul champ qui se modifie.
    # Le type, les options et l'aide décrivent le champ, pas le réglage : ils
    # restent lisibles, repliés.
    fieldsets = (
        ('Réglage', {'fields': ('cle', 'section', 'libelle', 'valeur')}),
        ('Description du champ', {
            'fields': ('type', 'options', 'aide', 'ordre'),
            'classes': ('collapse',),
        }),
        ('Système', {'fields': ('modifie_le',), 'classes': ('collapse',)}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EntreeJournal)
class EntreeJournalAdmin(ActionsColonneMixin, admin.ModelAdmin):
    # Journal : quand, quoi, où, sur quoi, par qui. La clé technique et l'adresse
    # IP restent sur la fiche.
    list_display = ('date', 'action', 'section', 'libelle', 'utilisateur')
    list_filter = ('action', 'section')
    search_fields = ('cle', 'libelle', 'utilisateur__username')
    date_hierarchy = 'date'
    readonly_fields = [f.name for f in EntreeJournal._meta.fields]
    # Une entrée de journal : quand, quoi, où, par qui. Le détail (clé technique,
    # valeur avant/après, adresse IP) sert au contrôle, pas à la lecture : replié.
    fieldsets = (
        ('Entrée', {'fields': ('date', 'action', 'section', 'libelle', 'utilisateur')}),
        ('Détail', {
            'fields': ('cle', 'avant', 'apres', 'ip'),
            'classes': ('collapse',),
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False