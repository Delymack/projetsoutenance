from rest_framework import viewsets
from apps.categories.models import Categorie
from apps.categories.serializers import CategorieSerializer
from apps.accounts.permissions import IsAdminOrReadOnly

class CategorieViewSet(viewsets.ModelViewSet):
    queryset = Categorie.objects.all()
    serializer_class = CategorieSerializer
    permission_classes = [IsAdminOrReadOnly]
