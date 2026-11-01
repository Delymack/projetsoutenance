import csv

from django import forms
from django.contrib import admin
from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html

from apps.produits.barcode import cle_ean13_valide, code_svg
from apps.produits.images import ImageDistanteInvalide, telecharger_image
from apps.produits.models import Produit
from apps.promotions.models import PromotionProduit
from apps.stocks.models import Stock
from config.admin_mixins import ActionsColonneMixin


@admin.action(description='Générer les codes-barres des produits sélectionnés')
def generer_codes_barres(modeladmin, request, queryset):
    generes, ignores = 0, 0
    for produit in queryset:
        if produit.code_barre:
            ignores += 1
            continue
        produit.attribuer_code_barre()
        produit.save(update_fields=['code_barre'])
        generes += 1
    message = f'{generes} code(s) généré(s).'
    if ignores:
        message += f' {ignores} produit(s) déjà codés, laissés intacts.'
    modeladmin.message_user(request, message, 'success')


@admin.action(description='Marquer les produits sélectionnés comme Indisponibles')
def rendre_indisponible(modeladmin, request, queryset):
    updated = queryset.update(statut=False)
    modeladmin.message_user(request, f'{updated} produit(s) marqué(s) comme indisponible(s).', 'warning')


@admin.action(description='Marquer les produits sélectionnés comme Disponibles')
def rendre_disponible(modeladmin, request, queryset):
    updated = queryset.update(statut=True)
    modeladmin.message_user(request, f'{updated} produit(s) marqué(s) comme disponible(s).', 'success')


@admin.action(description='Exporter les produits sélectionnés en CSV')
def exporter_csv(modeladmin, request, queryset):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="export_produits.csv"'
    writer = csv.writer(response, delimiter=';')
    writer.writerow([
        'Nom', 'Marque', 'Appellation', 'Cépage', 'Type', 'Volume',
        'Degré', 'Code-barres', 'Unité', 'Contenance', 'Coût de revient',
        'Prix détaillant', 'Prix consommateur', 'Prix lot', 'Marge',
        'Catégorie', 'Stock', 'Statut',
    ])
    for prod in queryset.select_related('categorie'):
        try:
            stock_qty = prod.stock.quantite
        except Stock.DoesNotExist:
            stock_qty = 0
        marge = prod.prix_vente - prod.cout_revenir
        writer.writerow([
            prod.nom, prod.marque, prod.appellation, prod.cepage, prod.type_vin,
            prod.volume, prod.degre_libelle,
            prod.code_barre or '', prod.get_unite_vente_display(), prod.contenance,
            prod.cout_revenir, prod.prix_revendeur, prod.prix_vente,
            prod.prix_conditionnement or '', marge,
            prod.categorie.nom if prod.categorie else '',
            stock_qty, 'Actif' if prod.statut else 'Inactif',
        ])
    return response


class ProduitAdminForm(forms.ModelForm):
    """Formulaire de saisie, avec des invites de saisie plutôt que de l'aide.

    L'ajout demande les informations de vente : nom, famille, volume, prix de
    vente, la photo (fichier joint ou adresse à importer) et la description.
    Tout le reste a une valeur par défaut ou attend le moment de la vente, le
    prendre ici serait du temps perdu.
    """

    # Photo distante : le champ n'existe que dans le formulaire. L'image
    # rapatriée est rangée dans `Produit.image`, qui reste la seule source
    # d'image du catalogue — la fiche, la caisse et le site lisent le même
    # fichier, et la photo survit à la disparition du lien d'origine.
    image_url = forms.URLField(
        required=False,
        label='URL de l’image',
        widget=forms.URLInput(attrs={
            'class': 'form-control',
            'placeholder': 'https://exemple.com/photo.jpg',
        }),
    )

    class Meta:
        model = Produit
        fields = '__all__'
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'form-control',
                'autofocus': True,
                'placeholder': 'Ex. : Vin Rouge Isaha',
            }),
            'volume': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex. : 75 cl',
            }),
            # La famille se choisit dans une liste fermée : un menu déroulant
            # tient sur une ligne, là où six cartes occupaient tout l'écran.
            'type_vin': forms.Select(attrs={'class': 'form-select'}),
            'cout_revenir': forms.NumberInput(attrs={
                'class': 'form-control input-money', 'step': '0.01', 'min': '0',
            }),
            'prix_vente': forms.NumberInput(attrs={
                'class': 'form-control input-money', 'step': '0.01', 'min': '0',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Ex. : Cuvée du domaine, notes de fruits rouges.',
            }),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Renseigné par `clean_image_url` quand une adresse a été fournie.
        self._image_importee = None

    def clean_image_url(self):
        """Rapatrie la photo distante dès la validation du formulaire.

        L'import se fait ici, et non à l'enregistrement, pour qu'un lien mort
        s'affiche sous le champ au lieu de faire échouer la page. Un fichier
        joint l'emporte : l'utilisateur a choisi une photo, on ne va pas
        chercher celle du lien.
        """
        lien = (self.cleaned_data.get('image_url') or '').strip()
        if not lien or self.cleaned_data.get('image'):
            return lien
        try:
            self._image_importee = telecharger_image(lien)
        except ImageDistanteInvalide as exc:
            raise forms.ValidationError(str(exc))
        return lien

    def clean(self):
        """À la création, une photo est obligatoire : fichier joint ou URL.

        Aucune bouteille ne doit entrer en rayon sans visuel : la caisse, le
        site et la fiche lisent la même image, et la retrouver après coup est
        plus coûteux que de la choisir au moment de la saisie. Le contrôle ne
        s'applique qu'à la création : les fiches existantes restent modifiables
        même sans photo.
        """
        cleaned = super().clean()
        if self.instance.pk is not None:
            return cleaned
        if cleaned.get('image') or cleaned.get('image_url'):
            return cleaned
        # Une URL déjà saisie mais rejetée par `clean_image_url` porte son
        # propre message : inutile d'en ajouter un second, contradictoire.
        if (self.data.get('image_url') or '').strip():
            return cleaned
        self.add_error(
            'image_url',
            forms.ValidationError(
                'Ajoutez une photo : importez un fichier ou collez une URL d’image.'
            ),
        )
        return cleaned

    def save(self, commit=True):
        produit = super().save(commit=False)
        if self._image_importee:
            nom, contenu = self._image_importee
            produit.image.save(nom, contenu, save=False)
        if commit:
            produit.save()
            self.save_m2m()
        return produit


@admin.register(Produit)
class ProduitAdmin(ActionsColonneMixin, admin.ModelAdmin):
    change_list_template = 'admin/produits/produit/change_list.html'
    change_form_template = 'admin/produits/produit/change_form.html'
    form = ProduitAdminForm
    # Liste réduite aux données qui comptent sur la ligne : la photo, le nom,
    # le prix de vente, le stock et l'état. La catégorie, le code-barres, le
    # conditionnement, les marges et le tarif revendeur ont quitté le tableau :
    # ces données se lisent sur la fiche du produit, pas sur un tableau de
    # 25 lignes. Le nom porte le lien de la ligne : un clic ouvre la fiche,
    # au titre de la colonne « Actions » (Modifier / Supprimer) pour la même
    # destination. Une ligne sans code-barres reste affichable
    # (test_changelist_produits_sans_code_barre).
    list_display = (
        'image_tag', 'nom', 'prix_vente', 'stock_badge', 'statut_display',
    )
    list_display_links = ('nom',)
    list_editable = ('prix_vente',)
    search_fields = ('nom', 'marque', 'type_vin', 'description', 'code_barre')
    search_help_text = "Nom, marque, type, code-barres"
    list_filter = ('statut', 'type_vin', 'categorie', 'appellation', 'unite_vente', 'code_barre')
    ordering = ('-date_creation',)
    readonly_fields = (
        'date_creation', 'updated_at', 'image_tag', 'marge_calc', 'stock_actuel',
        'code_barre_svg', 'prix_unitaire_preview', 'etiquette_preview',
    )
    autocomplete_fields = ('categorie',)
    list_per_page = 25
    actions = [generer_codes_barres, rendre_disponible, rendre_indisponible, exporter_csv]

    # Création : les champs essentiels, un seul bloc. Les neuf autres onglets de
    # la fiche sont des attributs de cave, pas des conditions de vente : les saisir
    # au moment d'enregistrer une bouteille coûte plus de temps qu'il n'en faut.
    # Le reste se complète sur la fiche, une fois le produit en rayon. Le
    # code-barres est généré après coup (action de masse), le stock est créé à
    # zéro par le signal `post_save`. La catégorie n'est pas demandée ici : elle
    # se choisit dans un référentiel qui existe déjà, chercher la bonne ligne à
    # chaque saisie ralentit plus qu'il n'aide. Un vin peut très bien entrer en
    # rayon sans que l'on sache encore à quelle famille il appartient.
    # Le tarif détaillant (prix_revendeur) est un attribut de cave : il se règle
    # sur la fiche, une fois le vin en rayon.
    # Le coût de revient n'est pas demandé non plus : il ne sert qu'à la marge,
    # un calcul de gestion qui n'a rien à faire devant un client qui attend sa
    # bouteille. Il se renseigne sur la fiche, à froid.
    add_fieldsets = (
        ('Produit', {
            'fields': (
                'nom', 'type_vin', 'volume', 'prix_vente',
                'image', 'image_url', 'description',
            )
        }),
    )

    fieldsets = (
        ('Produit', {
            'fields': ('nom', 'marque', 'type_vin', 'volume', 'statut')
        }),
        ('Tarification', {
            'fields': ('cout_revenir', 'prix_revendeur', 'prix_vente', 'marge_calc')
        }),
        ('Conditionnement', {
            'fields': (
                'unite_vente', 'contenance', 'prix_conditionnement',
                'prix_unitaire_preview',
            ),
        }),
        ('Code-barres', {
            'fields': ('code_barre', 'code_barre_svg', 'etiquette_preview'),
        }),
        ('Relations', {
            'fields': ('categorie',)
        }),
        ('Cave', {
            'fields': (
                'appellation', 'cepage', 'degre_alcool',
                'elevage', 'temperature_service', 'potentiel_garde',
            ),
        }),
        ('Détails', {
            'fields': ('description', 'image_tag', 'image'),
            'classes': ('collapse',)
        }),
        ('Stock', {
            'fields': ('stock_actuel',),
            'classes': ('collapse',)
        }),
        ('Système', {
            'fields': ('date_creation', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_fieldsets(self, request, obj=None):
        """Fiche complète à la modification, champs essentiels à la création.

        Ce qui est retiré pour aller vite à la création (code-barres,
        cépage, catégorie…) doit rester saisissable ensuite :
        la fiche est le seul endroit où ces attributs de cave se renseignent.
        """
        if obj is None:
            return self.add_fieldsets
        return self.fieldsets

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        kwargs['help_text'] = ''
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('categorie')

    @staticmethod
    def _quantite_en_stock(produit):
        """Même garde que les colonnes `stock_badge` et `stock_actuel` :
        un produit peut exister sans ligne de stock (import, reprise de données)."""
        try:
            return produit.stock.quantite
        except Stock.DoesNotExist:
            return 0

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        qs = Produit.objects.all()
        stocks = Stock.objects.all()
        promo_count = PromotionProduit.objects.values('produit').distinct().count()
        extra_context['produits_kpis'] = {
            'total': qs.count(),
            'actifs': qs.filter(statut=True).count(),
            'inactifs': qs.filter(statut=False).count(),
            'ruptures': stocks.filter(quantite__lte=0).count(),
            'faibles': stocks.filter(quantite__gt=0, quantite__lte=F('seuil_alerte')).count(),
            'en_promo': promo_count,
            'sans_code_barre': qs.filter(code_barre='').count(),
            # Marge potentielle immobilisée en cave : ce que le stock rapporte s'il
            # est intégralement vendu au prix de vente, moins son coût.
            'marge_stock': sum(
                p.marge_unitaire * self._quantite_en_stock(p)
                for p in qs.select_related('stock')
            ),
        }
        return super().changelist_view(request, extra_context=extra_context)

    # --- Colonnes personnalisées ---

    @admin.display(description='Stock')
    def stock_badge(self, obj):
        try:
            stock = obj.stock
            qty = stock.quantite
            seuil = stock.seuil_alerte
        except Stock.DoesNotExist:
            qty, seuil = 0, 10
        if qty <= 0:
            css, label = 'lb-badge-wine', 'Rupture'
        elif qty <= seuil:
            css, label = 'lb-badge-gold', f'{qty} sous seuil'
        else:
            css, label = 'lb-badge-sage', str(qty)
        return format_html('<span class="lb-badge {}">{}</span>', css, label)

    @admin.display(description='Image')
    def image_tag(self, obj):
        """Aperçu miniature de l'image du produit dans la liste et le détail admin."""
        if obj.image:
            return format_html(
                '<img src="{}" alt="Photo de {}">',
                obj.image.url,
                obj.nom,
            )
        return format_html(
            '<span class="product-card-placeholder" aria-hidden="true">'
            '<i class="fas fa-wine-bottle">{}</i></span>',
            '',
        )

    @admin.display(description='État', boolean=True)
    def statut_display(self, obj):
        return obj.statut

    @admin.display(description='Marge')
    def marge_calc(self, obj):
        if obj is None or obj.prix_vente is None or obj.cout_revenir is None:
            return '—'
        return obj.prix_vente - obj.cout_revenir

    @admin.display(description='Stock actuel (bouteilles)')
    def stock_actuel(self, obj):
        if obj is None:
            return '—'
        try:
            return obj.stock.quantite
        except Stock.DoesNotExist:
            return 0

    @admin.display(description='Prix qui sera appliqué en caisse')
    def prix_unitaire_preview(self, obj):
        if obj is None or obj.pk is None:
            return '—'
        return format_html(
            '<b>{}</b> <span class="lb-val-muted">par {}</span>'
            '<br><small class="lb-val-muted">soit {} la bouteille</small>',
            obj.prix_unitaire_vente,
            obj.get_unite_vente_display().lower(),
            obj.par_bouteille,
        )

    @admin.display(description='Code-barres (aperçu)')
    def code_barre_svg(self, obj):
        """Aperçu du code, avec alerte si la clé EAN-13 est invalide.

        Le code-barres n'est plus une colonne de la liste : l'alerte se lit
        sur la fiche, là où le code se corrige.
        """
        if obj is None or not obj.code_barre:
            return '—'
        alerte = ''
        if (
            obj.code_barre.isdigit()
            and len(obj.code_barre) == 13
            and not cle_ean13_valide(obj.code_barre)
        ):
            alerte = (
                '<i class="fas fa-triangle-exclamation lb-val-wine" '
                'title="Clé EAN-13 invalide"></i> '
            )
        return format_html('{}{}', alerte, code_svg(obj.code_barre, hauteur=48))

    @admin.display(description='Aperçu étiquette (30 × 20 mm)')
    def etiquette_preview(self, obj):
        if obj is None or not obj.code_barre:
            return '—'
        devise = self._devise()
        return format_html(
            '<div style="width:230px;height:155px;border:1px dashed var(--lb-ink-300);border-radius:6px;'
            'padding:8px;display:flex;flex-direction:column;justify-content:space-between;'
            'background:#fff;font-family:Arial,Helvetica,sans-serif">'
            '<div style="font-size:9px;color:#666;letter-spacing:.5px">{}</div>'
            '<div style="font-size:12px;font-weight:700;line-height:1.15">{}</div>'
            '<div>{}</div>'
            '<div style="font-size:15px;font-weight:800">{} {}</div>'
            '</div>',
            obj.volume or self._marque(),
            obj.nom,
            code_svg(obj.code_barre, hauteur=34),
            obj.prix_unitaire_vente, devise,
        )

    def _devise(self):
        from django.conf import settings
        return settings.SOCIETE.get('devise', 'Ar')

    def _marque(self):
        from django.conf import settings
        return settings.SOCIETE.get('nom_entreprise', 'CAISSE')

    # --- URLs personnalisées ---

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('stats/', self.admin_site.admin_view(self.stats_view), name='produits_stats'),
            path('export/', self.admin_site.admin_view(self.export_view), name='produits_export'),
            path('etiquettes/', self.admin_site.admin_view(self.etiquettes_view), name='produits_etiquettes'),
        ]
        return custom_urls + urls

    def stats_view(self, request):
        """Vue JSON des statistiques produits pour le frontend."""
        qs = Produit.objects.all()
        stocks = Stock.objects.all()
        data = {
            'total': qs.count(),
            'actifs': qs.filter(statut=True).count(),
            'inactifs': qs.filter(statut=False).count(),
            'ruptures': stocks.filter(quantite__lte=0).count(),
            'faibles': stocks.filter(quantite__gt=0, quantite__lte=F('seuil_alerte')).count(),
            'types': list(qs.values_list('type_vin', flat=True).distinct()),
            'categories': list(qs.values_list('categorie__nom', flat=True).distinct()),
        }
        return JsonResponse(data)

    def export_view(self, request):
        """Export CSV de tous les produits."""
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="produits_export.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'Nom', 'Marque', 'Appellation', 'Cépage', 'Type', 'Volume',
            'Degré', 'Code-barres', 'Unité', 'Contenance', 'Coût de revient',
            'Prix Vente', 'Prix lot', 'Marge', 'Catégorie', 'Stock', 'Statut',
        ])
        for prod in Produit.objects.select_related('categorie'):
            try:
                stock_qty = prod.stock.quantite
            except Stock.DoesNotExist:
                stock_qty = 0
            marge = prod.marge_unitaire
            writer.writerow([
                prod.nom, prod.marque, prod.appellation, prod.cepage,
                prod.get_type_vin_display(), prod.volume,
                prod.degre_libelle, prod.code_barre or '',
                prod.get_unite_vente_display(), prod.contenance,
                prod.cout_revenir, prod.prix_vente, prod.prix_conditionnement or '', marge,
                prod.categorie.nom if prod.categorie else '',
                stock_qty, 'Actif' if prod.statut else 'Inactif',
            ])
        return response

    def etiquettes_view(self, request):
        """
        Feuille d'étiquettes prête à imprimer (format Avery 30 × 20 mm).

        Le nombre d'exemplaires suit le stock : impossible d'imprimer plus
        d'étiquettes qu'il n'y a de bouteilles sur le rayon. Le rendu est fait
        côté serveur — la feuille s'imprime même si le JavaScript est coupé.
        """
        ids = request.GET.getlist('ids')
        if ids:
            produits = Produit.objects.filter(pk__in=ids)
        else:
            produits = Produit.objects.all()
        produits = produits.prefetch_related('stock').order_by('nom')

        cartes = []
        sans_code = 0
        for produit in produits:
            # `code_barre` est nullable et vidé à '' : sans code, pas d'étiquette
            # possible (et la génération du SVG lèverait une ValueError → 500).
            if not produit.code_barre:
                sans_code += 1
                continue
            try:
                quantite = produit.stock.quantite
            except Stock.DoesNotExist:
                quantite = 0
            # Un minimum de 1 : un produit en rupture reste étiquetable.
            # Au-delà, on borne à 60 pour ne pas noyer la page.
            copies = max(1, min(60, quantite))
            svg_code = code_svg(produit.code_barre, hauteur=34)
            for _ in range(copies):
                cartes.append({'produit': produit, 'code_svg': svg_code})

        contexte = dict(
            self.admin_site.each_context(request),
            cartes=cartes,
            sans_code=sans_code,
            nb_produits=len({id(c['produit']) for c in cartes}),
            devise=self._devise(),
            entreprise=self._marque(),
        )
        return TemplateResponse(request, 'admin/produits/etiquettes.html', contexte)
