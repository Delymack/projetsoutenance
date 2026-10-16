import { Injectable } from '@angular/core';

/**
 * Fabrique de confettis pour les micro-célébrations (ajout au panier, etc.).
 *
 * `canvas-confetti` est chargé en **import dynamique** (lazy) afin de ne pas
 * alourdir le bundle initial : la bibliothèque n'est téléchargée qu'au premier
 * effet. Les couleurs reprennent la palette de la marque (or, champagne, vin).
 */
@Injectable({ providedIn: 'root' })
export class ConfettiService {
  /** Palette Nuit & Or : or, or clair, vin, champagne, ivoire. */
  private readonly COULEURS = ['#d4af37', '#e8d5a0', '#8b1e3a', '#b13a55', '#f5f1e8'];

  /**
   * Explosion de confettis dorés, discrète, centrée sur la moitié basse de
   * l'écran (proche du bouton d'ajout). Sans effet si le module échoue.
   */
  ajoutPanier(): void {
    void import('canvas-confetti').then((module) => {
      module.default({
        particleCount: 60,
        spread: 70,
        startVelocity: 32,
        decay: 0.9,
        scalar: 0.9,
        ticks: 160,
        zIndex: 9999,
        colors: this.COULEURS,
        origin: { x: 0.5, y: 0.72 },
      });
    });
  }
}
