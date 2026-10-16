from django.urls import reverse
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe


class ActionsColonneMixin:
    """Ajoute une colonne « Actions » (Modifier / Supprimer / Voir) sur le
    changelist, appliquée à toutes les tables qui héritent de ce mixin.

    Les boutons respectent les permissions de l'utilisateur (ajouté en fin de
    list_display pour ne pas interférer avec le tri ni l'édition en ligne).
    """

    afficher_colonne_actions = True
    _requete_admin = None

    def get_list_display(self, request):
        self._requete_admin = request
        list_display = list(super().get_list_display(request))
        if self.afficher_colonne_actions:
            if "_actions_col" not in list_display:
                list_display.append("_actions_col")
        return tuple(list_display)

    def _actions_col(self, obj):
        request = getattr(self, "_requete_admin", None)
        if request is None:
            return ""
        opts = obj._meta
        boutons = []

        if self.has_change_permission(request, obj):
            url = reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk])
            boutons.append(
                f'<a class="databtn databtn-edit" href="{url}" aria-label="Modifier" data-quick-create="on" data-quick-create-title="Modifier: {escape(str(obj))}">'
                '<i class="fas fa-pen-nib"></i>'
                '<span class="databtn-label">Modifier</span></a>'
            )

        if self.has_delete_permission(request, obj):
            url = reverse(f"admin:{opts.app_label}_{opts.model_name}_delete", args=[obj.pk])
            nom = escape(str(obj))
            boutons.append(
                f'<a class="databtn databtn-delete" href="{url}" aria-label="Supprimer" data-confirm-name="{nom}">'
                '<i class="fas fa-trash"></i>'
                '<span class="databtn-label">Supprimer</span></a>'
            )

        if not boutons and self.has_view_permission(request, obj):
            url = reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk])
            boutons.append(
                f'<a class="databtn databtn-view" href="{url}" aria-label="Voir">'
                '<i class="fas fa-eye"></i>'
                '<span class="databtn-label">Voir</span></a>'
            )

        if not boutons:
            return format_html('<span class="text-muted">{}</span>', "—")
        return format_html('<span class="databtn-group">{}</span>', mark_safe("".join(boutons)))

    _actions_col.short_description = "Actions"