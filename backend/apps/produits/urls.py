# backend/apps/produits/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'produits', views.ProduitViewSet, basename='produits')

urlpatterns = [
    path('', include(router.urls)),
]
