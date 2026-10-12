import { HttpClient } from '@angular/common/http';
import { TranslateHttpLoader } from '@ngx-translate/http-loader';
import { TranslateLoader } from '@ngx-translate/core';
import { inject } from '@angular/core';
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

/**
 * Chargeur de traduction avec cache mémoire.
 *
 * `TranslateHttpLoader` refait une requête HTTP à chaque changement de langue.
 * On mémorise donc la réponse pour éviter les allers-retours inutiles vers
 * `/assets/i18n/<langue>.json`.
 */
export class TraductionsCacheLoader implements TranslateLoader {
  private readonly http = inject(HttpClient);
  private readonly cache = new Map<string, Observable<Record<string, unknown>>>();

  getTranslation(lang: string): Observable<Record<string, unknown>> {
    const enCache = this.cache.get(lang);
    if (enCache) return enCache;

    const requete = new TranslateHttpLoader(this.http, '/assets/i18n/', '.json')
      .getTranslation(lang)
      // Si le dictionnaire est absent, on ne casse pas l'affichage : les clés
      // restent affichées et le reste de l'application continue de fonctionner.
      .pipe(catchError(() => of({})));

    this.cache.set(lang, requete);
    return requete;
  }
}
