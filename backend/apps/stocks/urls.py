# backend/apps/stocks/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'stocks', views.StockViewSet, basename='stocks')
router.register(r'mouvements', views.MouvementStockViewSet, basename='mouvements-stock')

urlpatterns = [
    path('', include(router.urls)),
]
