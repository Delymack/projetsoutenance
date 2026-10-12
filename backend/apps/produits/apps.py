from django.apps import AppConfig

class ProduitsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.produits'
    verbose_name = '🍷 Vins & Produits'

    def ready(self):
        from apps.produits import signals  # noqa: F401  (garantit une ligne de stock par produit)
