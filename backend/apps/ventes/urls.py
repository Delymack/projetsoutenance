# backend/apps/ventes/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'ventes', views.VenteViewSet, basename='ventes')
router.register(r'reservations', views.ReservationViewSet, basename='reservations')
router.register(r'caisse', views.SessionCaisseViewSet, basename='caisse')

urlpatterns = [
    path('', include(router.urls)),
]
