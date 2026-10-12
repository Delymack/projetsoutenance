from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import uuid

from apps.clients.models import Client
from apps.produits.models import Produit


class Mode(models.TextChoices):
    """Vocabulaire des encaissements.

    Les codes ne bougent plus : une vente enregistrée doit rester relisible
    dans dix ans. Ce que le caissier peut réellement choisir est activé par le
    paramètre ``ventes_modes_paiement``.
    """

    ESPECES = 'ESPECES', _('Espèces')
    MVOLA = 'MVOLA', _('Mvola')
    ORANGE_MONEY = 'ORANGE_MONEY', _('Orange Money')
    AIRTEL_MONEY = 'AIRTEL_MONEY', _('Airtel Money')
    MOBILE_MONEY = 'MOBILE_MONEY', _('Mobile Money')
    CHEQUE = 'CHEQUE', _('Chèque')
    CARTE = 'CARTE', _('Carte bancaire')
    CREDIT = 'CREDIT', _('Compte client')


class Unite(models.TextChoices):
    BOUTEILLE = 'BOUTEILLE', _('Bouteille')
    PACK = 'PACK', _('Pack')
    CARTON = 'CARTON', _('Carton')


class Vente(models.Model):
    ModePaiement = Mode

    # Un opérateur identifié ou un chèque se rapproche ligne à ligne avec son
    # justificatif : sans référence, la clôture ne peut pas justifier
    # l'encaissement. La carte se rapproche via le terminal, et le mode
    # fourre-tout « Mobile Money » reste saisissable sans justificatif.
    MODES_A_REFERENCE_OBLIGATOIRE = (
        Mode.MVOLA, Mode.ORANGE_MONEY, Mode.AIRTEL_MONEY, Mode.CHEQUE,
    )

    class Statut(models.TextChoices):
        PAYEE = 'PAYEE', _('Payée')
        ANNULEE = 'ANNULEE', _('Annulée')

    reference = models.CharField(max_length=100, unique=True, verbose_name=_('Réf'), editable=False)
    # Client laissé vide pour une vente anonyme (client de passage) : le nom
    # donné au comptoir est alors porté par ``client_libelle`` sur le ticket.
    client = models.ForeignKey(
        Client, on_delete=models.PROTECT, null=True, blank=True,
        related_name='ventes', verbose_name=_('Client'),
    )
    client_libelle = models.CharField(max_length=150, blank=True, default='', verbose_name=_('Client de passage'))
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='ventes', verbose_name=_('Vendeur'),
    )
    session = models.ForeignKey(
        'ventes.SessionCaisse', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ventes', verbose_name=_('Session'),
    )

    date_vente = models.DateTimeField(auto_now_add=True, verbose_name=_('Date'))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('Total'))
    date_echeance = models.DateField(
        null=True, blank=True, verbose_name=_('Date d’échéance'),
    )
    # Barème fiscal figé à l’émission : modifier les paramètres ne réécrit pas
    # les factures déjà créées. NULL identifie les factures historiques.
    taux_tva = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        verbose_name=_('Taux de TVA appliqué'),
    )
    tva_incluse = models.BooleanField(
        null=True, blank=True, verbose_name=_('Prix TTC à l’émission'),
    )
    # Déjà encaissé avant la vente (réservation) : il reste « total − acompte ».
    acompte_anticipe = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('Acompte encaissé'))
    # Saisie à la caisse, distincte des promotions automatiques. Le motif est
    # obligatoire dès que le total n'est pas nul.
    remise_manuelle_totale = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('Remise manuelle'))
    motif_remise = models.CharField(max_length=255, blank=True, verbose_name=_('Motif'))
    montant_retourne = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('Montant retourné'))

    mode_paiement = models.CharField(
        max_length=20,
        choices=Mode.choices,
        default=Mode.ESPECES,
        verbose_name=_('Paiement'),
    )
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.PAYEE,
        verbose_name=_('Statut'),
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Création'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Maj'))

    class Meta:
        verbose_name = _('vente')
        verbose_name_plural = _('ventes')
        db_table = 'ventes_vente'
        ordering = ['-date_vente']
        indexes = [
            models.Index(fields=['date_vente'], name='vente_date_idx'),
            models.Index(fields=['date_echeance'], name='vente_echeance_idx'),
            models.Index(fields=['client', 'date_vente'], name='vente_client_date_idx'),
            models.Index(fields=['statut', 'date_vente'], name='vente_statut_date_idx'),
            models.Index(fields=['session', 'date_vente'], name='vente_session_date_idx'),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(total__gte=0), name='vente_total_non_negatif'),
            models.CheckConstraint(condition=models.Q(acompte_anticipe__gte=0), name='vente_acompte_non_negatif'),
            models.CheckConstraint(condition=models.Q(montant_retourne__gte=0), name='vente_retour_non_negatif'),
            models.CheckConstraint(
                condition=(
                    models.Q(taux_tva__isnull=True)
                    | models.Q(taux_tva__gte=0, taux_tva__lte=100)
                ),
                name='vente_tva_range',
            ),
        ]

    def __str__(self):
        return f"Vente {self.reference} - {self.client.nom if self.client else self.client_libelle or 'Client de passage'}"

    @property
    def nom_client(self):
        return self.client.nom if self.client else (self.client_libelle or _('Client de passage'))

    @property
    def net_a_encaiser(self):
        """Reste à encaisser : total moins l'acompte déjà versé."""
        return Decimal(self.total) - Decimal(self.acompte_anticipe)

    @property
    def a_des_retours(self):
        return self.retours.exists() or Decimal(self.montant_retourne) > 0

    @property
    def est_paiement_mixte(self):
        """Vente réglée par plusieurs encaissements de modes différents."""
        modes = self.paiements.values_list('mode', flat=True)
        return len(set(modes)) > 1

    @property
    def total_net(self):
        """Ce qui reste dû au comptoir une fois les retours déduits."""
        return Decimal(self.total) - Decimal(self.montant_retourne)

    @property
    def details_tva(self):
        """Décomposition du total TTC avec le taux figé à l’émission."""
        if self.taux_tva is None or self.tva_incluse is None:
            return None
        from apps.parametres.tva import decomposition
        return decomposition(self.total_net, self.taux_tva, True)

    def save(self, *args, **kwargs):
        if not self.reference:
            # Préfixe FAC- : c'est le numéro qui figure sur le ticket et le
            # reçu, celui que le client relit en boutique.
            self.reference = f"FAC-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)


class LigneVente(models.Model):
    Unite = Unite

    vente = models.ForeignKey(Vente, on_delete=models.CASCADE, related_name='lignes', verbose_name=_('Vente'))
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name='lignes_vente', verbose_name=_('Produit'))
    # Promotion qui a réellement accordé la remise sur cette ligne.
    promotion = models.ForeignKey(
        'promotions.Promotion', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lignes_vente', verbose_name=_('Promotion'),
    )

    quantite = models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name=_('Quantité'))
    unite = models.CharField(max_length=20, choices=Unite.choices, default=Unite.BOUTEILLE, verbose_name=_('Unité'))
    contenance = models.PositiveIntegerField(default=1, verbose_name=_('Contenance'))
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('Prix U'))
    remise = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_('Remise'))
    remise_manuelle = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_('Remise manuelle'))
    sous_total = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('Sous-total'))

    class Meta:
        verbose_name = _('ligne de vente')
        verbose_name_plural = _('lignes de vente')
        db_table = 'ventes_ligne_vente'
        constraints = [
            models.UniqueConstraint(fields=['vente', 'produit'], name='unique_vente_produit'),
            models.CheckConstraint(condition=models.Q(quantite__gte=1), name='ligne_vente_quantite_min'),
            models.CheckConstraint(condition=models.Q(contenance__gte=1), name='ligne_vente_contenance_min'),
            models.CheckConstraint(condition=models.Q(sous_total__gte=0), name='ligne_vente_sous_total_non_negatif'),
        ]

    @property
    def remise_promotion(self):
        """Part de la remise automatique, remise manuelle exclue."""
        return max(Decimal(self.remise) - Decimal(self.remise_manuelle), Decimal('0.00'))

    @property
    def quantite_bouteilles(self):
        return self.quantite * max(int(self.contenance or 1), 1)

    @property
    def quantite_retournee(self):
        return sum(r.quantite for r in self.retours.all())

    @property
    def quantite_restante(self):
        return max(self.quantite - self.quantite_retournee, 0)

    def __str__(self):
        return f"{self.quantite} x {self.produit.nom} (Vente: {self.vente.reference})"


class Paiement(models.Model):
    """Encaissement rattaché à une vente ou à une réservation, jamais aux deux."""

    vente = models.ForeignKey(
        Vente, on_delete=models.CASCADE, null=True, blank=True,
        related_name='paiements', verbose_name=_('Vente'),
    )
    reservation = models.ForeignKey(
        'ventes.Reservation', on_delete=models.CASCADE, null=True, blank=True,
        related_name='paiements', verbose_name=_('Commande'),
    )
    mode = models.CharField(max_length=20, choices=Mode.choices, verbose_name=_('Mode'))
    montant = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name=_('Montant'),
    )
    reference = models.CharField(max_length=100, blank=True, verbose_name=_('Référence'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Encaissement'))

    class Meta:
        verbose_name = _('paiement')
        verbose_name_plural = _('paiements')
        db_table = 'ventes_paiement'
        ordering = ['id']
        constraints = [
            models.CheckConstraint(condition=models.Q(montant__gt=0), name='paiement_montant_positif'),
            models.CheckConstraint(
                condition=(
                    models.Q(reservation__isnull=True, vente__isnull=False)
                    | models.Q(reservation__isnull=False, vente__isnull=True)
                ),
                name='paiement_une_seule_origine',
            ),
        ]

    def __str__(self):
        return f"{self.get_mode_display()} {self.montant}"


class Reservation(models.Model):
    class Source(models.TextChoices):
        INTERNE = 'INTERNE', _('Saisie interne')
        SITE = 'SITE', _('Site web')

    class ModeReception(models.TextChoices):
        RETRAIT = 'RETRAIT', _('Retrait en boutique')
        LIVRAISON = 'LIVRAISON', _('Livraison')

    class Statut(models.TextChoices):
        EN_ATTENTE = 'EN_ATTENTE', _('En attente')
        ACOMPTE = 'ACOMPTE', _('Acompte versé')
        SOLDEE = 'SOLDEE', _('Soldée')
        ANNULEE = 'ANNULEE', _('Annulée')
        EXPIREE = 'EXPIREE', _('Expirée')

    class ValidationStatut(models.TextChoices):
        A_VALIDER = 'A_VALIDER', _('À valider')
        VALIDEE = 'VALIDEE', _('Validée')
        REFUSEE = 'REFUSEE', _('Refusée')

    reference = models.CharField(max_length=100, unique=True, verbose_name=_('Réf'), editable=False)
    source = models.CharField(
        max_length=12, choices=Source.choices, default=Source.INTERNE, verbose_name=_('Origine'),
    )
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='reservations', verbose_name=_('Client'))
    compte_client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='commandes_site', verbose_name=_('Compte client'),
    )
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='reservations', null=True, blank=True, verbose_name=_('Créé par'),
    )
    vente = models.ForeignKey(
        'ventes.Vente', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reservation', verbose_name=_('Vente générée'),
    )

    # Passée à « Expirée » si la date de rétention est dépassée sans solde.
    statut = models.CharField(
        max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE, verbose_name=_('Statut'),
    )
    validation_statut = models.CharField(
        max_length=12, choices=ValidationStatut.choices, null=True, blank=True,
        verbose_name=_('Validation vendeur'),
    )
    validation_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='validations_commandes_site', verbose_name=_('Validée par'),
    )
    validation_le = models.DateTimeField(null=True, blank=True, verbose_name=_('Date de validation'))
    motif_refus = models.CharField(max_length=255, blank=True, default='', verbose_name=_('Motif du refus'))
    # Montant complet attendu à la livraison.
    montant_total = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('Montant total'))
    taux_tva = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        verbose_name=_('Taux de TVA réservé'),
    )
    tva_incluse = models.BooleanField(
        null=True, blank=True, verbose_name=_('Prix TTC à la commande'),
    )
    # Déjà encaissé : le solde à payer est la différence avec le montant total.
    montant_acompte = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('Acompte reçu'))
    mode_reception = models.CharField(
        max_length=12, choices=ModeReception.choices, default=ModeReception.RETRAIT,
        verbose_name=_('Réception'),
    )
    adresse_livraison = models.TextField(blank=True, default='', verbose_name=_('Adresse de livraison'))
    date_expiration = models.DateField(
        null=True, blank=True, verbose_name=_("Retenue jusqu'au"),
    )
    note = models.CharField(max_length=255, blank=True, verbose_name=_('Note'))

    date_creation = models.DateTimeField(auto_now_add=True, verbose_name=_('Création'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Maj'))

    class Meta:
        verbose_name = _('commande')
        verbose_name_plural = _('commandes')
        db_table = 'ventes_reservation'
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['statut', 'date_creation'], name='res_statut_date_idx'),
            models.Index(fields=['client', 'statut'], name='res_client_statut_idx'),
            models.Index(fields=['mode_reception', 'statut'], name='res_mode_statut_idx'),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(montant_total__gte=0), name='reservation_total_non_negatif'),
            models.CheckConstraint(
                condition=(
                    models.Q(taux_tva__isnull=True)
                    | models.Q(taux_tva__gte=0, taux_tva__lte=100)
                ),
                name='reservation_tva_range',
            ),
        ]

    def __str__(self):
        return f"Commande {self.reference}"

    @property
    def solde_du(self):
        """Reste à payer : montant total moins acompte déjà reçu.

        Une réservation soldée ou annulée ne doit plus rien afficher comme dû,
        même si l'acompte n'a representé qu'une part du total.
        """
        if self.statut in (self.Statut.SOLDEE, self.Statut.ANNULEE):
            return Decimal('0.00')
        return Decimal(self.montant_total) - Decimal(self.montant_acompte)

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"RES-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)


class MessageClient(models.Model):
    class Statut(models.TextChoices):
        NOUVEAU = 'NOUVEAU', _('Nouveau')
        TRAITE = 'TRAITE', _('Traité')
        ARCHIVE = 'ARCHIVE', _('Archivé')

    nom = models.CharField(max_length=150, verbose_name=_('Nom'))
    telephone = models.CharField(max_length=30, blank=True, verbose_name=_('Téléphone'))
    email = models.EmailField(blank=True, verbose_name=_('Email'))
    sujet = models.CharField(max_length=150, verbose_name=_('Sujet'))
    message = models.TextField(max_length=3000, verbose_name=_('Message'))
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.NOUVEAU, verbose_name=_('Statut'),
    )
    cree_le = models.DateTimeField(auto_now_add=True, verbose_name=_('Reçu le'))

    class Meta:
        verbose_name = _('message client')
        verbose_name_plural = _('messages clients')
        db_table = 'ventes_message_client'
        ordering = ['-cree_le']

    def __str__(self):
        return f'{self.sujet} · {self.nom}'


class LigneReservation(models.Model):
    reservation = models.ForeignKey(
        Reservation, on_delete=models.CASCADE, related_name='lignes', verbose_name=_('Commande'),
    )
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name='lignes_reservation', verbose_name=_('Produit'))

    quantite = models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name=_('Quantité'))
    unite = models.CharField(max_length=20, choices=Unite.choices, default=Unite.BOUTEILLE, verbose_name=_('Unité'))
    contenance = models.PositiveIntegerField(default=1, verbose_name=_('Contenance'))
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('Prix U'))

    @property
    def sous_total(self):
        """Montant TTC de la ligne : quantité × prix unitaire commandé."""
        return self.quantite * self.prix_unitaire

    class Meta:
        verbose_name = _('ligne de commande')
        verbose_name_plural = _('lignes de commande')
        db_table = 'ventes_ligne_reservation'
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['reservation', 'produit'], name='unique_reservation_produit'),
        ]

    def __str__(self):
        return f"{self.quantite} x {self.produit.nom}"


class RetourVente(models.Model):
    vente = models.ForeignKey(Vente, on_delete=models.CASCADE, related_name='retours', verbose_name=_('Vente'))
    ligne = models.ForeignKey(LigneVente, on_delete=models.CASCADE, related_name='retours', verbose_name=_('Ligne'))
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='retours', verbose_name=_('Enregistré par'),
    )

    quantite = models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name=_('Quantité retournée'))
    # Produit défectueux, erreur de caisse, produit non ag…
    motif = models.CharField(max_length=255, verbose_name=_('Motif'))
    mode_remboursement = models.CharField(
        max_length=20, choices=Mode.choices, default=Mode.ESPECES, verbose_name=_('Remboursé par'),
    )
    montant_rembourse = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('Montant remboursé'))
    reference = models.CharField(max_length=100, blank=True, verbose_name=_('Référence'))
    date_retour = models.DateTimeField(auto_now_add=True, verbose_name=_('Date'))

    class Meta:
        verbose_name = _('retour de vente')
        verbose_name_plural = _('retours de vente')
        db_table = 'ventes_retour'
        ordering = ['-date_retour']
        constraints = [
            models.CheckConstraint(condition=models.Q(quantite__gte=1), name='retour_quantite_min'),
            models.CheckConstraint(condition=models.Q(montant_rembourse__gte=0), name='retour_montant_non_negatif'),
        ]

    def __str__(self):
        return f"Retour {self.reference_retour}"

    @property
    def reference_retour(self):
        return f"RET-{self.id:06d}"


class SessionCaisse(models.Model):
    """Session de caisse : journée ouverte puis close, avec son instantané."""

    class Statut(models.TextChoices):
        OUVERTE = 'OUVERTE', _('Ouverte')
        FERMEE = 'FERMEE', _('Clôturée')

    # Journée couverte par la session.
    date_ventes = models.DateField(verbose_name=_('Journée'))
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.OUVERTE, verbose_name=_('Statut'))

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='sessions_caisse',
        verbose_name=_('Caissier'),
    )

    date_ouverture = models.DateTimeField(default=timezone.now, verbose_name=_('Ouverture'))
    date_cloture = models.DateTimeField(null=True, blank=True, verbose_name=_('Clôture'))

    ca_especes = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('CA espèces'))
    ca_mobile_money = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('CA Mobile Money'))
    ca_carte = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('CA carte'))
    ca_credit = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('CA compte client'))
    ca_total = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('CA total'))
    ca_rembourse = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('CA remboursé'))
    ca_net = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('CA net'))

    nb_tickets = models.PositiveIntegerField(default=0, verbose_name=_('Tickets'))
    nb_articles = models.PositiveIntegerField(default=0, verbose_name=_('Articles vendus'))
    nb_retours = models.PositiveIntegerField(default=0, verbose_name=_('Retours'))
    remise_totale = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('Remises'))
    remise_manuelle_totale = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('Remises manuelles'))

    fonds_de_caisse = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('Fonds de caisse'))
    especes_reel = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('Espèces comptées'))
    ecart = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('Écart de caisse'))

    note = models.CharField(max_length=255, blank=True, verbose_name=_('Note'))

    class Meta:
        verbose_name = _('session de caisse')
        verbose_name_plural = _('sessions de caisse')
        db_table = 'ventes_session_caisse'
        ordering = ['-date_ventes', 'statut']
        constraints = [
            models.UniqueConstraint(
                condition=models.Q(statut='OUVERTE'),
                fields=['date_ventes', 'utilisateur'],
                name='session_ouverte_unique_par_jour_caissier',
            ),
            models.UniqueConstraint(
                condition=models.Q(statut='FERMEE'),
                fields=['date_ventes', 'utilisateur'],
                name='session_fermee_unique_par_jour_caissier',
            ),
        ]

    @property
    def attendu_en_caisse(self):
        """Ce que le caissier doit trouver dans le tiroir à la clôture."""
        return Decimal(self.fonds_de_caisse) + Decimal(self.ca_especes)

    def __str__(self):
        return f"Session {self.date_ventes} - {self.ca_total} {settings.SOCIETE.get('devise', 'Ar')}"

    @classmethod
    def statistiques_jour(cls, jour):
        """
        Agrégats des ventes PAYEE pour la journée donnée (hors archivage).
        Retourne un dictionnaire utilisable par le rapport de caisse en direct.
        """
        from apps.ventes.services import CaisseService
        return CaisseService.rapport_du_jour(jour)