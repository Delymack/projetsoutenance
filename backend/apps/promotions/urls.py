# backend/apps/promotions/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'promotions', views.PromotionViewSet, basename='promotions')

urlpatterns = [
    path(
        'promotions/simuler/',
        views.SimulerVentePromoView.as_view({'post': 'list'}),
        name='promotions-simuler',
    ),
    path(
        'promotions/chevauchements/',
        views.ChevauchementsView.as_view({'get': 'list'}),
        name='promotions-chevauchements',
    ),
    path(
        'promotions/prix-produits/',
        views.PrixProduitsView.as_view({'get': 'list'}),
        name='promotions-prix-produits',
    ),
    path('', include(router.urls)),
]
