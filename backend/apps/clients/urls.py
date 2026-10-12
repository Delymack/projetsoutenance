# backend/apps/clients/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'clients', views.ClientViewSet, basename='clients')
router.register(r'reglements-clients', views.ReglementViewSet, basename='reglements-client')

urlpatterns = [
    path('', include(router.urls)),
]
