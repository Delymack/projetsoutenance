from django.urls import path

from apps.parametres import views

app_name = 'parametres'

urlpatterns = [
    path('', views.ParametresView.as_view(), name='index'),
    path('exporter/', views.exporter, name='exporter'),
    path('importer/', views.importer, name='importer'),
    path('imprimer/', views.imprimeur, name='imprimer'),
    path('sauvegarde/creer/', views.creer_sauvegarde, name='sauvegarde-creer'),
    path('sauvegarde/<int:pk>/telecharger/', views.telecharger_sauvegarde, name='sauvegarde-telecharger'),
    path('sauvegarde/<int:pk>/supprimer/', views.supprimer_sauvegarde, name='sauvegarde-supprimer'),
]
