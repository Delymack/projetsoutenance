"""Mode maintenance : bloque le back-office pour le personnel (sans les
superutilisateurs) quand le paramètre ``systeme_maintenance`` est actif."""

from django.shortcuts import render

from apps.parametres.services import get_param

_FREE_PREFIXES = ('/admin/login/', '/admin/logout/', '/static/', '/media/', '/api/')


class MaintenanceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if get_param('systeme_maintenance', False):
            user = getattr(request, 'user', None)
            is_super = bool(user and user.is_authenticated and user.is_superuser)
            if not is_super and request.path.startswith('/admin') and not request.path.startswith(_FREE_PREFIXES):
                return render(request, 'admin/parametres/maintenance.html', status=503)
        return self.get_response(request)