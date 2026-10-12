from datetime import timedelta
from decimal import Decimal

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.conf import settings
from django.db.models import Count, DecimalField, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.categories.models import Categorie
from apps.produits.models import Produit
from apps.promotions.models import Promotion, PromotionProduit
from apps.promotions.services import (
    happy_hour_active,
    impact_promotions,
    promotions_actives_q,
    repartition_par_cible,
    repartition_par_type,
    statistiques_promotion,
    top_promos_impact,
)
from apps.promotions.filters import CreneauFilter, EtatPromotionFilter


@admin.action(description='Activer les promotions sélectionnées')
def activer_promotions(modeladmin, request, queryset):
    nb = queryset.update(statut=True)
    modeladmin.message_user(request, f"{nb} promotion(s) activée(s) avec succès.")


@admin.action(description='Désactiver les promotions sélectionnées')
def desactiver_promotions(modeladmin, request, queryset):
    nb = queryset.update(statut=False)
    modeladmin.message_user(request, f"{nb} promotion(s) désactivée(s) avec succès.")


class PromotionAdminForm(forms.ModelForm):
    type_promotion = forms.ChoiceField(label='Type de remise')
    valeur = forms.DecimalField(
        label='Valeur',
        min_value=0.01,
        max_digits=10,
        decimal_places=2,
    )
    produits_cibles = forms.ModelMultipleChoiceField(
        label='Vins concernés',
        queryset=Produit.objects.order_by('nom'),
        required=False,
        widget=FilteredSelectMultiple('vins', is_stacked=False),
    )
    categories = forms.ModelMultipleChoiceField(
        label='Catégories concernées',
        queryset=Categorie.objects.order_by('nom'),
        required=False,
        widget=FilteredSelectMultiple('catégories', is_stacked=False),
    )
    date_debut = forms.DateTimeField(
        label='Date de début',
        input_formats=('%Y-%m-%dT%H:%M',),
        widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}),
    )
    date_fin = forms.DateTimeField(
        label='Date de fin',
        input_formats=('%Y-%m-%dT%H:%M',),
        widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}),
    )

    class Meta:
        model = Promotion
        fields = (
            'nom', 'type_promotion', 'valeur', 'date_debut', 'date_fin',
            'type_cible', 'quantite_min', 'code', 'statut',
            'produits_cibles', 'categories',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        types_disponibles = Promotion.TypePromotion.choices
        if not self.instance or not self.instance.pk:
            types_disponibles = (
                (Promotion.TypePromotion.POURCENTAGE, 'Pourcentage'),
                (Promotion.TypePromotion.MONTANT_FIXE, 'Montant fixe'),
            )
        self.fields['type_promotion'].choices = types_disponibles
        type_promotion = (
            self.data.get('type_promotion')
            or self.initial.get('type_promotion')
            or getattr(self.instance, 'type_promotion', Promotion.TypePromotion.POURCENTAGE)
        )
        self.fields['valeur'].label = (
            'Pourcentage de remise (%)'
            if type_promotion == Promotion.TypePromotion.POURCENTAGE
            else 'Montant de la remise (Ar)'
        )
        self.fields['valeur'].help_text = (
            'Saisissez un nombre entre 0 et 100.'
            if type_promotion == Promotion.TypePromotion.POURCENTAGE
            else 'Montant déduit du prix de chaque bouteille.'
        )
        if not self.instance or not self.instance.pk:
            debut = timezone.localtime().replace(second=0, microsecond=0)
            self.initial.setdefault('date_debut', debut)
            self.initial.setdefault('date_fin', debut + timedelta(days=30))
            self.fields['nom'].label = 'Nom de la promotion'
            self.fields['statut'].label = 'Statut actif'
            self.fields.pop('produits_cibles', None)
            self.fields.pop('categories', None)
        if self.instance and self.instance.pk:
            self.fields['produits_cibles'].initial = self.instance.produits.all()


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    change_list_template = 'admin/promotions/promotion/change_list.html'
    change_form_template = 'admin/promotions/promotion/change_form.html'
    form = PromotionAdminForm
    # Une promotion se lit en trois temps : la règle, sa cible, son état — puis ce
    # qu'elle rapporte. Le type (déjà dit par la règle), le créneau et les bornes
    # de dates (dites par l'état) restent sur la fiche et dans les filtres. Les
    # trois colonnes de résultat sont conservées : elles sont vérifiées
    # (test_impact_promotions_utilise_le_champ_total_des_ventes).
    list_display = (
        'nom', 'regle_display', 'cible_display', 'etat_display',
        'ventes_stat_display', 'remise_stat_display', 'ca_stat_display',
        'statut_toggle_display',
    )
    search_fields = ('nom', 'code', 'produits__nom', 'categories__nom')
    search_help_text = "Nom, code, produit, catégorie"
    list_filter = (
        EtatPromotionFilter, CreneauFilter, 'type_promotion',
        'type_cible', 'statut', 'date_debut', 'date_fin',
    )
    ordering = ('-created_at',)
    readonly_fields = ('nb_utilisations', 'created_at', 'updated_at')
    filter_horizontal = ('categories',)
    actions = [activer_promotions, desactiver_promotions]
    list_per_page = 25
    add_fieldsets = (
        ('Promotion', {
            'fields': ('nom', 'type_promotion', 'valeur', 'date_debut', 'date_fin', 'statut'),
        }),
    )
    fieldsets = (
        (None, {
            'fields': (
                'nom', 'type_promotion', 'valeur', 'date_debut', 'date_fin',
                'type_cible', 'quantite_min', 'code', 'statut',
                'produits_cibles', 'categories',
            ),
        }),
    )

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self.add_fieldsets
        return self.fieldsets

    def save_model(self, request, obj, form, change):
        if not change:
            obj.statut = form.cleaned_data['statut']
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        produits = form.cleaned_data.get('produits_cibles')
        if produits is None:
            return
        PromotionProduit.objects.filter(promotion=form.instance).delete()
        PromotionProduit.objects.bulk_create(
            PromotionProduit(promotion=form.instance, produit=produit)
            for produit in produits
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:object_id>/toggle-statut/',
                self.admin_site.admin_view(self.toggle_statut_view),
                name='promotions_promotion_toggle_statut'
            ),
        ]
        return custom_urls + urls

    def toggle_statut_view(self, request, object_id):
        """Active ou désactive une promotion en 1 clic depuis la liste ou la fiche."""
        promo = get_object_or_404(Promotion, pk=object_id)
        promo.statut = not promo.statut
        promo.save(update_fields=['statut', 'updated_at'])
        action = "activée" if promo.statut else "désactivée"
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
            return JsonResponse({'success': True, 'statut': promo.statut, 'message': f"Promotion « {promo.nom} » {action}."})
        self.message_user(request, f"La promotion « {promo.nom} » a été {action} avec succès.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER') or reverse('admin:promotions_promotion_changelist'))

    def get_queryset(self, request):
        from apps.ventes.models import Vente
        qs = super().get_queryset(request).prefetch_related('produits', 'categories')
        decimal_remise = DecimalField(max_digits=12, decimal_places=2)
        decimal_ca = DecimalField(max_digits=14, decimal_places=2)
        return qs.annotate(
            nb_ventes_promo=Count(
                'lignes_vente__vente',
                filter=Q(lignes_vente__vente__statut=Vente.Statut.PAYEE, lignes_vente__remise__gt=0),
                distinct=True
            ),
            remise_totale_promo=Coalesce(
                Sum(
                    'lignes_vente__remise',
                    filter=Q(lignes_vente__vente__statut=Vente.Statut.PAYEE, lignes_vente__remise__gt=0)
                ),
                Decimal('0.00'),
                output_field=decimal_remise
            ),
            ca_genere_promo=Coalesce(
                Sum(
                    'lignes_vente__sous_total',
                    filter=Q(lignes_vente__vente__statut=Vente.Statut.PAYEE, lignes_vente__remise__gt=0)
                ),
                Decimal('0.00'),
                output_field=decimal_ca
            ),
        )

    # --- Contexte de la liste ------------------------------------------------

    def get_promotion_alerts(self, qs, now):
        alerts = []

        proches = list(
            qs.filter(statut=True, date_debut__lte=now, date_fin__gte=now)
            .filter(date_fin__lte=now + timedelta(days=7))
            .order_by('date_fin')[:5]
        )
        if proches:
            alerts.append({
                'type': 'warning',
                'icon': 'clock',
                'title': 'Échéances proches',
                'summary': f"{len(proches)} promotion(s) doivent être relancées dans les 7 prochains jours.",
                'items': [
                    {'nom': promo.nom, 'detail': f"Expire le {promo.date_fin.strftime('%d/%m/%Y')}"}
                    for promo in proches
                ],
            })

        sans_produit = list(
            qs.annotate(nb_produits=Count('produits')).filter(nb_produits=0)[:5]
        )
        if sans_produit:
            alerts.append({
                'type': 'info',
                'icon': 'exclamation-triangle',
                'title': 'Promotions sans cible',
                'summary': f"{len(sans_produit)} promotion(s) n'ont ni produit ni catégorie associé et restent "
                           f"difficilement exploitables.",
                'items': [
                    {'nom': promo.nom, 'detail': 'Aucun produit ni catégorie associé'}
                    for promo in sans_produit
                ],
            })

        ouvertes = [p for p in qs.filter(promotions_actives_q())[:100] if happy_hour_active(p)]
        avec_creneau = [p for p in qs.filter(promotions_actives_q())[:100] if p.a_un_creneau]
        if avec_creneau:
            alerts.append({
                'type': 'info',
                'icon': 'clock-o',
                'title': 'Happy hour en cours',
                'summary': f"{len(ouvertes)} créneau(x) ouvert(s) sur {len(avec_creneau)} promotion(s) à horaire "
                           f"au moment présent.",
                'items': [
                    {'nom': p.nom, 'detail': f"{p.creneau_texte} — {p.regle_texte}"}
                    for p in avec_creneau[:5]
                ],
            })

        epuisees = list(
            qs.exclude(code__isnull=True).exclude(code='')
            .filter(limite_utilisation__isnull=False)
            .extra(where=['nb_utilisations >= limite_utilisation'])[:5]
        )
        if epuisees:
            alerts.append({
                'type': 'warning',
                'icon': 'ban',
                'title': 'Codes promo épuisés',
                'summary': f"{len(epuisees)} code(s) ont atteint leur quota d'utilisations et ne "
                           f"s'appliquent plus en caisse.",
                'items': [
                    {'nom': p.nom, 'detail': f"Code {p.code} — {p.nb_utilisations}/{p.limite_utilisation} utilisations"}
                    for p in epuisees
                ],
            })

        return alerts

    def changelist_view(self, request, extra_context=None):
        now = timezone.now()
        qs = self.get_queryset(request)
        actives = qs.filter(promotions_actives_q())
        kpis = {
            'total': qs.count(),
            'actives': actives.count(),
            'a_venir': qs.filter(statut=True, date_debut__gt=now).count(),
            'expirees': qs.filter(statut=True, date_fin__lt=now).count(),
            'bientot_expirees': actives.filter(date_fin__lte=now + timedelta(days=7)).count(),
            'sans_produit': qs.annotate(nb_produits=Count('produits')).filter(nb_produits=0).count(),
            'desactivees': qs.filter(statut=False).count(),
            'produits': PromotionProduit.objects.values('produit').distinct().count(),
            'avec_creneau': sum(1 for p in actives if p.a_un_creneau),
            'avec_code': qs.exclude(code__isnull=True).exclude(code='').count(),
        }
        kpis.update(impact_promotions(jours=30))
        extra_context = extra_context or {}
        extra_context['promotions_kpis'] = kpis
        extra_context['promotions_alerts'] = self.get_promotion_alerts(qs, now)
        extra_context['promotions_top_impact'] = top_promos_impact(limit=5, jours=30)
        extra_context['promotions_par_type'] = repartition_par_type(jours=30)
        extra_context['promotions_par_cible'] = repartition_par_cible(jours=30)
        return super().changelist_view(request, extra_context=extra_context)

    # --- Contexte de la fiche ------------------------------------------------

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['is_promotion_add'] = object_id is None
        if object_id:
            promo = self.get_object(request, object_id)
            if promo is not None:
                extra_context['promo_stats'] = statistiques_promotion(promo)
                extra_context['promo_stats_30j'] = statistiques_promotion(promo, jours=30)
                extra_context['promo_historique'] = promo.lignes_vente.select_related(
                    'vente', 'vente__client', 'produit'
                ).filter(vente__statut='PAYEE').order_by('-vente__date_vente')[:15]
        return super().changeform_view(request, object_id, form_url, extra_context)

    # --- Colonnes de liste ---------------------------------------------------

    @admin.display(description='Remise')
    def regle_display(self, obj):
        if obj.type_promotion == Promotion.TypePromotion.POURCENTAGE:
            return f"-{obj.valeur} %"
        if obj.type_promotion == Promotion.TypePromotion.MONTANT_FIXE:
            return f"-{obj.valeur} {settings.SOCIETE.get('devise', 'Ar')}"
        if obj.type_promotion == Promotion.TypePromotion.PRIX_PROMO:
            return format_html(
                '<span class="lb-val-gold">prix {}{}</span>',
                obj.prix_promotionnel, settings.SOCIETE.get('devise', 'Ar'),
            )
        return format_html(
            '<span class="lb-val-sage">{} = {} offerte</span>',
            obj.quantite_achetee, obj.quantite_offerte,
        )
    regle_display.admin_order_field = 'valeur'

    @admin.display(description='Cible')
    def cible_display(self, obj):
        morceaux = []
        nb_produits = obj.produits.count()
        if nb_produits:
            morceaux.append(f"{nb_produits} vin(s)")
        categories = list(obj.categories.all()[:2])
        if obj.categories.exists():
            noms = ', '.join(c.nom for c in categories)
            if obj.categories.count() > 2:
                noms += f" +{obj.categories.count() - 2}"
            morceaux.append(noms)
        if not morceaux:
            return format_html('<span class="lb-val-wine">{}</span>', '— aucune cible')
        return ', '.join(morceaux)

    @admin.display(description='État')
    def etat_display(self, obj):
        now = timezone.now()
        if not obj.statut:
            cls, libelle = 'desactivee', 'Désactivée'
        elif obj.date_debut > now:
            cls, libelle = 'avenir', 'À venir'
        elif obj.date_fin < now:
            cls, libelle = 'expiree', 'Expirée'
        else:
            cls, libelle = 'active', 'Active'
        return mark_safe(
            f'<span class="pr-etat pr-{cls}">{libelle}</span>'
        )
    etat_display.admin_order_field = 'statut'

    @admin.display(description='Ventes promo', ordering='nb_ventes_promo')
    def ventes_stat_display(self, obj):
        return obj.nb_ventes_promo

    @admin.display(description='Remise accordée', ordering='remise_totale_promo')
    def remise_stat_display(self, obj):
        return format_html(
            '{} {}',
            obj.remise_totale_promo,
            settings.SOCIETE.get('devise', 'Ar'),
        )

    @admin.display(description='CA généré', ordering='ca_genere_promo')
    def ca_stat_display(self, obj):
        return format_html(
            '{} {}',
            obj.ca_genere_promo,
            settings.SOCIETE.get('devise', 'Ar'),
        )

    @admin.display(description='Action')
    def statut_toggle_display(self, obj):
        action = 'Désactiver' if obj.statut else 'Activer'
        icone = 'fa-toggle-on' if obj.statut else 'fa-toggle-off'
        css = 'lb-val-sage' if obj.statut else 'lb-val-muted'
        return format_html(
            '<a class="{}" href="{}" title="{}" aria-label="{}">'
            '<i class="fas {}"></i> {}</a>',
            css,
            reverse('admin:promotions_promotion_toggle_statut', args=[obj.pk]),
            action,
            action,
            icone,
            action,
        )

