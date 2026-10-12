import { DOCUMENT, isPlatformBrowser } from '@angular/common';
import { inject, Injectable, PLATFORM_ID, signal } from '@angular/core';
import { TranslateService } from '@ngx-translate/core';

/** Langues supportées par l'application. */
export type Langue = 'fr' | 'mg' | 'en';

export interface LangueOption {
  code: Langue;
  /** Libellé affiché dans la langue elle-même. */
  libelle: string;
  /** Emoji utilisé comme indicateur, sans ressource externe. */
  drapeau: string;
}

const CLE_STOCKAGE = 'lb.langue';
export const LANGUE_DEFAUT: Langue = 'fr';

/**
 * Coordonne la langue affichée, ngx-translate, l'attribut lang du document
 * et la préférence enregistrée dans le navigateur.
 */
@Injectable({ providedIn: 'root' })
export class LangueService {
  private readonly translate = inject(TranslateService);
  private readonly platformId = inject(PLATFORM_ID);
  private readonly document = inject(DOCUMENT);

  /** Options du sélecteur de langue. */
  readonly langues: LangueOption[] = [
    { code: 'fr', libelle: 'Français', drapeau: '🇫🇷' },
    { code: 'mg', libelle: 'Malagasy', drapeau: '🇲🇬' },
    { code: 'en', libelle: 'English', drapeau: '🇬🇧' },
  ];

  /** La langue sélectionnée ou mémorisée, avec le français comme défaut. */
  readonly langue = signal<Langue>(this.langueInitiale());

  constructor() {
    this.translate.addLangs(this.langues.map((langue) => langue.code));
    this.translate.setDefaultLang(LANGUE_DEFAUT);
    this.appliquer(this.langue());
  }

  /** Change la langue active et mémorise le choix dans le navigateur. */
  changer(code: Langue): void {
    if (!this.langues.some((langue) => langue.code === code)) {
      throw new Error(`Langue non prise en charge : ${code}`);
    }

    if (isPlatformBrowser(this.platformId)) {
      this.document.defaultView?.localStorage.setItem(CLE_STOCKAGE, code);
    }

    this.appliquer(code);
  }

  /** Raccourci de traduction pour les templates et le code TypeScript. */
  t(cle: string, params?: Record<string, unknown>): string {
    return this.translate.instant(cle, params);
  }

  private appliquer(code: Langue): void {
    this.langue.set(code);
    this.translate.use(code);
    this.document.documentElement?.setAttribute('lang', code);
  }

  private langueInitiale(): Langue {
    if (!isPlatformBrowser(this.platformId)) {
      return LANGUE_DEFAUT;
    }

    const stockee = this.document.defaultView?.localStorage.getItem(CLE_STOCKAGE);
    return stockee === 'fr' || stockee === 'mg' || stockee === 'en'
      ? stockee
      : LANGUE_DEFAUT;
  }
}
