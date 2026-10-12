import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

/**
 * AuthGuard : bloque les pages nécessitant un JWT.
 *
 * Fonctionnel (CanActivateFn) plutôt que classe : plus léger, tree-shakeable,
 * et le comportement est entièrement lisible sur la route.
 *
 * - mémorise la page demandée dans `returnUrl` pour rediriger après connexion ;
 * - si l'utilisateur est connecté mais que le rôle ne suffit pas, RoleGuard prend le relais.
 */
export const authGuard: CanActivateFn = (_route, etat) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (auth.connecte()) return true;

  return router.createUrlTree(['/connexion'], {
    queryParams: { returnUrl: etat.url },
  });
};

/** Variante pour les routes « déjà connecté » (ex. /connexion). */
export const invitationGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.connecte() ? router.createUrlTree(['/']) : true;
};