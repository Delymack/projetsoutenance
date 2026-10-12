from django.db import models
from django.utils.translation import gettext_lazy as _

class Categorie(models.Model):
    nom = models.CharField(max_length=100, unique=True, verbose_name=_('Nom'))
    description = models.TextField(blank=True, null=True, verbose_name=_('Description'))
    statut = models.BooleanField(default=True, verbose_name=_('Actif'))
    
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name=_('Création'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Maj'))

    class Meta:
        verbose_name = _('catégorie')
        verbose_name_plural = _('catégories')
        db_table = 'categories_categorie'
        ordering = ['nom']

    def __str__(self):
        return self.nom
