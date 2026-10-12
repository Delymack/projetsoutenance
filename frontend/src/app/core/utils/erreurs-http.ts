// frontend/src/app/core/utils/erreurs-http.ts
import { HttpErrorResponse } from '@angular/common/http';

/**
 * Extrait un message affichable depuis une erreur HTTP Django/DRF.
 *
 * L'intercepteur rejette les `HttpErrorResponse` (qui ne sont pas des `Error`) :
 * sans ce helper, les pages affichent leur message générique et masquent la
 * cause réelle renvoyée par le backend (`{champ: ["..."]}`, `{error: "..."}`,
 * `{detail: "..."}`…).
 *
 * @param erreur valeur attrapée dans un `catch`
 * @param fallback message à afficher si aucune raison exploitable
 */
export function messageErreurHttp(erreur: unknown, fallback: string): string {
  if (erreur instanceof HttpErrorResponse) {
    const corps: unknown = erreur.error;

    if (typeof corps === 'string' && corps.trim()) {
      return corps.trim();
    }
    if (corps && typeof corps === 'object') {
      const objet = corps as Record<string, unknown>;
      for (const cle of ['error', 'detail', 'message']) {
        const valeur = objet[cle];
        if (typeof valeur === 'string' && valeur.trim()) {
          return valeur.trim();
        }
      }
      for (const valeur of Object.values(objet)) {
        if (Array.isArray(valeur)) {
          const premier = valeur.find((item): item is string => typeof item === 'string');
          if (premier?.trim()) return premier.trim();
        } else if (typeof valeur === 'string' && valeur.trim()) {
          return valeur.trim();
        }
      }
    }
    if (erreur.status === 0) {
      return 'Serveur injoignable. Vérifiez que l\'API Django est lancée sur le port 8000.';
    }
    if (erreur.status >= 500) {
      return `Erreur serveur (${erreur.status}). Consultez la console du backend pour le détail.`;
    }
    return fallback;
  }
  if (erreur instanceof Error && erreur.message.trim()) {
    return erreur.message;
  }
  return fallback;
}
