from rest_framework import permissions
from apps.accounts.models import User

class IsAdmin(permissions.BasePermission):
    """
    Permission globale autorisant uniquement les administrateurs.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.has_management_access)

class IsVendeur(permissions.BasePermission):
    """
    Permission autorisant uniquement les vendeurs.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == User.Role.VENDEUR)

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Autorise la lecture pour tous les utilisateurs authentifiés,
    mais restreint la modification aux administrateurs.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.has_management_access

class CanManageClients(permissions.BasePermission):
    """
    Administrateurs et vendeurs peuvent gérer (CRUD) les clients.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            request.user.role in [User.Role.ADMIN, User.Role.GESTIONNAIRE, User.Role.VENDEUR]
        )

class CanManageVentes(permissions.BasePermission):
    """
    Administrateurs et vendeurs peuvent créer et consulter les ventes.
    Seul l'administrateur peut modifier/annuler si nécessaire (logique supplémentaire possible).
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Le vendeur peut lire et créer, l'admin peut tout faire.
        if request.method in [*permissions.SAFE_METHODS, 'POST']:
            return request.user.role in [User.Role.ADMIN, User.Role.GESTIONNAIRE, User.Role.VENDEUR]
            
        return request.user.has_management_access
