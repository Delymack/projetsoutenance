import { DOCUMENT } from '@angular/common';
import { computed, effect, inject, Injectable, signal } from '@angular/core';

/** Thèmes disponibles. */
export type Theme = 'clair' | 'sombre';

const CLE_STOCKAGE = 'lb.theme';

/**
 * Service de thème.
 *
 * Rôle :
 * - exposer le thème courant sous forme de `signal` (reactive, zoneless-friendly) ;
 * - l'appliquer sur `<html data-theme="...">` pour que les CSS variables prennent effet ;
 * - le persister dans localStorage et respecter la préférence système au 1er lancement.
 *
 * On utilise un `signal` plutôt qu'un BehaviorSubject : la valeur est un simple
 * état de présentation, et l_usage depuis les templates est plus directe.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly document = inject(DOCUMENT);

  /** Thème actuellement appliqué. */
  readonly theme = signal<Theme>(this.reprendreThemeInitial());

  /** Signal dérivé : true si le thème sombre est actif (pratique pour les icônes). */
  readonly estSombre = computed(() => this.theme() === 'sombre');

  /** L'utilisateur a-t-il choisi un thème manuellement ? */
  private readonly choixManuel = signal<boolean>(!!localStorage.getItem(CLE_STOCKAGE));

  constructor() {
    // Applique immédiatement le thème retenu : les `effect()` ne s'exécutent
    // qu'au prochain cycle de détection de changement, ce qui laisserait brièvement
    // la page sans le bon thème (flash) au démarrage.
    this.appliquer(this.theme());

    // Applique le thème au document à chaque changement.
    effect(() => this.appliquer(this.theme()));

    // En l'absence de choix explicite, on suit la préférence système.
    if (typeof matchMedia === 'function') {
      const requete = matchMedia('(prefers-color-scheme: dark)');
      const synchroniser = (e: MediaQueryListEvent) => {
        if (!this.choixManuel()) this.theme.set(e.matches ? 'sombre' : 'clair');
      };
      requete.addEventListener?.('change', synchroniser);
    }
  }

  /** Bascule clair ⇄ sombre. */
  basculer(): void {
    this.definir(this.theme() === 'clair' ? 'sombre' : 'clair');
  }

  /** Définit un thème et le mémorise. */
  definir(theme: Theme): void {
    this.theme.set(theme);
    this.choixManuel.set(true);
    this.ecrireCle(theme);
  }

  /** Restaure le thème système (supprime la préférence persistée). */
  suivreSysteme(): void {
    this.choixManuel.set(false);
    localStorage.removeItem(CLE_STOCKAGE);
    const clair = typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: light)').matches;
    this.theme.set(clair ? 'clair' : 'sombre');
  }

  /** Écrit l'attribut `data-theme` sur la racine du document. */
  private appliquer(theme: Theme): void {
    this.document.documentElement.setAttribute('data-theme', theme);
    // Le thème Angular Material est piloté par ce même attribut : le fichier
    // styles/_material.scss émet les variables `--mat-sys-*` dans
    // `[data-theme='sombre']`. Aucune classe supplémentaire n'est nécessaire.
    // Le meta theme-color suit également le thème (barre mobile / PWA).
    this.document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute('content', theme === 'sombre' ? '#0a0a0b' : '#f8f5ef');
  }

  private reprendreThemeInitial(): Theme {
    const stocke = localStorage.getItem(CLE_STOCKAGE);
    if (stocke === 'clair' || stocke === 'sombre') return stocke;
    // Identité « Nuit & Or » : le thème sombre est le choix par défaut.
    return 'sombre';
  }

  private ecrireCle(theme: Theme): void {
    localStorage.setItem(CLE_STOCKAGE, theme);
  }
}