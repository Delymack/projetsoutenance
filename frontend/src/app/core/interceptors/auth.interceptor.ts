import {
  HttpErrorResponse,
  HttpHandlerFn,
  HttpInterceptorFn,
  HttpRequest,
} from '@angular/common/http';
import { inject, Injector } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { TranslateService } from '@ngx-translate/core';
import { catchError, from, switchMap, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

/**
 * Intercepteur HTTP.
 *
 * Responsabilités :
 *  1. injecter le JWT dans l'en-tête `Authorization` ;
 *  2. gérer 401 / 403 / 404 / 500 / erreur réseau via un toast (MatSnackBar) ;
 *  3. sur 401, purger la session et rediriger vers /connexion.
 *
 * Point d'attention : on récupère MatSnackBar et TranslateService via
 * `inject(Injector).get(...)` car les intercepteurs fonctionnels s'exécutent
 * avant l'amorçage des providers applicatifs : un `inject()` direct
 * provoquerait une erreur de dépendance cyclique.
 */
export const authInterceptor: HttpInterceptorFn = (req, suivant) => {
  const auth = inject(AuthService);
  const injector = inject(Injector);

  // 1. Ajout du JWT, sauf sur les appels d'authentification (signup, login, resend) et les assets.
  let requete: HttpRequest<unknown> = req;
  const token = auth.token;
  if (token && !req.url.includes('/auth/') && !req.url.startsWith('/assets/')) {
    requete = req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
  }

  // Résolution différée : uniquement si une erreur survient.
  const notifier = (message: string, panelClass: string, duree = 5000): void => {
    const snack = injector.get(MatSnackBar);
    const translate = injector.get(TranslateService);
    snack.open(translate.instant(message), 'OK', { duration: duree, panelClass: [panelClass] });
  };

  const signaler = (erreur: HttpErrorResponse): void => {
    switch (erreur.status) {
      case 0:
        // Status 0 = requête jamais arrivée au serveur (réseau coupé, DNS, CORS).
        notifier('ERREURS.reseau', 'snack-danger', 5000);
        break;
      case 403:
        notifier('ERREURS.403', 'snack-warning', 5000);
        break;
      case 404:
        notifier('ERREURS.404', 'snack-warning', 4000);
        break;
      case 500:
        notifier('ERREURS.500', 'snack-danger', 6000);
        break;
      default:
        if (erreur.status >= 400) notifier('COMMUN.erreur', 'snack-warning', 5000);
    }
  };

  return suivant(requete).pipe(
    catchError((erreur: HttpErrorResponse) => {
      // Échec d'authentification sur /auth/* (login, inscription, code OTP) :
      // la page affiche elle-même le message, on ne touche pas à la session.
      if (erreur.status === 401 && req.url.includes('/auth/')) {
        return throwError(() => erreur);
      }

      // 401 sur une ressource protégée (JWT expiré) : on renouvelle le token
      // puis on rejoue la requête une seule fois. La session n'est rompue
      // (déconnexion) que si le rafraîchissement échoue — le client reste donc
      // connecté tant qu'il ne se déconnecte pas explicitement.
      if (erreur.status === 401 && token) {
        return from(auth.renouvelerToken()).pipe(
          switchMap((nouveau) => {
            if (nouveau) {
              const rejeu = req.clone({ setHeaders: { Authorization: `Bearer ${nouveau}` } });
              return suivant(rejeu).pipe(
                catchError((erreurRejeu: HttpErrorResponse) => {
                  signaler(erreurRejeu);
                  return throwError(() => erreurRejeu);
                }),
              );
            }
            notifier('ERREURS.401', 'snack-danger', 5000);
            auth.deconnexion('/connexion');
            return throwError(() => erreur);
          }),
        );
      }

      signaler(erreur);
      return throwError(() => erreur);
    }),
  );
};