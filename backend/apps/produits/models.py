from decimal import Decimal

from django.core.files.storage import storages
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.categories.models import Categorie


def produit_image_storage():
    return storages['product_images']


class Produit(models.Model):
    class UniteVente(models.TextChoices):
        BOUTEILLE = 'BOUTEILLE', _('Bouteille')
        PACK = 'PACK', _('Pack')
        CARTON = 'CARTON', _('Carton')

    class TypeVin(models.TextChoices):
        """Familles du catalogue : vins, apéritifs et produits dérivés."""
        ROUGE = 'Rouge', _('Rouge')
        ROSE = 'Rose', _('Rose')
        BLANCHE = 'Blanche', _('Blanche')
        APERITIF = 'Apéritif', _('Apéritif')
        EAU_DE_VIE = 'Eau-de-vie', _('Eau-de-vie')
        LIQUEUR = 'Liqueur', _('Liqueur')

    nom = models.CharField(max_length=200, verbose_name=_('Nom'))
    description = models.TextField(blank=True, null=True, verbose_name=_('Description'))
    type_vin = models.CharField(
        max_length=100, choices=TypeVin.choices, default=TypeVin.ROUGE, verbose_name=_('Famille'),
    )
    marque = models.CharField(max_length=150, blank=True, default='', verbose_name=_('Marque'))
    volume = models.CharField(max_length=50, verbose_name=_('Volume'))

    # Fiche de cave : ce qui distingue une cuvée d'une autre sur une étiquette.
    appellation = models.CharField(max_length=150, blank=True, default='', verbose_name=_('Appellation'))
    cepage = models.CharField(max_length=200, blank=True, default='', verbose_name=_('Cépage'))
    degre_alcool = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True, verbose_name=_('Degré'),
    )
    elevage = models.CharField(max_length=150, blank=True, default='', verbose_name=_('Élevage'))
    temperature_service = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name=_('Température'),
    )
    potentiel_garde = models.CharField(max_length=80, blank=True, default='', verbose_name=_('Garde'))

    # Coût de revient de la bouteille, quand elle n'est pas achetée. Sert
    # uniquement au calcul de marge, en repli du prix d'achat.
    cout_revenir = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name=_('Coût de revient'),
    )
    # Prix d'achat de la bouteille quand elle vient de l'extérieur ; à défaut
    # de coût de revient, il sert à valoriser le stock et à calculer la marge.
    prix_achat = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name=_('Prix d\'achat'),
    )
    prix_vente = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name=_('Prix de vente'),
    )
    # Tarif détaillant par bouteille ; zéro conserve le tarif public historique.
    prix_revendeur = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_('Prix détaillant par bouteille'),
    )

    # Code-barres interne : pilier de la vente rapide à la caisse. Une douchette
    # USB saisit ce code dans le champ de recherche, ce qui évite de faire
    # défiler le catalogue.
    code_barre = models.CharField(
        max_length=64, unique=True, null=True, blank=True,
        db_index=True, verbose_name=_('Code-barres'),
    )

    # Conditionnement : une bouteille, un pack de 6, un carton de 12…
    unite_vente = models.CharField(
        max_length=20, choices=UniteVente.choices, default=UniteVente.BOUTEILLE,
        verbose_name=_('Unité'),
    )
    contenance = models.PositiveIntegerField(
        default=1, verbose_name=_('Contenance'),
    )
    prix_conditionnement = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name=_('Prix du lot'),
    )

    image = models.ImageField(
        upload_to='produits/', storage=produit_image_storage,
        blank=True, null=True, verbose_name=_('Image'),
    )
    statut = models.BooleanField(default=True, verbose_name=_('Statut'))
    
    categorie = models.ForeignKey(Categorie, on_delete=models.SET_NULL, null=True, related_name='produits', verbose_name=_('Catégorie'))

    date_creation = models.DateTimeField(auto_now_add=True, verbose_name=_('Création'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Maj'))

    class Meta:
        verbose_name = _('produit')
        verbose_name_plural = _('produits')
        db_table = 'produits_produit'
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['nom'], name='produit_nom_idx'),
            models.Index(fields=['categorie', 'statut'], name='produit_cat_statut_idx'),
            models.Index(fields=['type_vin', 'statut'], name='produit_type_statut_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(contenance__gte=1), name='produit_contenance_min'
            ),
            models.CheckConstraint(
                condition=models.Q(prix_revendeur__gte=0), name='produit_prix_revendeur_min'
            ),
        ]

    def __str__(self):
        return self.nom

    @property
    def marge_brute_unitaire(self):
        """Marge brute par bouteille = prix_vente - (cout_revenir ou prix_achat)."""
        cout = self.cout_revenir if self.cout_revenir > 0 else self.prix_achat
        return max(Decimal(self.prix_vente) - Decimal(cout), Decimal('0.00'))

    @property
    def taux_marque(self):
        """Taux de marque = (marge_brute / prix_vente) * 100."""
        if self.prix_vente and self.prix_vente > 0:
            return round((self.marge_brute_unitaire / Decimal(self.prix_vente)) * Decimal('100.0'), 1)
        return Decimal('0.0')

    @property
    def en_stock(self):
        """Indique si la bouteille est disponible en stock positif."""
        return hasattr(self, 'stock') and self.stock.quantite > 0

    # ------------------------------------------------------------------
    # Conditionnement
    # ------------------------------------------------------------------
    @property
    def bouteilles_par_unite(self):
        """Nombre de bouteilles physiquement contenues dans une unité de vente."""
        return max(int(self.contenance or 1), 1)

    @property
    def prix_unitaire_vente(self):
        """Prix de vente de l'unité de vente (bouteille, pack, carton)."""
        if self.unite_vente != Produit.UniteVente.BOUTEILLE and self.prix_conditionnement > 0:
            return Decimal(self.prix_conditionnement)
        return Decimal(self.prix_vente) * self.bouteilles_par_unite

    def prix_bouteille_pour_client(self, type_client=None):
        """Prix bouteille selon le segment, avec repli sur le tarif public."""
        if type_client in {'REVENDEUR', 'RESTAURANT', 'HOTEL'} and self.prix_revendeur > 0:
            return Decimal(self.prix_revendeur)
        return Decimal(self.prix_vente)

    def prix_unitaire_pour_client(self, type_client=None, unite=None):
        """Prix du conditionnement vendu selon le tarif du client.

        Le tarif détaillant est défini à la bouteille et s'applique donc au
        nombre de bouteilles d'un pack/carton. Le prix de conditionnement
        configuré reste prioritaire pour le tarif public.
        """
        unite = unite or self.unite_vente or Produit.UniteVente.BOUTEILLE
        contenance = 1 if unite == Produit.UniteVente.BOUTEILLE else self.bouteilles_par_unite
        tarif_professionnel = (
            type_client in {'REVENDEUR', 'RESTAURANT', 'HOTEL'}
            and self.prix_revendeur > 0
        )
        if tarif_professionnel:
            return self.prix_bouteille_pour_client(type_client) * contenance
        if unite == self.unite_vente:
            return self.prix_unitaire_vente
        return Decimal(self.prix_vente) * contenance

    @property
    def conditionnement_libelle(self):
        """libellé court affiché à la caisse : « Bouteille », « Pack de 6 »…"""
        if self.unite_vente == Produit.UniteVente.BOUTEILLE:
            return _('Bouteille')
        return f"{self.get_unite_vente_display()} de {self.bouteilles_par_unite}"

    @property
    def par_bouteille(self):
        """Prix ramené à la bouteille, pour comparer deux conditionnements."""
        return (self.prix_unitaire_vente / self.bouteilles_par_unite).quantize(Decimal('0.01'))

    # ------------------------------------------------------------------
    # Marge
    # ------------------------------------------------------------------
    @property
    def cout_effectif(self):
        """Coût retenu pour la marge et la valorisation du stock.

        Une cuvée produite au domaine a un coût de revient. Une cuvée achetée
        n'en a pas : on retient alors son prix d'achat. Sans cela, la marge et
        la valeur du stock seraient calculées sur un coût nul, donc fausses.
        """
        if self.cout_revenir and self.cout_revenir > 0:
            return Decimal(self.cout_revenir)
        return Decimal(self.prix_achat or 0)

    @property
    def marge_unitaire(self):
        """Marge brute par bouteille vendue (prix de vente - coût effectif)."""
        return Decimal(self.prix_vente) - self.cout_effectif

    @property
    def marge_pct(self):
        """Marge en % du coût effectif. 0 si le coût n'est connu d'aucun côté."""
        cout = self.cout_effectif
        if not cout or cout <= 0:
            return Decimal('0')
        return (self.marge_unitaire / cout * 100).quantize(Decimal('0.1'))

    # ------------------------------------------------------------------
    # Fiche de cave
    # ------------------------------------------------------------------
    @property
    def appellation_ou_marque(self):
        """Ce qu'on imprime sous le nom : appellation si connue, sinon la marque."""
        return self.appellation or self.marque

    @property
    def degre_libelle(self):
        """Degré d'alcool formaté pour l'étiquette, ex. « 13,5 % vol. »."""
        if self.degre_alcool is None:
            return ''
        return f"{str(self.degre_alcool).replace('.', ',')} % vol."

    # ------------------------------------------------------------------
    # Code-barres
    # ------------------------------------------------------------------
    PREFIXE_CODE_INTERNE = '200'

    @staticmethod
    def generer_code_interne(sequence, prefixe=PREFIXE_CODE_INTERNE):
        """
        Code interne déterministe de type EAN-13 (préfixe 200 = usage interne).

        Le 7e chiffre est la clé de contrôle EAN-13, ce qui rend le code lisible
        et imprimable tel quel par une imprimante d'étiquettes standard.
        """
        corps = f"{prefixe}{int(sequence):09d}"[:12]
        somme = sum((1 if i % 2 == 0 else 3) * int(d) for i, d in enumerate(corps))
        return corps + str((10 - somme % 10) % 10)

    def attribuer_code_barre(self, prefixe=PREFIXE_CODE_INTERNE):
        """
        Attribue (et mémorise) un code-barre interne si le produit n'en a pas.

        La séquence est celle du dernier code attribué : deux produits
        exécutés dans le même appel ne peuvent pas obtenir le même code.
        """
        if self.code_barre:
            return self.code_barre
        dernier = (
            Produit.objects.exclude(pk=self.pk)
            .filter(code_barre__startswith=prefixe)
            .order_by('-code_barre')
            .values_list('code_barre', flat=True)
            .first()
        )
        sequence = int(dernier[3:]) + 1 if dernier else 1
        self.code_barre = Produit.generer_code_interne(sequence, prefixe)
        return self.code_barre
