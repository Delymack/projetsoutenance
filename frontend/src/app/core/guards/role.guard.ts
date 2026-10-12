import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';
import { UserRole } from '../models/product.model';

/**
 * RoleGuard : bloque une page selon le rôle.
 *
 * Usage sur une route :
 *   { path: 'dashboard', canActivate: [authGuard, roleGuard],
 *     data: { roles: ['admin', 'gestionnaire'] satisfies UserRole[] } }
 *
 * On lit `data.roles` : le guard reste générique et réutilisable.
 */
export const roleGuard: CanActivateFn = (route) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  const roles = (route.data?.['roles'] ?? []) as UserRole[];

  // Aucune restriction déclarée → accès libre (aux connectés).
  if (!roles.length) return true;

  if (auth.hasRole(roles)) return true;

  // Règles « 403 » : on renvoie vers la page d'accueil avec un paramètre,
  // plutôt que d'afficher une page vide. L'utilisateur est déjà connecté.
  return router.createUrlTree(['/'], { queryParams: { acces: 'refuse' } });
};

/** Fabrique un guard de rôle prêt à l'emploi (pratique pour des routes typées). */
export function roleGuardPour(...roles: UserRole[]): CanActivateFn {
  return (route) => {
    const auth = inject(AuthService);
    const router = inject(Router);
    if (roles.length === 0 || auth.hasRole(roles)) return true;
    return router.createUrlTree(['/'], { queryParams: { acces: 'refuse' } });
  };
}