from django.db import models
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from apps.produits.models import Produit

class Stock(models.Model):
    produit = models.OneToOneField(
        Produit,
        on_delete=models.CASCADE,
        related_name='stock',
        verbose_name=_('Produit')
    )
    quantite = models.IntegerField(
        validators=[MinValueValidator(0)],
        default=0,
        verbose_name=_('Quantité')
    )
    seuil_alerte = models.IntegerField(
        validators=[MinValueValidator(0)],
        default=10,
        verbose_name=_('Alerte')
    )
    date_mise_a_jour = models.DateTimeField(auto_now=True, verbose_name=_('Maj'))

    class Meta:
        verbose_name = _('stock')
        verbose_name_plural = _('stocks')
        db_table = 'stocks_stock'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantite__gte=0), name='stock_quantite_non_negatif'
            ),
            models.CheckConstraint(
                condition=models.Q(seuil_alerte__gte=0), name='stock_seuil_non_negatif'
            ),
        ]

    def __str__(self):
        return f"Stock de {self.produit.nom} ({self.quantite})"

    @property
    def etat_stock(self):
        """
        Détermine l'état du stock:
        - RUPTURE : quantité <= 0
        - STOCK_FAIBLE : quantité <= seuil_alerte
        - STOCK_NORMAL : quantité > seuil_alerte
        """
        if self.quantite <= 0:
            return 'RUPTURE'
        elif self.quantite <= self.seuil_alerte:
            return 'STOCK_FAIBLE'
        return 'STOCK_NORMAL'
    @property
    def est_en_rupture(self):
        return self.quantite <= 0

    @property
    def est_en_alerte(self):
        return self.quantite <= self.seuil_alerte

    @property
    def besoin_reappro(self):
        """Quantité suggérée pour reconstituer un stock de sécurité optimal (2 × seuil)."""
        seuil_cible = self.seuil_alerte * 2
        return max(seuil_cible - self.quantite, 0)


class MouvementStock(models.Model):
    class TypeMouvement(models.TextChoices):
        ENTREE = 'ENTREE', _('Entrée (Réapprovisionnement)')
        SORTIE = 'SORTIE', _('Sortie (Vente)')
        RETOUR = 'RETOUR', _('Retour Client')
        AJUSTEMENT = 'AJUSTEMENT', _('Ajustement Manuel')

    produit = models.ForeignKey(
        Produit, 
        on_delete=models.CASCADE, 
        related_name='mouvements', 
        verbose_name=_('Produit')
    )
    quantite = models.IntegerField(verbose_name=_('Quantité'))
    type_mouvement = models.CharField(
        max_length=20, 
        choices=TypeMouvement.choices, 
        verbose_name=_('Type')
    )
    description = models.CharField(max_length=255, blank=True, verbose_name=_('Description'))
    reference_id = models.CharField(max_length=100, blank=True, db_index=True, verbose_name=_('Réf. Objet'))
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        related_name='mouvements_saisis',
        verbose_name=_('Utilisateur')
    )
    date_mouvement = models.DateTimeField(auto_now_add=True, verbose_name=_('Date'))

    class Meta:
        verbose_name = _('mouvement de stock')
        verbose_name_plural = _('mouvements de stock')
        db_table = 'stocks_mouvement'
        ordering = ['-date_mouvement']
        indexes = [
            models.Index(fields=['produit', 'date_mouvement'], name='mvt_produit_date_idx'),
            models.Index(fields=['type_mouvement', 'date_mouvement'], name='mvt_type_date_idx'),
        ]
        constraints = [
            # Un mouvement nul n'endisque rien et n'a aucune traçabilité : les
            # sorties (ventes) sont négatives, les entrées/retours positifs.
            models.CheckConstraint(
                condition=models.Q(quantite__lt=0) | models.Q(quantite__gt=0),
                name='mouvement_quantite_non_nulle',
            ),
        ]

    def __str__(self):
        return f"{self.type_mouvement} - {self.produit.nom} ({self.quantite})"
