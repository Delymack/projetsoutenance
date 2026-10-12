import { Injectable, signal } from '@angular/core';

/** Clé de la préférence « son de validation ». */
const CLE_SON = 'lb.caisse.son';

/** Variantes de bip shorthand. */
export type VarianteSon = 'scan' | 'ajout' | 'succes' | 'erreur';

/**
 * Service de signal sonore de la caisse.
 *
 * Le son est produit via l'API Web Audio (aucun fichier à charger) : trois
 * tons distincts pour scan / ajout / succès, un ton grave pour l'erreur.
 * La préférence est persistée dans localStorage, avec repli silencieux si le
 * stockage est indisponible (mode privé strict).
 */
@Injectable({ providedIn: 'root' })
export class SonService {
  /** Le bip de validation est-il activé ? */
  readonly actif = signal(this.lirePreference());

  /** Bascule la préférence et la persiste. */
  basculer(): void {
    this.actif.set(!this.actif());
    try {
      localStorage.setItem(CLE_SON, this.actif() ? '1' : '0');
    } catch {
      console.warn('Préférence de son non enregistrée (stockage indisponible).');
    }
  }

  /** Joue un bip court ; no-op si le son est coupé ou Web Audio absent. */
  jouer(variante: VarianteSon): void {
    if (!this.actif() || typeof AudioContext === 'undefined') return;

    const frequences: Record<VarianteSon, number[]> = {
      scan: [880],
      ajout: [660],
      succes: [660, 880, 1180],
      erreur: [220, 180],
    };

    try {
      const contexte = new AudioContext();
      frequences[variante].forEach((frequence, index) => {
        const oscillateur = contexte.createOscillator();
        const gain = contexte.createGain();
        const debut = contexte.currentTime + index * 0.11;

        oscillateur.frequency.value = frequence;
        oscillateur.type = 'sine';
        // Enveloppe : montée courte, extinction rapide — un « bip » sec.
        gain.gain.setValueAtTime(0.0001, debut);
        gain.gain.exponentialRampToValueAtTime(0.16, debut + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, debut + 0.12);

        oscillateur.connect(gain).connect(contexte.destination);
        oscillateur.start(debut);
        oscillateur.stop(debut + 0.14);
      });

      // Le contexte est suspendu par défaut dans certains navigateurs.
      void contexte.resume();
      window.setTimeout(() => void contexte.close(), 800);
    } catch (erreur) {
      console.warn('Son de validation indisponible.', erreur);
    }
  }

  private lirePreference(): boolean {
    try {
      return localStorage.getItem(CLE_SON) !== '0';
    } catch {
      return true;
    }
  }
}