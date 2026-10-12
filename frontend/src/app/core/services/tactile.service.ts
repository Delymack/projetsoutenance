import { Injectable, computed, signal } from '@angular/core';

/** Clé de la préférence « mode tactile forcé ». */
const CLE_TACTILE = 'lb.caisse.tactile';

/**
 * Service du mode tactile de la caisse.
 *
 * Détection automatique via `(pointer: coarse)` / `maxTouchPoints`, avec
 * bascule manuelle persistée qui reste prioritaire tant qu'elle n'est pas
 * remise à « automatique ». L'écoute du changement de media query est
 * enregistrée ici (et non dans le composant) pour éviter une fuite.
 */
@Injectable({ providedIn: 'root' })
export class TactileService {
  /** Choix manuel de l'utilisateur : `null` = détection automatique. */
  private readonly manuel = signal<boolean | null>(this.lirePreference());

  /** Valeur de la détection automatique, suivie via matchMedia. */
  readonly auto = signal<boolean>(this.detecter());

  /** Mode tactile effectif. */
  readonly actif = computed(() => this.manuel() ?? this.auto());

  constructor() {
    this.suivreAuto();
  }

  /** Bascule le mode tactile en forçant la valeur choisie. */
  basculer(): void {
    this.manuel.set(!this.actif());
    try {
      if (this.actif()) localStorage.setItem(CLE_TACTILE, '1');
      else localStorage.removeItem(CLE_TACTILE);
    } catch {
      console.warn('Préférence tactile non enregistrée (stockage indisponible).');
    }
  }

  /** Suit les changements de pointeur (branchement/débranchement d'un stylet). */
  private suivreAuto(): void {
    if (typeof matchMedia !== 'function') return;

    const requete = matchMedia('(pointer: coarse)');
    requete.addEventListener?.('change', () => this.auto.set(this.detecter()));
    this.auto.set(this.detecter());
  }

  private detecter(): boolean {
    if (typeof navigator === 'undefined') return false;
    return navigator.maxTouchPoints > 0 || window.matchMedia('(pointer: coarse)').matches;
  }

  private lirePreference(): boolean | null {
    try {
      return localStorage.getItem(CLE_TACTILE) === '1' ? true : null;
    } catch {
      return null;
    }
  }
}