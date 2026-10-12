import { ApplicationConfig, isDevMode, LOCALE_ID, provideZoneChangeDetection } from '@angular/core';
import { provideRouter, withComponentInputBinding, withInMemoryScrolling, withViewTransitions } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { provideServiceWorker } from '@angular/service-worker';
import { registerLocaleData } from '@angular/common';
import localeFr from '@angular/common/locales/fr';
import { TranslateLoader, provideTranslateService } from '@ngx-translate/core';

import { routes } from './app.routes';
import { authInterceptor } from './core/interceptors/auth.interceptor';
import { TraductionsCacheLoader } from './core/services/traductions';

/**
 * Locale française par défaut.
 *
 * Angular ne fournit que `en-US` : sans cet enregistrement, les pipes `number`,
 * `date` et `currency` lèvent NG0701 (`Missing locale data`) dès qu'on leur
 * demande `fr-FR`, ce qui interrompt le rendu des composants concernés.
 */
registerLocaleData(localeFr);

/**
 * Configuration racine de l'application (providers globaux).
 *
 * Points notables :
 *  - `withComponentInputBinding()` : permet de recevoir directement un paramètre
 *    de route via `input()` dans un composant (utile pour /vin/:id) ;
 * - `withViewTransitions` : transitions natives entre routes ;
 * - `provideTranslateService` + `provideTranslateHttpLoader` : i18n ;
 * - `provideServiceWorker` : PWA / mode hors ligne, uniquement en production.
 */
export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),

    // Formatage des nombres, dates et montants en français.
    { provide: LOCALE_ID, useValue: 'fr-FR' },

 // --- Routage ---
    provideRouter(
      routes,
      withComponentInputBinding(),
      withInMemoryScrolling({ scrollPositionRestoration: 'top', anchorScrolling: 'enabled' }),
      withViewTransitions({ skipInitialTransition: true }),
    ),

 // --- HTTP + intercepteur JWT ---
    provideHttpClient(withInterceptors([authInterceptor])),

 // --- Animations ---
    provideAnimationsAsync(),

 // --- i18n FR / MG / EN ---
    provideTranslateService({
      loader: { provide: TranslateLoader, useClass: TraductionsCacheLoader },
      // Traduit dès l'amorçage : sans `defaultLanguage`, le dictionnaire n'est
      // jamais chargé et les templates affichent les clés brutes (« ACCUEIL.titre »).
      defaultLanguage: 'fr',
      useDefaultLang: true,
    }),

 // --- PWA : service worker en production uniquement ---
    provideServiceWorker('ngsw-worker.js', {
      enabled: !isDevMode(),
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};