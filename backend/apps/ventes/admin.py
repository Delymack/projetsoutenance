import csv
import base64
import io
import json
from decimal import Decimal
from datetime import timedelta

from django import forms
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.shortcuts import get_object_or_404, redirect

from apps.clients.models import Client
from apps.produits.models import Produit
from apps.ventes.models import (
    LigneReservation,
    LigneVente,
    MessageClient,
    Paiement,
    Reservation,
    RetourVente,
    SessionCaisse,
    Vente,
)
from apps.ventes.services import CaisseService, ReservationService, VenteService
from config.admin_mixins import ActionsColonneMixin


def _notifier_erreur_validation(modeladmin, request, exc):
    """Affiche une ValidationError (Django ou DRF) en messages lisibles.

    `ReservationService` lève `rest_framework.exceptions.ValidationError`
    (attribut `.detail` : dict champ → liste d'ErrorDetail) tandis que les
    formulaires lèvent `django.core.exceptions.ValidationError` (attribut
    `.messages`). Sans ce formateur, l'admin affichait le dict brut :
    `{'validation_statut': ErrorDetail(...)}`.
    """
    detail = getattr(exc, 'detail', None)
    if isinstance(detail, dict):
        for champ, erreurs in detail.items():
            if not isinstance(erreurs, (list, tuple)):
                erreurs = [erreurs]
            for erreur in erreurs:
                modeladmin.message_user(request, f'{champ} : {erreur}', level='error')
        return
    messages = getattr(exc, 'messages', None)
    if messages:
        for message in messages:
            modeladmin.message_user(request, message, level='error')
        return
    modeladmin.message_user(request, str(exc), level='error')


class ReservationManuelleForm(forms.Form):
    client = forms.ModelChoiceField(queryset=Client.objects.order_by('nom', 'prenom'))
    mode_reception = forms.ChoiceField(choices=Reservation.ModeReception.choices)
    adresse_livraison = forms.CharField(required=False, max_length=1000)
    date_expiration = forms.DateField(
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        initial=lambda: timezone.localdate() + timedelta(days=7),
    )
    note = forms.CharField(required=False, max_length=255)
    lignes = forms.CharField(widget=forms.HiddenInput())

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get('mode_reception') == Reservation.ModeReception.LIVRAISON
            and not cleaned.get('adresse_livraison', '').strip()
        ):
            self.add_error('adresse_livraison', 'Une adresse est obligatoire pour une livraison.')
        return cleaned


@admin.action(description='Annuler les ventes sélectionnées (restaure le stock)')
def annuler_ventes_massives(modeladmin, request, queryset):
    count = 0
    for vente in queryset:
        if vente.statut != Vente.Statut.ANNULEE:
            VenteService.annuler_vente(vente.id)
            count += 1
    modeladmin.message_user(request, f"{count} vente(s) annulée(s) et stocks restaurés.")


@admin.action(description='Exporter les ventes en CSV (Tableur)')
def exporter_csv(modeladmin, request, queryset):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="export_ventes.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'Reference', 'Client', 'Vendeur', 'Date', 'Mode de Paiement',
        'Detail encaissements', 'Statut', 'Total', 'Remise manuelle',
        'Net rembourse', 'Acompte anticipé', 'Date d’échéance', 'Taux TVA', 'Montant TVA',
    ])
    for vente in queryset:
        detail = ' + '.join(
            f"{p.mode} {p.montant}" for p in vente.paiements.all()
        ) or vente.get_mode_paiement_display()
        details_tva = vente.details_tva
        writer.writerow([
            vente.reference,
            vente.nom_client,
            vente.utilisateur.username,
            vente.date_vente.strftime("%Y-%m-%d %H:%M"),
            vente.get_mode_paiement_display(),
            detail,
            vente.get_statut_display(),
            vente.total,
            vente.remise_manuelle_totale,
            vente.montant_retourne,
            vente.acompte_anticipe,
            vente.date_echeance.isoformat() if vente.date_echeance else '',
            vente.taux_tva if vente.taux_tva is not None else '',
            details_tva['tva'] if details_tva else '',
        ])
    return response


class PaiementInline(admin.TabularInline):
    """Détail des encaissements : c'est la source de vérité du rapport de caisse."""
    model = Paiement
    extra = 0
    fields = ('mode', 'montant', 'created_at', 'reservation', 'reference')
    readonly_fields = ('created_at', 'reference')
    autocomplete_fields = ('reservation',)


class RetourVenteInline(admin.TabularInline):
    model = RetourVente
    extra = 0
    fields = ('date_retour', 'utilisateur', 'ligne', 'quantite', 'montant_rembourse', 'mode_remboursement', 'motif')
    readonly_fields = ('date_retour', 'utilisateur', 'ligne', 'quantite', 'montant_rembourse', 'mode_remboursement')
    show_change_link = True


class LigneVenteInline(admin.TabularInline):
    model = LigneVente
    extra = 0
    readonly_fields = ('produit', 'quantite', 'unite', 'prix_unitaire_display', 'remise_display', 'sous_total_display', 'promotion_display', 'remise_manuelle_ligne_display')
    can_delete = False
    show_change_link = True

    def prix_unitaire_display(self, obj):
        unite = f" / {obj.get_unite_display()}" if obj.unite != LigneVente.Unite.BOUTEILLE else ""
        return f"{obj.prix_unitaire} {settings.SOCIETE.get('devise', 'Ar')}{unite}"
    def remise_display(self, obj):
        return f"{obj.remise} {settings.SOCIETE.get('devise', 'Ar')}"
    def sous_total_display(self, obj):
        return format_html('<b class="lb-val-sage">{} {}</b>', obj.sous_total, settings.SOCIETE.get('devise', 'Ar'))
    def promotion_display(self, obj):
        if not obj.promotion:
            return format_html('<span class="lb-val-muted">{}</span>', '—')
        return format_html('<span class="lb-badge lb-badge-gold">{}</span>', obj.promotion.nom)
    def remise_manuelle_ligne_display(self, obj):
        if not obj.remise_manuelle:
            return format_html('<span class="lb-val-muted">{}</span>', '—')
        return format_html('<span class="lb-badge lb-badge-wine">-{}</span>', obj.remise_manuelle)

    prix_unitaire_display.short_description = "PU"
    remise_display.short_description = "Remise"
    sous_total_display.short_description = "Sous-total"
    promotion_display.short_description = "Promotion"
    remise_manuelle_ligne_display.short_description = "Remise"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Vente)
class VenteAdmin(ActionsColonneMixin, admin.ModelAdmin):
    change_list_template = 'admin/ventes/vente/change_list.html'
    list_display = (
        'reference', 'client_affiche', 'total_badge', 'statut_badge',
        'date_vente', 'date_echeance', 'imprimer_facture',
    )
    search_fields = ('reference', 'client__nom', 'client__prenom', 'client_libelle')
    list_filter = ('statut', 'date_vente', 'date_echeance')
    ordering = ('-date_vente',)
    readonly_fields = (
        'reference', 'total', 'montant_retourne', 'date_echeance', 'taux_tva', 'tva_incluse',
        'date_vente', 'created_at', 'updated_at',
        'paiements_display', 'net_a_encaiser_display',
    )
    autocomplete_fields = ('client', 'utilisateur', 'session')
    inlines = [PaiementInline, LigneVenteInline, RetourVenteInline]
    date_hierarchy = 'date_vente'
    list_per_page = 20
    actions = [annuler_ventes_massives, exporter_csv]

    def get_queryset(self, request):
        """Évite une requête supplémentaire par vente et par ligne affichée."""
        return super().get_queryset(request).select_related(
            'client', 'utilisateur', 'session'
        ).prefetch_related('lignes', 'paiements', 'retours')

    @admin.display(description='Client', ordering='client__nom')
    def client_affiche(self, obj):
        """Fiche client, nom libre du client de passage, ou mention anonyme."""
        if obj.client_id:
            return f"{obj.client.nom} {obj.client.prenom}".strip()
        if obj.client_libelle:
            return f"{obj.client_libelle} (de passage)"
        return 'Client de passage'

    fieldsets = (
        ('Vente', {
            'fields': (
                'reference', 'statut', 'mode_paiement', 'paiements_display', 'total',
                'date_echeance', 'taux_tva', 'tva_incluse',
                'montant_retourne', 'net_a_encaiser_display', 'remise_manuelle_totale',
                'motif_remise', 'acompte_anticipe',
            )
        }),
        ('Client', {
            'fields': ('client', 'client_libelle', 'utilisateur', 'session')
        }),
        ('Dates', {
            'fields': ('date_vente', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Encaissements')
    def paiements_display(self, obj):
        if not obj.paiements.exists():
            return format_html('<span class="lb-val-muted">{}</span>', 'Aucun détail (vente antérieure)')
        morceaux = [
            format_html('<span class="lb-badge lb-badge-muted">{} {}</span>', p.mode, p.montant)
            for p in obj.paiements.all()
        ]
        return format_html('<div style="display:flex;flex-wrap:wrap;gap:4px">{}</div>', *morceaux)

    @admin.display(description='Net à payer')
    def net_a_encaiser_display(self, obj):
        return f"{obj.total_net} {settings.SOCIETE.get('devise', 'Ar')}"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:vente_id>/facture/', self.admin_site.admin_view(self.facture_view), name='vente-facture'),
        ]
        return custom_urls + urls

    def facture_view(self, request, vente_id):
        vente = get_object_or_404(
            Vente.objects.select_related('client', 'utilisateur', 'session')
            .prefetch_related('lignes__produit', 'paiements', 'retours'),
            pk=vente_id,
        )
        format_impression = request.GET.get('format')
        # `LigneVente.remise` contient déjà la somme des deux natures de remise
        # (promotion automatique + geste commercial manuel) : l'additionner à
        # nouveau avec `remise_manuelle` compterait le geste deux fois.
        total_remise = sum(
            (ligne.remise for ligne in vente.lignes.all()),
            Decimal('0.00'),
        )
        context = dict(
            self.admin_site.each_context(request),
            vente=vente,
            compact=format_impression == 'compact',
            qr_code=self._facture_qr(vente),
            total_remise=total_remise,
            ticket_80mm=format_impression == 'ticket80',
        )
        return TemplateResponse(request, "admin/facture.html", context)

    @staticmethod
    def _facture_qr(vente):
        """Génère un QR code PNG (data URI) résumant la facture pour vérification."""
        try:
            import segno
        except ImportError:
            return None
        contenu = (
            f"FACTURE:{vente.reference}|DATE:{vente.date_vente:%Y-%m-%d %H:%M}"
            f"|TOTAL:{vente.total}|STATUT:{vente.get_statut_display()}"
        )
        qr = segno.make(contenu, error='m')
        buffer = io.BytesIO()
        qr.save(buffer, kind='png', scale=4, border=2)
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

    def imprimer_facture(self, obj):
        return format_html(
            '<a class="btn btn-sm btn-info" href="{}"><i class="fas fa-print"></i> Facture</a>',
            f'/admin/ventes/vente/{obj.id}/facture/'
        )
    imprimer_facture.short_description = "Imprimer"

    def total_badge(self, obj):
        return format_html('<b class="lb-val-wine" style="font-size:14px">{} {}</b>', obj.total, settings.SOCIETE.get('devise', 'Ar'))
    total_badge.short_description = 'Total'
    total_badge.admin_order_field = 'total'

    def statut_badge(self, obj):
        css = {
            Vente.Statut.PAYEE: 'lb-badge-sage',
            Vente.Statut.ANNULEE: 'lb-badge-wine',
        }.get(obj.statut, 'lb-badge-muted')
        icone = 'fa-check' if obj.statut == Vente.Statut.PAYEE else 'fa-ban'
        return format_html(
            '<span class="lb-badge {}"><i class="fas {}"></i>{}</span>', css, icone, obj.get_statut_display()
        )
    statut_badge.short_description = 'Statut'
    statut_badge.admin_order_field = 'statut'

    def has_add_permission(self, request):
        return False


class LigneReservationInline(admin.TabularInline):
    model = LigneReservation
    extra = 0
    readonly_fields = ('produit', 'quantite', 'unite', 'contenance', 'unit_price_display')
    autocomplete_fields = ('produit',)
    show_change_link = True

    @admin.display(description='Prix unitaire')
    def unit_price_display(self, obj):
        return f"{obj.prix_unitaire} {settings.SOCIETE.get('devise', 'Ar')}"


@admin.register(Reservation)
class ReservationAdmin(ActionsColonneMixin, admin.ModelAdmin):
    change_list_template = 'admin/ventes/reservation/change_list.html'
    change_form_template = 'admin/ventes/reservation/change_form.html'
    # La liste montre le suivi immédiat. Le mode de réception et la date
    # d'expiration restent accessibles dans la fiche de la commande.
    list_display = (
        'reference', 'source_badge', 'client_badge', 'statut_badge',
        'actions_reservation',
    )
    list_filter = ('statut', 'validation_statut', 'source', 'date_expiration', 'date_creation')
    search_fields = ('reference', 'client__nom', 'client__prenom', 'client__telephone', 'note')
    autocomplete_fields = ('client', 'utilisateur', 'vente')
    readonly_fields = (
        'reference', 'source', 'solde_du', 'statut', 'taux_tva', 'tva_incluse',
        'date_creation', 'updated_at', 'statut_badge', 'validation_badge', 'lignes_resume',
    )
    inlines = [LigneReservationInline]
    ordering = ('-date_creation',)
    date_hierarchy = 'date_creation'
    list_per_page = 25
    fieldsets = (
        ('Commande', {
            'fields': (
                'client', 'montant_total', 'montant_acompte', 'taux_tva',
                'tva_incluse', 'mode_reception', 'adresse_livraison',
                'date_expiration',
            ),
        }),
        ('Commandé', {'fields': ('lignes_resume',)}),
        ('Suivi', {'fields': ('source', 'statut_badge', 'validation_badge', 'solde_du', 'vente', 'statut', 'reference')}),
        ('Traçabilité', {
            'fields': ('utilisateur', 'note', 'date_creation', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('client', 'utilisateur', 'vente').prefetch_related('lignes')

    def add_view(self, request, form_url='', extra_context=None):
        return redirect('admin:commande-manuelle')

    def has_add_permission(self, request):
        return False

    def commande_manuelle_view(self, request):
        if not request.user.has_perm('ventes.add_reservation'):
            raise PermissionDenied

        form = ReservationManuelleForm(request.POST or None)
        produits = list(
            Produit.objects.filter(statut=True, stock__quantite__gt=0)
            .select_related('stock').order_by('nom')
        )
        erreur = ''
        if request.method == 'POST' and form.is_valid():
            try:
                lignes = json.loads(form.cleaned_data['lignes'])
                if not isinstance(lignes, list) or not lignes:
                    raise ValueError
                lignes_data = [
                    {
                        'produit_id': int(ligne['produit_id']),
                        'quantite': int(ligne['quantite']),
                        'unite': ligne.get('unite', 'BOUTEILLE'),
                    }
                    for ligne in lignes
                ]
                if any(ligne['quantite'] < 1 for ligne in lignes_data):
                    raise ValueError
                reservation = ReservationService.creer(
                    client_id=form.cleaned_data['client'].pk,
                    lignes_data=lignes_data,
                    utilisateur=request.user,
                    date_expiration=form.cleaned_data['date_expiration'],
                    note=form.cleaned_data['note'].strip(),
                    source=Reservation.Source.INTERNE,
                    mode_reception=form.cleaned_data['mode_reception'],
                    adresse_livraison=form.cleaned_data['adresse_livraison'].strip(),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                erreur = 'Le panier est vide ou invalide.'
            except Exception as exc:
                erreur = str(exc)
            else:
                self.message_user(request, f'Commande {reservation.reference} créée.', level='success')
                return redirect(reverse('admin:ventes_reservation_change', args=[reservation.pk]))

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': 'Nouvelle commande client manuelle',
            'form': form,
            'produits': produits,
            'erreur': erreur,
            'devise': settings.SOCIETE.get('devise', 'Ar'),
        }
        return TemplateResponse(request, 'admin/ventes/reservation/commande_manuelle.html', context)

    @admin.display(description='Client', ordering='client__nom')
    def client_badge(self, obj):
        return format_html(
            '<b>{} {}</b><br><small style="color:var(--lb-ink-500)">{}</small>',
            obj.client.nom, obj.client.prenom, obj.client.telephone or '—',
        )

    @admin.display(description='Origine', ordering='source')
    def source_badge(self, obj):
        if obj.source == Reservation.Source.SITE:
            return format_html('<span class="lb-badge lb-badge-gold">{}</span>', 'Site web')
        return format_html('<span class="lb-badge lb-badge-muted">{}</span>', 'Saisie interne')

    @admin.display(description='Réception', ordering='mode_reception')
    def reception_badge(self, obj):
        adresse = obj.adresse_livraison if obj.mode_reception == Reservation.ModeReception.LIVRAISON else ''
        return format_html(
            '<strong>{}</strong>{}',
            obj.get_mode_reception_display(),
            format_html('<br><small>{}</small>', adresse) if adresse else '',
        )

    @admin.display(description='Statut', ordering='statut')
    def statut_badge(self, obj):
        styles = {
            Reservation.Statut.EN_ATTENTE: ('lb-badge-muted', 'fa-hourglass-half'),
            Reservation.Statut.ACOMPTE: ('lb-badge-gold', 'fa-coins'),
            Reservation.Statut.SOLDEE: ('lb-badge-sage', 'fa-check'),
            Reservation.Statut.ANNULEE: ('lb-badge-wine', 'fa-ban'),
            Reservation.Statut.EXPIREE: ('lb-badge-muted', 'fa-clock'),
        }
        css, icone = styles.get(obj.statut, ('lb-badge-muted', 'fa-circle'))
        return format_html(
            '<span class="lb-badge {}"><i class="fas {}"></i>{}</span>', css, icone, obj.get_statut_display()
        )

    @admin.display(description='Validation', ordering='validation_statut')
    def validation_badge(self, obj):
        """Pastille de validation vendeur : le caissier voit d'un coup d'œil
        si la commande du site peut être encaissée."""
        if obj.source != Reservation.Source.SITE:
            return format_html('<span class="lb-val-muted">{}</span>', '—')
        styles = {
            Reservation.ValidationStatut.A_VALIDER: ('lb-badge-gold', 'fa-hourglass-half', 'À valider'),
            Reservation.ValidationStatut.VALIDEE: ('lb-badge-sage', 'fa-check', 'Validée'),
            Reservation.ValidationStatut.REFUSEE: ('lb-badge-wine', 'fa-ban', 'Refusée'),
        }
        css, icone, libelle = styles.get(
            obj.validation_statut, ('lb-badge-muted', 'fa-circle', obj.get_validation_statut_display() or '—')
        )
        detail = ''
        if obj.validation_par:
            detail = format_html(
                '<br><small>par {} le {}</small>',
                obj.validation_par,
                obj.validation_le.strftime('%d/%m/%Y %H:%M') if obj.validation_le else '—',
            )
        if obj.validation_statut == Reservation.ValidationStatut.REFUSEE and obj.motif_refus:
            detail = format_html('<br><small>Motif : {}</small>', obj.motif_refus)
        return format_html(
            '<span class="lb-badge {}"><i class="fas {}"></i>{}</span>{}',
            css, icone, libelle, detail,
        )

    @admin.display(description='Pour le', ordering='date_expiration')
    def date_expiration_badge(self, obj):
        aujourd_hui = timezone.localdate()
        if obj.statut in (Reservation.Statut.SOLDEE, Reservation.Statut.ANNULEE):
            return obj.date_expiration
        if not obj.date_expiration:
            return '—'
        jours = (obj.date_expiration - aujourd_hui).days
        if jours < 0:
            return format_html('<b class="lb-val-wine">{} (échue)</b>', obj.date_expiration)
        if jours <= 2:
            return format_html('<b class="lb-val-gold">{} (J-{})</b>', obj.date_expiration, jours)
        return obj.date_expiration

    @admin.display(description='Contenu')
    def lignes_resume(self, obj):
        if not obj.lignes.exists():
            return format_html('<span class="lb-val-muted">{}</span>', '—')
        morceaux = [
            format_html('<span style="font-size:11px">{} × {}</span>', l.produit.nom, l.quantite)
            for l in obj.lignes.all()[:6]
        ]
        reste = obj.lignes.count() - 6
        if reste > 0:
            morceaux.append(format_html('<span class="lb-val-muted" style="font-size:11px">+{}</span>', reste))
        return format_html('<div style="display:flex;flex-wrap:wrap;gap:4px">{}</div>', *morceaux)

    @admin.display(description='Opérations')
    def actions_reservation(self, obj):
        boutons = []
        a_valider = (
            obj.source == Reservation.Source.SITE
            and obj.validation_statut == Reservation.ValidationStatut.A_VALIDER
        )
        encaissable = obj.statut in (Reservation.Statut.EN_ATTENTE, Reservation.Statut.ACOMPTE)
        if a_valider and encaissable:
            # Commande du site non validée : on propose Valider ou Refuser, pas Encaisser.
            # Encaisser lèverait « Un vendeur doit valider avant encaissement ».
            boutons.append(format_html(
                '<a class="btn btn-sm btn-warning" href="{}"><i class="fas fa-check"></i> Valider</a>',
                f'/admin/ventes/reservation/{obj.id}/valider/'),
            )
            boutons.append(format_html(
                '<a class="btn btn-sm btn-danger" href="{}"><i class="fas fa-times-circle"></i> Refuser</a>',
                f'/admin/ventes/reservation/{obj.id}/refuser/'),
            )
        elif encaissable:
            boutons.append(format_html(
                '<a class="btn btn-sm btn-success" href="{}"><i class="fas fa-cash-register"></i> Encaisser</a>',
                f"{reverse('caisse-enregistreuse')}?reservation={obj.pk}"),
            )
        if obj.statut == Reservation.Statut.SOLDEE:
            boutons.append(format_html(
                '<a class="btn btn-sm btn-info" href="{}"><i class="fas fa-receipt"></i> Ticket</a>',
                f'/admin/ventes/vente/{obj.vente_id}/facture/') if obj.vente_id else '')
        if obj.statut not in (Reservation.Statut.SOLDEE, Reservation.Statut.ANNULEE):
            boutons.append(format_html(
                '<a class="btn btn-sm btn-danger" href="{}"><i class="fas fa-ban"></i> Annuler</a>',
                f'/admin/ventes/reservation/{obj.id}/annuler/'),
            )
        return format_html(
            '<div style="display:flex;flex-wrap:wrap;gap:4px">{}</div>',
            mark_safe(''.join(str(b) for b in boutons if b)),
        )

    actions_reservation.short_description = 'Opérations'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('commande-manuelle/', self.admin_site.admin_view(self.commande_manuelle_view), name='commande-manuelle'),
            path('<int:pk>/valider/', self.admin_site.admin_view(self.valider_view), name='reservation-valider'),
            path('<int:pk>/refuser/', self.admin_site.admin_view(self.refuser_view), name='reservation-refuser'),
            path('<int:pk>/encaisser/', self.admin_site.admin_view(self.encaisser_view), name='reservation-encaisser'),
            path('<int:pk>/annuler/', self.admin_site.admin_view(self.annuler_view), name='reservation-annuler'),
        ]
        return custom_urls + urls

    def valider_view(self, request, pk):
        """Valide une commande du site (sans encaisser ni toucher le stock)."""
        from django.shortcuts import redirect
        from django.urls import reverse

        reservation = get_object_or_404(Reservation, pk=pk)
        try:
            ReservationService.valider(reservation.id, request.user)
        except Exception as exc:  # noqa: BLE001 - ValidationError Django ou DRF
            _notifier_erreur_validation(self, request, exc)
            return redirect(reverse('admin:ventes_reservation_change', args=[pk]))
        self.message_user(request, f'Commande {reservation.reference} validée. Elle peut être encaissée.', level='success')
        return redirect(reverse('admin:ventes_reservation_change', args=[pk]))

    def refuser_view(self, request, pk):
        """
        Refuse une commande du site avec un motif obligatoire.

        Contrairement à valider/annuler, le refus exige une explication (5
        caractères minimum, imposés par le service) : on affiche donc un petit
        formulaire de confirmation en GET avant d'appliquer le refus en POST.
        """
        from django.urls import reverse

        reservation = get_object_or_404(Reservation, pk=pk)
        if request.method == 'POST':
            motif = request.POST.get('motif', '')
            try:
                ReservationService.refuser(reservation.id, request.user, motif)
            except Exception as exc:  # noqa: BLE001 - ValidationError Django ou DRF, message lisible
                _notifier_erreur_validation(self, request, exc)
                return redirect(reverse('admin:ventes_reservation_change', args=[pk]))
            self.message_user(
                request,
                f'Commande {reservation.reference} refusée. Le client en sera informé.',
                level='success',
            )
            return redirect(reverse('admin:ventes_reservation_changelist'))

        return TemplateResponse(request, 'admin/ventes/reservation/refuser.html', {
            'reservation': reservation,
            'opts': self.model._meta,
            'title': 'Refuser la commande',
        })

    def encaisser_view(self, request, pk):
        """
        Encaisse une commande en totalité, en espèces.

        L'encaissement complet est le seul geste possible depuis l'admin : les
        paiements partiels et le choix du mode se font à la caisse, qui dispose
        du terminal de paiement.
        """
        from django.core.exceptions import ValidationError
        from django.shortcuts import redirect
        from django.urls import reverse

        reservation = get_object_or_404(Reservation, pk=pk)
        try:
            # `encaisser` renvoie (vente, reservation) : sans déballage,
            # `vente.reference` lèverait un AttributeError après l'encaissement.
            vente, _reservation = ReservationService.encaisser(
                reservation.id,
                mode_paiement=Vente.ModePaiement.ESPECES,
                utilisateur=request.user,
            )
        except Exception as exc:  # noqa: BLE001 - ValidationError Django ou DRF, message lisible
            # `_notifier_erreur_validation` couvre déjà les trois formes possibles :
            # dict DRF (`.detail`), messages Django (`.messages`) et repli `str(exc)`.
            _notifier_erreur_validation(self, request, exc)
            return redirect(reverse('admin:ventes_reservation_change', args=[pk]))
        self.message_user(request, f"Vente {vente.reference} créée pour la commande {reservation.reference}.")
        return redirect(reverse('admin:ventes_vente_change', args=[vente.id]))

    def annuler_view(self, request, pk):
        from django.core.exceptions import ValidationError
        from django.shortcuts import redirect
        from django.urls import reverse

        reservation = get_object_or_404(Reservation, pk=pk)
        try:
            ReservationService.annuler(reservation.id)
            self.message_user(request, f"Commande {reservation.reference} annulée.")
        except Exception as exc:  # noqa: BLE001 - ValidationError Django ou DRF, message lisible
            _notifier_erreur_validation(self, request, exc)
        return redirect(reverse('admin:ventes_reservation_change', args=[pk]))


@admin.register(MessageClient)
class MessageClientAdmin(ActionsColonneMixin, admin.ModelAdmin):
    change_form_template = 'admin/ventes/messageclient/change_form.html'
    list_display = ('sujet', 'nom', 'telephone', 'statut', 'cree_le', 'repondu_le')
    list_filter = ('statut', 'cree_le')
    search_fields = ('nom', 'telephone', 'email', 'sujet', 'message', 'reponse')
    readonly_fields = (
        'nom', 'telephone', 'email', 'compte_client', 'sujet',
        'message_original_display', 'cree_le', 'repondu_le',
    )
    fieldsets = (
        ('Coordonnées du client', {
            'fields': ('nom', 'email', 'telephone', 'compte_client', 'cree_le'),
            'classes': ('wine-message-sender',),
        }),
        ('Message reçu', {
            'fields': ('sujet', 'message_original_display'),
            'classes': ('wine-message-original',),
        }),
        ('Votre réponse', {
            'fields': ('reponse', 'repondu_le', 'statut'),
            'classes': ('wine-message-reply',),
        }),
    )
    ordering = ('-cree_le',)
    date_hierarchy = 'cree_le'

    def get_fieldsets(self, request, obj=None):
        if request.GET.get('repondre') == '1':
            return (
                self.fieldsets[1],
                ('Votre réponse', {'fields': ('reponse',), 'classes': ('wine-message-reply',)}),
            )
        return super().get_fieldsets(request, obj)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'reponse':
            kwargs['widget'] = forms.Textarea(attrs={
                'rows': 7,
                'maxlength': 3000,
                'placeholder': 'Rédigez une réponse claire et personnalisée au client…',
                'class': 'wine-message-reply-input',
                'data-message-reply': 'true',
            })
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description='Message du client')
    def message_original_display(self, obj):
        return format_html('<div class="wine-message-original-text">{}</div>', obj.message)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        obj = self.get_object(request, object_id)
        if obj is not None and self.has_view_or_change_permission(request, obj):
            from apps.accounts.models import UserNotification

            UserNotification.objects.update_or_create(
                user=request.user,
                key=f'message-client:{obj.pk}',
                defaults={'etat': UserNotification.Etat.LUE},
            )
        return super().change_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        if change and 'reponse' in form.changed_data:
            from django.utils import timezone

            obj.repondu_le = timezone.now() if obj.reponse.strip() else None
            if obj.reponse.strip() and obj.statut == MessageClient.Statut.NOUVEAU:
                obj.statut = MessageClient.Statut.TRAITE
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        return False


@admin.register(SessionCaisse)
class SessionCaisseAdmin(ActionsColonneMixin, admin.ModelAdmin):
    # Une session de caisse : quand, dans quel état, combien encaissé, combien de
    # tickets, l'écart, la clôture. Le fonds, l'attendu, les articles et le vendeur
    # sont sur la fiche.
    list_display = ('date_ventes', 'statut_badge', 'ca_total_badge', 'ecart_badge', 'date_cloture')
    list_filter = ('statut', 'date_ventes')
    search_fields = ('utilisateur__username', 'note')
    readonly_fields = [f.name for f in SessionCaisse._meta.fields] + ['duree_display', 'paiements_resume']
    date_hierarchy = 'date_ventes'
    list_per_page = 25
    # Une session de caisse, dans l'ordre où on la relit : la journée et son
    # état, ce qui est entré par mode de paiement, les totaux, puis le comptage.
    # Tout est en lecture seule : la caisse est la seule à écrire ici.
    fieldsets = (
        ('Session', {
            'fields': ('date_ventes', 'statut', 'utilisateur', 'date_ouverture', 'date_cloture', 'duree_display'),
        }),
        ('Encaissements', {
            'fields': ('ca_especes', 'ca_mobile_money', 'ca_carte', 'ca_credit', 'paiements_resume'),
        }),
        ('Totaux', {
            'fields': (
                'ca_total', 'ca_rembourse', 'ca_net', 'nb_tickets', 'nb_articles',
                'nb_retours', 'remise_totale', 'remise_manuelle_totale',
            ),
        }),
        ('Comptage de caisse', {
            'fields': ('fonds_de_caisse', 'especes_reel', 'ecart', 'note'),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('utilisateur')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='État', ordering='statut')
    def statut_badge(self, obj):
        if obj.statut == SessionCaisse.Statut.OUVERTE:
            return format_html(
                '<span class="lb-badge lb-badge-sage"><i class="fas fa-lock-open"></i>{}</span>',
                obj.get_statut_display(),
            )
        return format_html(
            '<span class="lb-badge lb-badge-muted"><i class="fas fa-lock"></i>{}</span>',
            obj.get_statut_display(),
        )

    @admin.display(description='CA', ordering='ca_total')
    def ca_total_badge(self, obj):
        return format_html('<strong class="lb-val-wine">{} {}</strong>', obj.ca_total, settings.SOCIETE.get('devise', 'Ar'))

    @admin.display(description='Écart', ordering='ecart')
    def ecart_badge(self, obj):
        css = 'lb-val-sage' if obj.ecart == 0 else 'lb-val-wine'
        return format_html(
            '<span class="{}">{} {}</span>', css, obj.ecart, settings.SOCIETE.get('devise', 'Ar')
        )

    @admin.display(description='Durée')
    def duree_display(self, obj):
        if not obj.date_ouverture:
            return '—'
        fin = obj.date_cloture or timezone.now()
        duree = fin - obj.date_ouverture
        heures, reste = divmod(int(duree.total_seconds()), 3600)
        return f'{heures}h{reste // 60:02d}'

    @admin.display(description='Encaissements')
    def paiements_resume(self, obj):
        rapport = CaisseService.rapport_du_jour(obj.date_ventes)
        devise = settings.SOCIETE.get('devise', 'Ar')
        lignes = [
            (Vente.ModePaiement.ESPECES, rapport['ca_especes']),
            (Vente.ModePaiement.MOBILE_MONEY, rapport['ca_mobile_money']),
            (Vente.ModePaiement.CARTE, rapport['ca_carte']),
            (Vente.ModePaiement.CREDIT, rapport['ca_credit']),
        ]
        morceaux = [
            format_html(
                '<span class="lb-badge lb-badge-muted">{} {}</span>',
                dict(Vente.ModePaiement.choices).get(mode, mode), montant,
            )
            for mode, montant in lignes
        ]
        acompte = rapport.get('acompte_caisses') or Decimal('0')
        if acompte:
            morceaux.append(format_html(
                '<span class="lb-badge lb-badge-gold">Acomptes réserv. {}</span>', acompte,
            ))
        return format_html('<div style="display:flex;flex-wrap:wrap;gap:4px">{}</div>', *morceaux)
