# backend/config/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from apps.dashboard.views import (
    ApercuView,
    DashboardView,
    RapportVentesView,
    RapportsView,
    VentesParJourView,
)
from apps.parametres.api import AccueilView
from apps.ventes.views_pos import POSView
from apps.ventes.views_zreport import ZReportView
from apps.ventes.views_client import commande_client, contact_client

urlpatterns = [
    path('', RedirectView.as_view(url='/admin/', permanent=False)),
    # Pages publiques serveur (commande en ligne, contact).
    path('commande/', commande_client, name='commande-client'),
    path('contact/', contact_client, name='contact-client'),
    # Espace d'authentification avancé (inscription, 2FA, lien magique, sécurité).
    # Déclaré AVANT admin.site.urls pour que /admin/signup/ …, /admin/2fa/…
    # ne soient pas captées par le back-office.
    path('admin/', include('apps.accounts.pages_urls')),
    path('admin/caisse/', POSView.as_view(), name='caisse-enregistreuse'),
    path('admin/zreport/', ZReportView.as_view(), name='zreport'),
    path('admin/rapports/', RapportsView.as_view(), name='rapports'),
    path('admin/parametres/', include('apps.parametres.urls')),
    path('admin/', admin.site.urls),

    # Authentification
    path('api/auth/', include('apps.accounts.urls')),

    # Google login (allauth)
    path('accounts/signup/', RedirectView.as_view(url='/admin/login/', permanent=False)),
    path('accounts/', include('allauth.urls')),

    # Dashboard
    path('api/dashboard/', DashboardView.as_view(), name='dashboard'),
    path('api/dashboard/apercu/', ApercuView.as_view(), name='dashboard-apercu'),
    path('api/dashboard/ventes-par-jour/', VentesParJourView.as_view(), name='dashboard-ventes-par-jour'),
    path('api/rapports/ventes/', RapportVentesView.as_view(), name='rapport-ventes'),

    # API endpoints
    # Page principale du frontend : textes + couleurs (public).
    path('api/accueil/', AccueilView.as_view(), name='accueil-api'),
    path('api/', include('apps.ventes.urls')),
    path('api/', include('apps.produits.urls')),
    path('api/', include('apps.categories.urls')),
    path('api/', include('apps.clients.urls')),
    path('api/', include('apps.promotions.urls')),
    path('api/', include('apps.stocks.urls')),
    path('api/', include('apps.clients.fidelite_urls')),
]

# En développement, Django sert lui-même les photos téléversées
# (`MEDIA_ROOT`) : sans cette route, l'image enregistrée sur un produit
# répond 404 et n'apparaît ni en boutique ni dans l'aperçu de la fiche.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)