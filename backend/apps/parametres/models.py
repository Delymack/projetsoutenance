from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class Section(models.TextChoices):
    SOCIETE = 'SOCIETE', _('Société & identité')
    VENTES = 'VENTES', _('Règles métier')
    POS = 'POS', _('Caisse & documents')
    SECURITE = 'SECURITE', _('Sécurité & accès')
    APPEARANCE = 'APPEARANCE', _('Apparence')
    ACCUEIL = 'ACCUEIL', _('Page d’accueil')
    SYSTEME = 'SYSTEME', _('Système')


class TypeParam(models.TextChoices):
    TEXT = 'TEXT', _('Texte')
    TEXTAREA = 'TEXTAREA', _('Texte long')
    EMAIL = 'EMAIL', _('E-mail')
    INT = 'INT', _('Nombre entier')
    DECIMAL = 'DECIMAL', _('Nombre décimal')
    BOOL = 'BOOL', _('Interrupteur')
    CHOICE = 'CHOICE', _('Choix')
    #: Plusieurs cases cochées dans un ordre choisi : le stock est une liste
    #: (les modes de paiement acceptés, par exemple), pas une valeur unique.
    MULTI = 'MULTI', _('Liste de choix')


class Parametre(models.Model):
    """Clé de configuration valorisable, groupée par section métier."""

    section = models.CharField(max_length=20, choices=Section.choices, verbose_name=_('Section'))
    cle = models.CharField(max_length=80, unique=True, verbose_name=_('Clé'))
    libelle = models.CharField(max_length=120, verbose_name=_('Libellé'))
    type = models.CharField(max_length=20, choices=TypeParam.choices, verbose_name=_('Type'))
    valeur = models.TextField(blank=True, null=True, verbose_name=_('Valeur'))
    options = models.JSONField(blank=True, default=dict, verbose_name=_('Options'))
    aide = models.TextField(blank=True, verbose_name=_('Aide'))
    ordre = models.PositiveIntegerField(default=0, verbose_name=_('Ordre'))
    modifie_le = models.DateTimeField(auto_now=True, verbose_name=_('Modifié le'))

    class Meta:
        verbose_name = _('paramètre')
        verbose_name_plural = _('paramètres')
        db_table = 'parametres_parametre'
        ordering = ['section', 'ordre', 'cle']

    def __str__(self):
        return f'{self.cle} = {self.valeur or "—"}'


class EntreeJournal(models.Model):
    """Trace les modifications de configuration (audit, whodunnit, avant/après)."""

    class Action(models.TextChoices):
        MODIF = 'MODIF', _('Modification')
        IMPORT = 'IMPORT', _('Import')
        RESET = 'RESET', _('Réinitialisation')
        MAINTENANCE = 'MAINTENANCE', _('Maintenance')

    action = models.CharField(max_length=20, choices=Action.choices, verbose_name=_('Action'))
    section = models.CharField(max_length=20, choices=Section.choices, blank=True, verbose_name=_('Section'))
    cle = models.CharField(max_length=80, blank=True, verbose_name=_('Clé'))
    libelle = models.CharField(max_length=120, blank=True, verbose_name=_('Libellé'))
    avant = models.TextField(blank=True, null=True, verbose_name=_('Avant'))
    apres = models.TextField(blank=True, null=True, verbose_name=_('Après'))
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='entrees_journal_parametres', verbose_name=_('Utilisateur')
    )
    ip = models.GenericIPAddressField(null=True, blank=True, verbose_name=_('IP'))
    date = models.DateTimeField(auto_now_add=True, verbose_name=_('Date'))

    class Meta:
        verbose_name = _('entrée de journal')
        verbose_name_plural = _("entrées du journal d'activité")
        db_table = 'parametres_journal'
        ordering = ['-date']

    def __str__(self):
        return f'{self.get_action_display()} — {self.cle}'

def chemin_sauvegarde(instance, filename):
    """Range les dumps dans ``media/sauvegardes/AAAA/MM/``."""
    from django.utils import timezone

    maintenant = timezone.now()
    return f'sauvegardes/{maintenant:%Y}/{maintenant:%m}/{filename}'


class Sauvegarde(models.Model):
    """Une copie de la base de données, conservée et téléchargeable.

    Le fichier vit dans ``MEDIA_ROOT`` ; la ligne n'en garde que ce qu'il faut
    pour l'afficher (format, taille, auteur) et la purger. Aucune restauration
    n'est proposée ici : écraser la base courante depuis une page web serait
    la pire manière de perdre les données.
    """

    class Format(models.TextChoices):
        SQLITE = 'sqlite3', _('Copie SQLite')
        PGDUMP = 'pgdump', _('Dump PostgreSQL')
        JSON = 'json', _('Export JSON compressé')

    class Statut(models.TextChoices):
        EN_COURS = 'EN_COURS', _('En cours')
        REUSSIE = 'REUSSIE', _('Réussie')
        ECHEC = 'ECHEC', _('Échouée')

    fichier = models.FileField(upload_to=chemin_sauvegarde, verbose_name=_('Fichier'))
    format = models.CharField(max_length=10, choices=Format.choices, verbose_name=_('Format'))
    engine = models.CharField(max_length=40, verbose_name=_('Moteur'))
    taille = models.PositiveBigIntegerField(default=0, verbose_name=_('Taille (octets)'))
    nb_tables = models.PositiveIntegerField(default=0, verbose_name=_('Tables'))
    nb_lignes = models.PositiveIntegerField(default=0, verbose_name=_('Lignes'))
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.EN_COURS,
        verbose_name=_('Statut'),
    )
    erreur = models.TextField(blank=True, verbose_name=_('Erreur'))
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='sauvegardes', verbose_name=_('Utilisateur'),
    )
    date = models.DateTimeField(auto_now_add=True, verbose_name=_('Date'))

    class Meta:
        verbose_name = _('sauvegarde')
        verbose_name_plural = _('sauvegardes')
        db_table = 'parametres_sauvegardes'
        ordering = ['-date']

    def __str__(self):
        return f'{self.date:%d/%m/%Y %H:%M} — {self.get_format_display()}'

    @property
    def taille_lisible(self):
        octets = float(self.taille or 0)
        for unite in ('o', 'Ko', 'Mo', 'Go'):
            if octets < 1024 or unite == 'Go':
                return f'{octets:.0f} {unite}' if unite == 'o' else f'{octets:.1f} {unite}'
            octets /= 1024

    @property
    def disponible(self):
        return self.statut == self.Statut.REUSSIE and bool(self.fichier)
