from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _
from apps.produits.models import Produit

class Promotion(models.Model):
    class TypePromotion(models.TextChoices):
        POURCENTAGE = 'POURCENTAGE', _('Pourcentage')
        MONTANT_FIXE = 'MONTANT_FIXE', _('Montant fixe')
        PRIX_PROMO = 'PRIX_PROMO', _('Prix promo')
        LOT = 'LOT', _('Lot')

    class TypeCible(models.TextChoices):
        TOUS = 'TOUS', _('Tous')
        PARTICULIER = 'PARTICULIER', _('Particuliers')
        REVENDEUR = 'REVENDEUR', _('Revendeurs')
        RESTAURANT = 'RESTAURANT', _('Restaurants')
        HOTEL = 'HOTEL', _('Hôtels')

    # Ces deux types se calculent sur ``valeur`` ; les deux autres demandent
    # des paramètres dédiés (prix unitaire, quantités du lot).
    TYPES_SUR_VALEUR = (TypePromotion.POURCENTAGE, TypePromotion.MONTANT_FIXE)

    nom = models.CharField(max_length=150, verbose_name=_('Nom'))
    description = models.TextField(blank=True, null=True, verbose_name=_('Description'))
    # Détermine quels paramètres sont utiles : « Pourcentage » et
    # « Montant fixe » se calculent sur la valeur ; « Prix promo » et
    # « Lot » demandent des paramètres supplémentaires.
    type_promotion = models.CharField(
        max_length=20,
        choices=TypePromotion.choices,
        default=TypePromotion.POURCENTAGE,
        verbose_name=_('Remise'),
    )
    # Pourcentage (0-100) ou montant fixe retiré du prix unitaire.
    valeur = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name=_('Valeur')
    )
    # Prix de vente alvoisin appliqué à l'unité (type « prix promotionnel »).
    prix_promotionnel = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)], verbose_name=_('Prix promo'),
    )
    # Nombre d'unités payantes puis offertes une fois le lot atteint.
    quantite_achetee = models.PositiveIntegerField(default=2, verbose_name=_('Qté achetée'))
    quantite_offerte = models.PositiveIntegerField(default=1, verbose_name=_('Qté offerte'))
    # Quantité minimale de la ligne de vente requise.
    quantite_min = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1)], verbose_name=_('Qté minimale'),
    )

    # Segment de clientQui bénéficie de la promotion.
    type_cible = models.CharField(
        max_length=20, choices=TypeCible.choices, default=TypeCible.TOUS, verbose_name=_('Cible'),
    )
    # Renseignée : la promotion ne s'applique que si le client saisit ce code.
    code = models.CharField(max_length=30, unique=True, null=True, blank=True, verbose_name=_('Code'))

    date_debut = models.DateTimeField(verbose_name=_('Début'))
    date_fin = models.DateTimeField(verbose_name=_('Fin'))

    # Créneau horaire : début, fin et jours d'application. Un créneau nocturne
    # (22:00 → 02:00) est accepté.
    heure_debut = models.TimeField(null=True, blank=True, verbose_name=_('Heure de début'))
    heure_fin = models.TimeField(null=True, blank=True, verbose_name=_('Heure de fin'))
    jours_semaine = models.CharField(max_length=20, blank=True, default='', verbose_name=_('Jours'))

    # Vide = illimité. Départage les remises identiques : la plus élevée l'emporte.
    limite_utilisation = models.PositiveIntegerField(null=True, blank=True, verbose_name=_('Limite'))
    nb_utilisations = models.PositiveIntegerField(default=0, verbose_name=_('Utilisations'))
    priorite = models.PositiveIntegerField(default=0, verbose_name=_('Priorité'))

    statut = models.BooleanField(default=True, verbose_name=_('Actif'))

    produits = models.ManyToManyField(
        Produit,
        through='PromotionProduit',
        related_name='promotions',
        verbose_name=_('Produits')
    )
    # Vide = tous les vins de ces catégories.
    categories = models.ManyToManyField(
        'categories.Categorie', blank=True, related_name='promotions', verbose_name=_('Catégories'),
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Création'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Maj'))

    class Meta:
        verbose_name = _('promotion')
        verbose_name_plural = _('promotions')
        db_table = 'promotions_promotion'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code'], name='promo_code_idx'),
            models.Index(fields=['date_debut', 'date_fin'], name='promo_periode_idx'),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantite_min__gte=1), name='promo_quantite_min_valide'),
        ]

    def __str__(self):
        return f"{self.nom} ({self.get_type_promotion_display()} - {self.valeur})"

    def clean(self):
        """Validations métier transverses (appelées par l'admin et le formulaire)."""
        errors = {}
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            errors['date_fin'] = _("La date de fin doit être postérieure ou égale à la date de début.")
        if self.valeur is not None and self.valeur <= 0:
            errors['valeur'] = _("La valeur de la remise doit être strictement positive.")
        if (
            self.valeur is not None
            and self.type_promotion == self.TypePromotion.POURCENTAGE
            and self.valeur > 100
        ):
            errors['valeur'] = _("Un pourcentage de remise ne peut pas dépasser 100 %.")
        if errors:
            raise DjangoValidationError(errors)

    @property
    def est_active(self):
        now = timezone.now()
        return self.statut and self.date_debut <= now <= self.date_fin

    @property
    def a_un_creneau(self):
        return bool(self.heure_debut or self.heure_fin or self.jours_semaine)

    @property
    def jours_semaine_liste(self):
        return [j.strip() for j in (self.jours_semaine or '').split(',') if j.strip()]

    @property
    def creneau_texte(self):
        if not self.a_un_creneau:
            return ''
        if self.heure_debut and self.heure_fin:
            plage = f"{self.heure_debut:%H:%M}–{self.heure_fin:%H:%M}"
        elif self.heure_debut:
            plage = f"à partir de {self.heure_debut:%H:%M}"
        elif self.heure_fin:
            plage = f"jusqu'à {self.heure_fin:%H:%M}"
        else:
            plage = ''
        jours = self.jours_semaine_liste
        if jours:
            return f"{plage} ({', '.join(jours)})".strip()
        return plage

    @property
    def regle_texte(self):
        if self.type_promotion == self.TypePromotion.POURCENTAGE:
            return f"− {self.valeur} %"
        if self.type_promotion == self.TypePromotion.MONTANT_FIXE:
            from django.conf import settings
            return f"− {self.valeur} {settings.SOCIETE.get('devise', 'Ar')}"
        if self.type_promotion == self.TypePromotion.PRIX_PROMO:
            from django.conf import settings
            return f"prix {self.prix_promotionnel} {settings.SOCIETE.get('devise', 'Ar')}"
        return f"{self.quantite_achetee} achetées, {self.quantite_offerte} offerte(s)"

    @property
    def est_epuisee(self):
        return self.limite_utilisation is not None and self.nb_utilisations >= self.limite_utilisation


class PromotionProduit(models.Model):
    promotion = models.ForeignKey(Promotion, on_delete=models.CASCADE, verbose_name=_('promotion'))
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, verbose_name=_('produit'))

    class Meta:
        verbose_name = _('produit en promotion')
        verbose_name_plural = _('produits en promotion')
        db_table = 'promotions_promotion_produit'
        constraints = [
            models.UniqueConstraint(fields=['promotion', 'produit'], name='unique_promotion_produit')
        ]

    def __str__(self):
        return f"{self.produit.nom} - {self.promotion.nom}"
