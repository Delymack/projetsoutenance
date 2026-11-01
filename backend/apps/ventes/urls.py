# backend/apps/ventes/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views
from .contact_api import ContactMessageView

router = DefaultRouter()
router.register(r'ventes', views.VenteViewSet, basename='ventes')
router.register(r'reservations', views.ReservationViewSet, basename='reservations')
router.register(r'caisse', views.SessionCaisseViewSet, basename='caisse')

urlpatterns = [
    path('contact/messages/', ContactMessageView.as_view(), name='contact-message-api'),
    path('', include(router.urls)),
]
