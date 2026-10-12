from rest_framework import serializers
from apps.stocks.models import Stock, MouvementStock
from apps.produits.serializers import ProduitSerializer
from apps.accounts.serializers import UserSerializer # Supposant qu'il existe

class StockSerializer(serializers.ModelSerializer):
    etat_stock = serializers.ReadOnlyField()
    est_en_rupture = serializers.ReadOnlyField()
    est_en_alerte = serializers.ReadOnlyField()
    besoin_reappro = serializers.ReadOnlyField()

    class Meta:
        model = Stock
        fields = [
            'id', 'produit', 'quantite', 'seuil_alerte', 'etat_stock',
            'est_en_rupture', 'est_en_alerte', 'besoin_reappro', 'date_mise_a_jour',
        ]
        read_only_fields = [
            'date_mise_a_jour', 'etat_stock', 'est_en_rupture', 'est_en_alerte', 'besoin_reappro',
        ]


class StockDetailSerializer(StockSerializer):
    produit = ProduitSerializer(read_only=True)


class MouvementStockSerializer(serializers.ModelSerializer):
    utilisateur_nom = serializers.ReadOnlyField(source='utilisateur.username')
    produit_nom = serializers.ReadOnlyField(source='produit.nom')
    type_mouvement_display = serializers.CharField(source='get_type_mouvement_display', read_only=True)

    class Meta:
        model = MouvementStock
        fields = [
            'id', 'produit', 'produit_nom', 'quantite', 
            'type_mouvement', 'type_mouvement_display', 
            'description', 'reference_id', 'utilisateur', 
            'utilisateur_nom', 'date_mouvement'
        ]
        read_only_fields = ['date_mouvement', 'utilisateur']
