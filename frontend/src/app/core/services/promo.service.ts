import { Injectable, computed, signal } from '@angular/core';

import { LotPromo, TypeJeuPromo } from '../models/product.model';

const CLE_STOCKAGE = 'lb.promo.jeux';

/** Ce que l'utilisateur a gagné aujourd'hui, par jeu. */
interface JeuxDuJour {
  /** Date locale au format AAAA-MM-JJ : le tirage est remis à zéro chaque jour. */
  date: string;
  lots: Partial<Record<TypeJeuPromo, LotPromo>>;
}

/**
 * Lots de la roue de la fortune.
 *
 * `poids` est la probabilité relative : la somme des poids vaut 100, ce qui lit
 * « 5 % de chances de gagner une bouteille ». Les lots sont lus dans l'ordre
 * d'affichage sur la roue, le premier segment partant en haut.
 */
const LOTS_ROUE: { poids: number; lot: LotPromo }[] = [
  {
    poids: 63,
    lot: { id: 'r-perdu', nature: 'perdu', remisePct: 0, vinOffertId: null },
  },
  {
    poids: 30,
    lot: { id: 'r-remise15', nature: 'remise', remisePct: 15, vinOffertId: null },
  },
  {
    poids: 7,
    lot: { id: 'r-vin', nature: 'vinOffert', remisePct: 0, vinOffertId: 'v-012' },
  },
];

/** Lots de la carte à gratter. */
const LOTS_CARTE: { poids: number; lot: LotPromo }[] = [
  {
    poids: 50,
    lot: { id: 'c-perdu', nature: 'perdu', remisePct: 0, vinOffertId: null },
  },
  {
    poids: 42,
    lot: { id: 'c-remise5', nature: 'remise', remisePct: 5, vinOffertId: null },
  },
  {
    poids: 8,
    lot: { id: 'c-vin', nature: 'vinOffert', remisePct: 0, vinOffertId: 'v-002' },
  },
];

/**
 * Jeux promotionnels du bloc 2.
 *
 * Règle métier : un tirage par jeu et par jour, mémorisé dans le navigateur.
 * Le lot déjà gagné est renvoyé tel quel au rechargement de la page : on ne
 * triche pas en rechargeant, ce qui laisse la démo reproductible.
 */
@Injectable({ providedIn: 'root' })
export class PromoService {
  /** Lots affichés sur la roue, dans l'ordre des segments. */
  readonly segmentsRoue: LotPromo[] = LOTS_ROUE.map((entree) => entree.lot);

  private readonly etat = signal<JeuxDuJour>(this.reprendre());

  /** Lots déjà gagnés aujourd'hui. */
  readonly lotsDuJour = computed(() => this.etat().lots);

  /** Le jeu a-t-il déjà été joué aujourd'hui ? */
  aJoue(type: TypeJeuPromo): boolean {
    return !!this.lotsDuJour()[type];
  }

  /** Lot gagné aujourd'hui pour ce jeu, s'il existe. */
  lot(type: TypeJeuPromo): LotPromo | null {
    return this.lotsDuJour()[type] ?? null;
  }

  /**
   * Tirage pondéré. Renvoie le lot déjà gagné si le jeu a été joué, sinon
   * tire un lot, le mémorise et le renvoie.
   */
  jouer(type: TypeJeuPromo): LotPromo {
    const dejaGagne = this.lot(type);
    if (dejaGagne) return dejaGagne;

    const table = type === 'roue' ? LOTS_ROUE : LOTS_CARTE;
    const tire = Math.random() * table.reduce((total, entree) => total + entree.poids, 0);
    let cumule = 0;
    let gagnant = table[table.length - 1].lot;

    for (const entree of table) {
      cumule += entree.poids;
      if (tire <= cumule) {
        gagnant = entree.lot;
        break;
      }
    }

    this.enregistrer(type, gagnant);
    return gagnant;
  }

  /** Vide les gains du jour (utile pour rejouer une démonstration). */
  reinitialiser(): void {
    this.ecrire({ date: this.aujourdhui(), lots: {} });
  }

  private enregistrer(type: TypeJeuPromo, lot: LotPromo): void {
    this.ecrire({ date: this.aujourdhui(), lots: { ...this.etat().lots, [type]: lot } });
  }

  private ecrire(etat: JeuxDuJour): void {
    this.etat.set(etat);
    try {
      localStorage.setItem(CLE_STOCKAGE, JSON.stringify(etat));
    } catch {
      console.warn('Jeux promotionnels non enregistrés (stockage indisponible).');
    }
  }

  private reprendre(): JeuxDuJour {
    const vierge: JeuxDuJour = { date: this.aujourdhui(), lots: {} };

    try {
      const brut = localStorage.getItem(CLE_STOCKAGE);
      if (!brut) return vierge;
      const parsed: unknown = JSON.parse(brut);
      if (typeof parsed !== 'object' || parsed === null) return vierge;
      const ancien = parsed as {
        date?: unknown;
        lots?: Record<string, { nature?: unknown } | null>;
      };
      if (ancien.date !== this.aujourdhui() || !ancien.lots || typeof ancien.lots !== 'object') {
        return vierge;
      }
      return ancien as JeuxDuJour;
    } catch {
      return vierge;
    }
  }

  /** Date locale du jour (le fuseau de l'utilisateur, pas UTC). */
  private aujourdhui(): string {
    const maintenant = new Date();
    const mois = String(maintenant.getMonth() + 1).padStart(2, '0');
    const jour = String(maintenant.getDate()).padStart(2, '0');
    return `${maintenant.getFullYear()}-${mois}-${jour}`;
  }
}