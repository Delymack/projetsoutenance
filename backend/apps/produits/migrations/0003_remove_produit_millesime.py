from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('produits', '0002_produit_produit_cat_statut_idx_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='produit',
            name='millesime',
        ),
    ]
