import csv
from datetime import timedelta
from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.db.models import Count, DecimalField, F, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse, HttpResponseRedirect
from django.template.loader import render_to_string
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from apps.clients.models import Client, ReglementClient
from apps.dashboard.templatetags.lb_tags import montant
from apps.ventes.models import Vente
from config.admin_mixins import ActionsColonneMixin


SEUIL_RISQUE = Decimal('0.6')
JOURS_INACTIF = 90


def messages_validation_erreur(exc):
    """Transforme une `ValidationError` de DRF en messages affichables.

    `ReglementService` lève l'exception de DRF, qui expose `.detail` (un dict
    par champ, ou une liste) et non `.messages` comme celle de Django. Sans
    cet aplatissement, l'admin afficherait `{'$montant': [ErrorDetail(...)]}`.
    """
    detail = exc.detail
    if isinstance(detail, dict):
        elements = []
        for champ, erreurs in detail.items():
            for erreur in (erreurs if isinstance(erreurs, (list, tuple)) else [erreurs]):
                elements.append(f'{champ} : {erreur}')
        return elements
    return [str(x) for x in (detail if isinstance(detail, (list, tuple)) else [detail])]


class FormEncaissement(forms.Form):
    """Encaissement saisi sur la fiche client.

    Le montant est pré-rempli avec le reste dû par la vue : l'encaissement
    intégral est le cas courant, la saisie la plus courte. Les règles (montant
    strictement positif, jamais supérieur au solde dû) sont appliquées par
    `ReglementService`, donc une seule définition dans tout le projet.
    """

    montant = forms.DecimalField(
        label='Montant encaissé', max_digits=12, decimal_places=2,
        min_value=Decimal('0.01'),
        widget=forms.TextInput(attrs={
            'class': 'form-control lb-input-money',
            'inputmode': 'decimal', 'autocomplete': 'off',
        }),
    )
    mode = forms.ChoiceField(
        label='Mode', choices=ReglementClient.Mode.choices,
        initial=ReglementClient.Mode.ESPECES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    reference_facture = forms.CharField(
        label='Réf. facture', max_length=100, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
    )
    note = forms.CharField(
        label='Note', max_length=255, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
    )


def clients_a_risque(queryset):
    """Encours élevé (≥ 60 % du plafond) ou endetté sans plafond de crédit."""
    return queryset.filter(solde_du__gt=0).filter(
        Q(max_credit__lte=0) | Q(solde_du__gte=F('max_credit') * SEUIL_RISQUE)
    )


def clients_sans_achat(queryset, jours=JOURS_INACTIF):
    """Dernière vente payée plus ancienne que `jours`, ou client sans vente payée.

    Annoter `Max()` puis filtrer : c'est la seule façon de dire « son dernier
    achat est vieux » sans ramener toutes ses ventes en mémoire.
    """
    limite = timezone.now() - timedelta(days=jours)
    return queryset.annotate(
        dernier_paye=Max('ventes__date_vente', filter=Q(ventes__statut=Vente.Statut.PAYEE))
    ).filter(
        Q(dernier_paye__lt=limite)
        | Q(dernier_paye__isnull=True, date_creation__date__lte=limite.date())
    )


# Les critères de la liste (type de client, fidélité, risque, encours, inactivité)
# restent disponibles par paramètres d'URL et pour les KPI. Le bandeau natif de
# filtres Django est retiré du gabarit pour alléger la liste.
class EncoursFilter(admin.SimpleListFilter):
    """« À jour » / « Avec dette »."""

    title = 'encours'
    parameter_name = 'solde_due'

    def lookups(self, request, model_admin):
        return (
            ('1', 'Avec dette'),
            ('0', 'À jour'),
        )

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(solde_du__gt=0)
        if self.value() == '0':
            return queryset.filter(solde_du=0)
        return queryset


class FideliteFilter(admin.SimpleListFilter):
    """Regroupe les niveaux de fidélité, ce que le champ unique ne sait pas faire.

    Le champ « niveau » ne filtre que sur une valeur à la fois : ce filtre permet
    de sélectionner « Fidèles » (= Argent + Or) depuis un paramètre d'URL.
    """

    title = 'fidélité'
    parameter_name = 'fidelite'

    def lookups(self, request, model_admin):
        return (
            ('fidelite', 'Fidèles (Argent + Or)'),
            ('ambassadeur', 'Ambassadeurs (Or)'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'fidelite':
            return queryset.filter(niveau__in=[Client.Niveau.ARGENT, Client.Niveau.OR])
        if self.value() == 'ambassadeur':
            return queryset.filter(niveau=Client.Niveau.OR)
        return queryset


class CreditOuvertFilter(admin.SimpleListFilter):
    """« À risque » : encours élevé (≥ 60 % du plafond) ou sans plafond."""

    title = 'risque'
    parameter_name = 'credit_ouvert'

    def lookups(self, request, model_admin):
        return ('1', 'À risque (encours ≥ 60 % du plafond, ou sans plafond)'),

    def queryset(self, request, queryset):
        return clients_a_risque(queryset) if self.value() == '1' else queryset


class InactifFilter(admin.SimpleListFilter):
    """« Sans achat depuis 90 j » : dernière vente payée ancienne, ou jamais."""

    title = 'achat récent'
    parameter_name = 'inactif_90j'

    def lookups(self, request, model_admin):
        return ('1', f'Sans achat depuis {JOURS_INACTIF} jours'),

    def queryset(self, request, queryset):
        return clients_sans_achat(queryset) if self.value() == '1' else queryset


@admin.register(Client)
class ClientAdmin(ActionsColonneMixin, admin.ModelAdmin):
    change_list_template = 'admin/clients/client/change_list.html'
    change_form_template = 'admin/clients/client/change_form.html'
    # La colonne « Actions » standard (mixin : Modifier / Supprimer / Voir) est
    # conservée ; `contact_actions` n'ajoute que les raccourcis téléphone/WhatsApp.
    # Les informations de fidélité et d'encours restent dans la fiche et les KPI,
    # pas dans le tableau de consultation.
    list_display = (
        'client_display', 'contact_display', 'activite_display', 'contact_actions',
    )
    search_fields = ('nom', 'prenom', 'telephone', 'email', 'adresse')
    # Les critères restent disponibles par paramètres d'URL et par KPI ; le
    # bandeau natif « Filter » est retiré du gabarit. Aucun drill-down par date.
    list_filter = (
        FideliteFilter, CreditOuvertFilter, InactifFilter, EncoursFilter, 'type_client',
    )
    ordering = ('-date_creation',)
    readonly_fields = ('date_creation', 'updated_at', 'points_fidelite', 'niveau', 'solde_du', 'historique')
    list_per_page = 25
    list_select_related = False
    actions = ['actions_export_csv', 'actions_telephone_appel', 'actions_telephone_whatsapp', 'actions_liberer_credit']

    # Un formulaire unique : la création et la modification demandent
    # exactement les mêmes champs (identité, adresse, plafond de crédit). La
    # fenêtre flottante « nouveau client » et l'action « Modifier » affichent
    # donc la même fiche — seule la section 360° (historique) apparaît après
    # le premier enregistrement.
    fieldsets = (
        ('Identité', {'fields': ('nom', 'prenom', 'telephone', 'email')}),
        ('Adresse', {'fields': ('adresse',)}),
        ('Crédit', {'fields': ('max_credit',)}),
        ('Fiche client', {'fields': ('historique',), 'classes': ('lb-full-width',)}),
        ('Dates', {'fields': ('date_creation', 'updated_at'), 'classes': ('collapse',)}),
    )

    def get_fieldsets(self, request, obj=None):
        """
        Mêmes champs à la création et à la modification.

        Les compteurs et la dette (`points_fidelite`, `niveau`, `solde_du`) et
        les dates restent hors saisie : ils sont calculés par les ventes, les
        règlements et le temps. Le type de client reste porté par le modèle,
        le filtre et les KPI sans alourdir la fiche. La fiche 360° (historique,
        encaissement) n'apparaît qu'une fois le client enregistré : un compte
        sans identifiant n'a pas d'historique à montrer.
        """
        if obj is None:
            return tuple(
                fieldset for fieldset in self.fieldsets
                if fieldset[0] not in ('Fiche client', 'Dates')
            )
        return self.fieldsets

    def get_queryset(self, request):
        payee = Q(ventes__statut=Vente.Statut.PAYEE)
        return super().get_queryset(request).annotate(
            nombre_achats=Count('ventes', filter=payee, distinct=True),
            ca_genere=Coalesce(
                Sum('ventes__total', filter=payee),
                Value(Decimal('0.00')),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            total_regle=Coalesce(
                Sum('reglements__montant'),
                Value(Decimal('0.00')),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            dernier_achat=Max('ventes__date_vente', filter=payee),
        )

    def changelist_view(self, request, extra_context=None):
        today = timezone.localdate()
        premier_jour = today.replace(day=1)
        devise = settings.SOCIETE.get('devise', 'Ar')

        base = Client.objects.all()
        payee = Q(ventes__statut=Vente.Statut.PAYEE)

        ca_total = base.aggregate(
            total=Coalesce(
                Sum('ventes__total', filter=payee),
                Value(Decimal('0.00')),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )['total']
        encours = base.aggregate(
            total=Coalesce(
                Sum('solde_du'),
                Value(Decimal('0.00')),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )['total']
        nombre_achats = base.filter(payee).count()
        panier_moyen = (ca_total / nombre_achats) if nombre_achats else Decimal('0.00')

        # « Sans achat 90 j » et « À risque » réutilisent les fonctions des
        # filtres de la page : une seule définition pour les KPI et les filtres.
        # Le comptage se fait sur un queryset annoté à part, sinon l'annotation
        # Max() dupliquerait les lignes de ventes.
        a_risque = clients_a_risque(base).count()
        sans_achat_90j = clients_sans_achat(base).count()

        extra_context = extra_context or {}
        extra_context['devise'] = devise
        extra_context['clients_kpis'] = {
            'total': base.count(),
            'nouveaux_mois': base.filter(date_creation__date__gte=premier_jour).count(),
            'actifs': base.filter(payee).distinct().count(),
            'fideles': base.filter(niveau__in=[Client.Niveau.ARGENT, Client.Niveau.OR]).count(),
            'a_credit': base.filter(solde_du__gt=0).count(),
            'sans_achat_90j': sans_achat_90j,
            'ca_total': ca_total,
            'panier_moyen': panier_moyen,
            'encours': encours,
            'taux_credit': round((encours / ca_total) * 100, 1) if ca_total else 0,
            'revenus': base.filter(type_client=Client.TypeClient.REVENDEUR).count(),
            'professionnels': base.filter(
                type_client__in=[Client.TypeClient.REVENDEUR, Client.TypeClient.RESTAURANT,
                                 Client.TypeClient.HOTEL]
            ).count(),
        }

        return super().changelist_view(request, extra_context=extra_context)

    # ---------- Colonnes de la liste ----------

    @admin.display(description='Client', ordering='nom')
    def client_display(self, obj):
        initiales = ''.join(filter(None, [obj.nom[:1], obj.prenom[:1]])).upper()
        return format_html(
            '<span style="display:flex;align-items:center;gap:.6rem">'
            '<span class="lb-avatar lb-avatar-sm">{}</span>'
            '<span><span class="lb-val-ink">{} {}</span>'
            '<br><span style="color:var(--lb-ink-500);font-size:.74rem">{}</span></span></span>',
            initiales, obj.nom, obj.prenom, obj.get_type_client_display(),
        )

    @admin.display(description='Contact')
    def contact_display(self, obj):
        tel = format_html('<a href="tel:{}" class="lb-val-wine">{}</a>', obj.telephone, obj.telephone)
        mail = format_html('<a href="mailto:{}">{}</a>', obj.email, obj.email) if obj.email else '-'
        return format_html('<span style="font-size:.8rem;line-height:1.5">{}<br>{}</span>', tel, mail)

    @admin.display(description='Activité', ordering='nombre_achats')
    def activite_display(self, obj):
        devise = settings.SOCIETE.get('devise', 'Ar')
        dernier = timezone.localtime(obj.dernier_achat).strftime('%d/%m/%Y') if obj.dernier_achat else 'Jamais'
        return format_html(
            '<span style="font-size:.8rem;line-height:1.5">'
            '<span class="lb-badge lb-badge-gold">{} achat{}</span><br>'
            '<span class="lb-val-wine">{} {}</span>'
            '<br><span style="color:var(--lb-ink-500);font-size:.7rem">Dernier : {}</span></span>',
            obj.nombre_achats, '' if obj.nombre_achats == 1 else 's',
            obj.ca_genere, devise, dernier,
        )

    @admin.display(description='Contact rapide')
    def contact_actions(self, obj):
        return format_html(
            '<span class="lb-row-actions">'
            '<a href="tel:{}" title="Appeler"><i class="fas fa-square-phone-flip"></i></a>'
            '<a href="{}" title="WhatsApp" target="_blank" rel="noopener">'
            '<i class="fab fa-whatsapp"></i></a>'
            '</span>',
            obj.telephone, f'https://wa.me/{obj.telephone.lstrip("+")}',
        )

    @admin.display(description='Fiche client')
    def historique(self, obj):
        """Bloc 360° affiché dans le formulaire de modification."""
        if not obj.pk:
            return 'Enregistrez le client pour voir son historique commercial.'
        devise = settings.SOCIETE.get('devise', 'Ar')
        ventes = Vente.objects.filter(client=obj).order_by('-date_vente')[:10]
        reglements = ReglementClient.objects.filter(client=obj).order_by('-date_reglement')[:10]
        contexte = {
            'obj': obj,
            'ventes': ventes,
            'reglements': reglements,
            'nb_reglements': ReglementClient.objects.filter(client=obj).count(),
            'ca_total': sum((v.total for v in Vente.objects.filter(client=obj, statut=Vente.Statut.PAYEE)), Decimal('0.00')),
            'total_regle': sum((r.montant for r in ReglementClient.objects.filter(client=obj)), Decimal('0.00')),
            'devise': devise,
            'form_encaissement': FormEncaissement(
                initial={'montant': obj.solde_du, 'mode': ReglementClient.Mode.ESPECES},
            ) if obj.solde_du > 0 else None,
        }
        return render_to_string('admin/clients/client/_historique.html', contexte)

    # ---------- Encaissement depuis la fiche client ----------

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:pk>/encaisser/', self.admin_site.admin_view(self.encaisser_view),
                 name='clients_client_encaisser'),
        ]
        return custom_urls + urls

    def encaisser_view(self, request, pk):
        """Enregistre un règlement et revient sur la fiche du client.

        La section « Règlements clients » a disparu du menu : l'encaissement
        se fait là où l'on constate la dette, sur la fiche. Le montant est
        pré-rempli avec le reste dû, donc l'encaissement intégral est le geste
        le plus court et l'erreur la plus coûteuse (encaisser plus que dû) est
        impossible à saisir par megarde.

        Ce bouton est dans le formulaire client, pas dans un formulaire
        imbriqué : un `<form>` dans un `<form>` est du HTML invalide que le
        navigateur jette, et l'encaissement partirait alors vers la fiche
        client. D'où `formaction` sur le bouton, qui envoie la requête vers
        cette vue en réutilisant le jeton CSRF déjà présent.
        """
        client = self.get_object(request, pk)
        url_fiche = reverse('admin:clients_client_change', args=[client.pk])

        if request.method != 'POST':
            return HttpResponseRedirect(url_fiche)

        form = FormEncaissement(request.POST)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    self.message_user(request, erreur, messages.ERROR)
            return HttpResponseRedirect(url_fiche)

        from apps.ventes.services import ReglementService  # évite un cycle d'import

        try:
            reglement = ReglementService.enregistrer(
                client_id=client.pk,
                montant=form.cleaned_data['montant'],
                mode=form.cleaned_data['mode'],
                utilisateur=request.user,
                reference_facture=form.cleaned_data['reference_facture'],
                note=form.cleaned_data['note'],
            )
        except ValidationError as exc:
            for message in messages_validation_erreur(exc):
                self.message_user(request, message, messages.ERROR)
            return HttpResponseRedirect(url_fiche)

        client.refresh_from_db()
        reste = montant(client.solde_du) if client.solde_du > 0 else 'rien'
        self.message_user(
            request,
            f'Règlement de {montant(reglement.montant)} enregistré '
            f'({reglement.get_mode_display()}). Reste dû : {reste}.',
        )
        return HttpResponseRedirect(url_fiche)

    # ---------- Actions de masse ----------

    @admin.action(description='Exporter la sélection en CSV')
    def actions_export_csv(self, request, queryset):
        devise = settings.SOCIETE.get('devise', 'Ar')
        reponse = HttpResponse(content_type='text/csv')
        reponse['Content-Disposition'] = f'attachment; filename="clients_{timezone.now():%Y%m%d}.csv"'
        reponse.write('\ufeff')
        ecrivain = csv.writer(reponse)
        ecrivain.writerow(['Nom', 'Prénom', 'Téléphone', 'Email', 'Type', 'Niveau', 'Points', 'Encours', f'CA ({devise})'])
        for client in queryset:
            ecrivain.writerow([
                client.nom, client.prenom, client.telephone, client.email or '',
                client.get_type_client_display(), client.get_niveau_display(),
                client.points_fidelite, client.solde_du,
                getattr(client, 'ca_genere', 0),
            ])
        return reponse

    @admin.action(description='Ouvrir le lien d\'appel')
    def actions_telephone_appel(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, 'Sélectionnez un seul client pour cette action.', messages.WARNING)
            return None
        return HttpResponseRedirect(f'tel:{queryset.first().telephone}')

    @admin.action(description='Ouvrir la conversation WhatsApp')
    def actions_telephone_whatsapp(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, 'Sélectionnez un seul client pour cette action.', messages.WARNING)
            return None
        return HttpResponseRedirect(f'https://wa.me/{queryset.first().telephone.lstrip("+")}')

    @admin.action(description='Autoriser un plafond de crédit (si aucun)')
    def actions_liberer_credit(self, request, queryset):
        """Accorde le plafond par défaut aux clients qui n'en ont pas.

        Le montant vient de `SOCIETE['credit_plafond_defaut']` : plus de
        constante figée dans le code. Un client déjà plafonné n'est jamais
        modifié, donc l'action ne peut pas augmenter un encours accordé.
        """
        devise = settings.SOCIETE.get('devise', 'Ar')
        montant = Decimal(str(settings.SOCIETE.get('credit_plafond_defaut') or 0))
        if montant <= 0:
            self.message_user(
                request,
                'Aucun plafond par défaut défini : renseignez SOCIETE_CREDIT_PLAFOND_DEFAUT.',
                messages.ERROR,
            )
            return None

        sans_plafond = queryset.filter(max_credit__lte=0)
        modifies = sans_plafond.update(max_credit=montant, updated_at=timezone.now())
        deja_plafonnes = queryset.count() - sans_plafond.count()

        if modifies:
            self.message_user(
                request,
                f'Plafond de {montant} {devise} autorisé pour {modifies} client(s).',
                messages.SUCCESS,
            )
        if deja_plafonnes:
            self.message_user(
                request,
                f'{deja_plafonnes} client(s) déjà plafonné(s) : plafond inchangé '
                f'(modifiez la fiche pour l\'augmenter).',
                messages.WARNING,
            )
        if not modifies and not deja_plafonnes:
            self.message_user(request, 'Aucun client sélectionné.', messages.WARNING)




@admin.register(ReglementClient)
class ReglementClientAdmin(ActionsColonneMixin, admin.ModelAdmin):
    # Un règlement : quand, qui, combien, comment et sur quelle pièce. Le vendeur
    # qui l'a encaissé reste sur la fiche.
    list_display = ('date_reglement', 'client', 'montant_badge', 'mode', 'reference_facture')
    search_fields = ('client__nom', 'client__prenom', 'reference_facture')
    list_filter = ('mode', 'date_reglement')
    autocomplete_fields = ('client',)
    readonly_fields = ('utilisateur', 'date_reglement')
    date_hierarchy = 'date_reglement'
    list_per_page = 25

    class Form(forms.ModelForm):
        class Meta:
            model = ReglementClient
            fields = '__all__'

        def clean(self):
            cleaned = super().clean()
            client = cleaned.get('client')
            montant = cleaned.get('montant')
            if client and montant is not None and montant > client.solde_du:
                self.add_error(
                    'montant',
                    f"Ce règlement dépasse le solde dû du client ({client.solde_du}).",
                )
            return cleaned

    form = Form

    fieldsets = (
        ('Règlement', {'fields': ('client', 'montant', 'mode')}),
        ('Détails', {'fields': ('reference_facture', 'note')}),
        ('Traçabilité', {'fields': ('utilisateur', 'date_reglement'), 'classes': ('collapse',)}),
    )

    def save_model(self, request, obj, form, change):
        if change:
            return  # Les règlements ne se modifient pas : le solde aurait déjà bougé.
        obj.utilisateur = request.user
        obj.save()
        client = obj.client
        client.solde_du = max(client.solde_du - obj.montant, Decimal('0.00'))
        client.save(update_fields=['solde_du', 'updated_at'])

    def has_change_permission(self, request, obj=None):
        """Un encaissement est un fait comptable : on ne le réécrit pas.

        Autoriser l'édition donnerait un formulaire dont l'enregistrement est
        silencieusement ignoré (`save_model`) : l'utilisateur croit avoir
        corrigé, le solde reste faux. La fiche reste consultable (permission
        de lecture) et une erreur se corrige en supprimant l'encaissement, ce
        qui rétablit le solde.
        """
        return False

    def delete_model(self, request, obj):
        """Supprimer un règlement saisi par erreur doit rendre la dette au client.

        Sans ce contrôle, un `DELETE` direct laisserait le client débiteur d'un
        encaissement qui n'existe plus. `ReglementService.supprimer` est
        atomique et rétablit le solde : une seule règle, quel que soit le point
        d'entrée (admin, API, caisse).
        """
        from apps.ventes.services import ReglementService  # évite un cycle d'import

        ReglementService.supprimer(reglement_id=obj.pk)

    @admin.display(description='Montant', ordering='montant')
    def montant_badge(self, obj):
        devise = settings.SOCIETE.get('devise', 'Ar')
        return format_html('<strong class="lb-val-sage">{} {}</strong>', obj.montant, devise)