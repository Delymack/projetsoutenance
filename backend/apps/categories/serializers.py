from rest_framework import serializers
from apps.categories.models import Categorie

class CategorieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categorie
        fields = '__all__'
        read_only_fields = ['date_creation', 'updated_at']
