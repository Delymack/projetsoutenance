from rest_framework import serializers
from apps.clients.models import Client, ReglementClient

class ClientSerializer(serializers.ModelSerializer):
    niveau_label = serializers.CharField(source='get_niveau_display', read_only=True)
    credit_disponible = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    peut_acheter_a_credit = serializers.BooleanField(read_only=True)
    est_en_depassement_credit = serializers.BooleanField(read_only=True)
    taux_remise_fidelite = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    points_pour_prochain_palier = serializers.IntegerField(read_only=True)

    class Meta:
        model = Client
        fields = '__all__'
        read_only_fields = ['date_creation', 'updated_at', 'points_fidelite', 'niveau', 'solde_du']


class ReglementClientSerializer(serializers.ModelSerializer):
    client_nom = serializers.SerializerMethodField()

    class Meta:
        model = ReglementClient
        fields = ['id', 'client', 'client_nom', 'montant', 'mode', 'reference_facture', 'note', 'utilisateur', 'date_reglement']
        read_only_fields = ['utilisateur', 'date_reglement']

    def get_client_nom(self, obj):
        return str(obj.client)