from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _
from decimal import Decimal

class Client(models.Model):
    class Niveau(models.TextChoices):
        BRONZE = 'BRONZE', _('Dégustateur')
        ARGENT = 'ARGENT', _('Connaisseur')
        OR = 'OR', _('Ambassadeur')

    class TypeClient(models.TextChoices):
        """Segments de clientèle : le critère de ciblage des promotions.

        Restaurant et hôtel se distinguent du revendeur : ils rachètent en
        volume, sur des horaires de service, avec des besoins de livraison —
        et c'est exactement ce qui justifie un traitement commercial distinct.
        """
        PARTICULIER = 'PARTICULIER', _('Particulier')
        REVENDEUR = 'REVENDEUR', _('Revendeur')
        RESTAURANT = 'RESTAURANT', _('Restaurant')
        HOTEL = 'HOTEL', _('Hôtel')

    SEUIL_ARGENT = 3000
    SEUIL_OR = 15000

    nom = models.CharField(max_length=100, verbose_name=_('Nom'))
    prenom = models.CharField(max_length=100, verbose_name=_('Prénom'))
    telephone = models.CharField(max_length=20, verbose_name=_('Téléphone'))
    email = models.EmailField(blank=True, null=True, verbose_name=_('Email'))
    adresse = models.TextField(blank=True, null=True, verbose_name=_('Adresse'))

    points_fidelite = models.PositiveIntegerField(default=0, verbose_name=_('Points'))
    type_client = models.CharField(
        max_length=20,
        choices=TypeClient.choices,
        default=TypeClient.PARTICULIER,
        verbose_name=_('Type'),
    )
    niveau = models.CharField(
        max_length=20,
        choices=Niveau.choices,
        default=Niveau.BRONZE,
        verbose_name=_('Niveau')
    )
    max_credit = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name=_('Plafond crédit'),
    )
    solde_du = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name=_('Encours'),
    )

    date_creation = models.DateTimeField(auto_now_add=True, verbose_name=_('Création'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Maj'))

    class Meta:
        verbose_name = _('client')
        verbose_name_plural = _('clients')
        db_table = 'clients_client'
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['telephone'], name='client_telephone_idx'),
            models.Index(fields=['nom', 'prenom'], name='client_nom_prenom_idx'),
            models.Index(fields=['type_client', 'niveau'], name='client_type_niveau_idx'),
            models.Index(fields=['date_creation'], name='client_creation_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(max_credit__gte=0), name='client_max_credit_non_negatif'
            ),
            models.CheckConstraint(
                condition=models.Q(solde_du__gte=0), name='client_solde_du_non_negatif'
            ),
        ]

    def __str__(self):
        return f"{self.nom} {self.prenom}"

    def save(self, *args, **kwargs):
        # Le niveau suit automatiquement le capital de points.
        if self.points_fidelite >= self.SEUIL_OR:
            self.niveau = self.Niveau.OR
        elif self.points_fidelite >= self.SEUIL_ARGENT:
            self.niveau = self.Niveau.ARGENT
        else:
            self.niveau = self.Niveau.BRONZE
        super().save(*args, **kwargs)

    @staticmethod
    def points_pour_montant(montant):
        """Points gagnés pour un montant encaissé (1 pt par tranche de points_regle Ar)."""
        regle = int(getattr(settings, 'SOCIETE', {}).get('points_regle', 1000))
        if regle <= 0:
            return 0
        return int(montant // regle)

    @property
    def credit_disponible(self):
        return max(self.max_credit - self.solde_du, 0)

    @property
    def peut_acheter_a_credit(self):
        return self.max_credit > 0 and self.credit_disponible > 0

    @property
    def est_en_depassement_credit(self):
        """Indique si le solde dû a atteint ou excédé le plafond de crédit autorisé."""
        return self.max_credit > 0 and self.solde_du >= self.max_credit

    @property
    def taux_remise_fidelite(self):
        """Taux de remise automatique selon le statut fidélité (BRONZE=0%, ARGENT=5%, OR=10%)."""
        if self.niveau == self.Niveau.OR:
            return Decimal('10.00')
        if self.niveau == self.Niveau.ARGENT:
            return Decimal('5.00')
        return Decimal('0.00')

    @property
    def points_pour_prochain_palier(self):
        """Points restants à acquérir pour atteindre le niveau VIP supérieur."""
        if self.points_fidelite < self.SEUIL_ARGENT:
            return self.SEUIL_ARGENT - self.points_fidelite
        if self.points_fidelite < self.SEUIL_OR:
            return self.SEUIL_OR - self.points_fidelite
        return 0


class ReglementClient(models.Model):
    class Mode(models.TextChoices):
        ESPECES = 'ESPECES', _('Espèces')
        MOBILE_MONEY = 'MOBILE_MONEY', _('Mobile Money')
        CARTE = 'CARTE', _('Carte')

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='reglements', verbose_name=_('Client'))
    montant = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name=_('Montant'),
    )
    mode = models.CharField(
        max_length=20, choices=Mode.choices, default=Mode.ESPECES, verbose_name=_('Mode'),
    )
    reference_facture = models.CharField(max_length=100, blank=True, verbose_name=_('Réf. facture'))
    note = models.CharField(max_length=255, blank=True, verbose_name=_('Note'))
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True,
        related_name='reglements_saisis',
        verbose_name=_('Encaissé par')
    )
    date_reglement = models.DateTimeField(auto_now_add=True, verbose_name=_('Date'))

    class Meta:
        verbose_name = _('règlement client')
        verbose_name_plural = _('règlements clients')
        db_table = 'clients_reglement'
        ordering = ['-date_reglement']

    def __str__(self):
        return f"Règlement {self.client} - {self.montant}"