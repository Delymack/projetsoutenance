from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from apps.categories.models import Categorie
from apps.categories.serializers import CategorieSerializer
from apps.accounts.permissions import IsAdminOrReadOnly


class CategorieViewSet(viewsets.ModelViewSet):
    queryset = Categorie.objects.all()
    serializer_class = CategorieSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        return super().get_permissions()
