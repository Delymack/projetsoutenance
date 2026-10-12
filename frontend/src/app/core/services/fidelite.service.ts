import { Injectable, computed, inject, signal } from '@angular/core';

import { BadgeFidelite, PalierFidelite, RecompenseFidelite } from '../models/product.model';
import { PanierService } from './panier.service';

const CLE_POINTS = 'lb.fidelite.points';
const CLE_RECOMPENSES = 'lb.fidelite.recompenses';

/** Ariary nécessaires pour un point de fidélité (arrondi inférieur). */
export const ARIARY_PAR_POINT = 1000;

/** Solde attribué à la première visite : la démo n'a pas d'historique de commandes. */
const SOLDE_INITIAL_DEMO = 1240;

/** Paliers du programme, du moins au plus exigeant. */
const PALIERS: PalierFidelite[] = [
  { cle: 'Bronze', seuil: 0, icone: 'bronze' },
  { cle: 'Argent', seuil: 500, icone: 'workspace_premium' },
  { cle: 'Or', seuil: 1500, icone: 'emoji_events' },
  { cle: 'Platine', seuil: 3000, icone: 'diamond' },
];

/** Badges cumulés. */
const BADGES: BadgeFidelite[] = [
  { id: 'b-premiere', seuil: 50, icone: 'shopping_bag', cle: 'premiereBouteille' },
  { id: 'b-dix', seuil: 500, icone: 'local_bar', cle: 'dixBouteilles' },
  { id: 'b-cent', seuil: 1500, icone: 'wine_bar', cle: 'centBouteilles' },
  { id: 'b-amateur', seuil: 2500, icone: 'auto_awesome', cle: 'amateur' },
  { id: 'b-ambassadeur', seuil: 4000, icone: 'public', cle: 'ambassadeur' },
];

/** Récompenses échangeables. */
const RECOMPENSES: RecompenseFidelite[] = [
  { id: 'r-verre', cout: 400, icone: 'wine_bar', cle: 'verreGraffe' },
  { id: 'r-decanter', cout: 900, icone: 'hourglass_bottom', cle: 'decanter' },
  { id: 'r-seance', cout: 1500, icone: 'groups', cle: 'seanceDegustation' },
  { id: 'r-bouteille', cout: 2200, icone: 'card_giftcard', cle: 'bouteilleOfferte' },
  { id: 'r-formation', cout: 3000, icone: 'school', cle: 'formation' },
];

/**
 * Programme de fidélité.
 *
 * Les points acquis sont mémorisés dans le navigateur ; ceux du panier en
 * cours sont *estimés* (un point pour 1 000 Ar) et présentés comme « en attente
 * de validation », car en production ils ne sont crédités qu'après paiement.
 * Les récompenses utilisées sont également persistées pour ne pas être
 * offered deux fois.
 */
@Injectable({ providedIn: 'root' })
export class FideliteService {
  private readonly panier = inject(PanierService);

  readonly paliers = PALIERS;
  readonly badges = BADGES;
  readonly recompenses = RECOMPENSES;

  /** Points déjà validés sur des commandes passées. */
  readonly pointsAcquis = signal<number>(this.lirePoints());

  /** Identifiants des récompenses déjà activées. */
  readonly recompensesUtilisees = signal<string[]>(this.lireRecompenses());

  /** Points estimés sur le panier en cours (validés après paiement). */
  readonly pointsEnAttente = computed(() => Math.floor(this.panier.total() / ARIARY_PAR_POINT));

  /** Solde total : validé + estimé. */
  readonly points = computed(() => this.pointsAcquis() + this.pointsEnAttente());

  /** Palier atteint. */
  readonly niveau = computed<PalierFidelite>(
    () =>
      [...PALIERS].reverse().find((palier) => this.points() >= palier.seuil) ?? PALIERS[0],
  );

  /** Prochain palier, ou null si le client est au sommet. */
  readonly niveauSuivant = computed<PalierFidelite | null>(
    () => PALIERS.find((palier) => palier.seuil > this.points()) ?? null,
  );

  /** Points manquants pour le prochain palier. */
  readonly pointsRestants = computed(() => {
    const suivant = this.niveauSuivant();
    return suivant ? Math.max(suivant.seuil - this.points(), 0) : 0;
  });

  /** Avancement vers le prochain palier, en pourcentage. */
  readonly progression = computed(() => {
    const suivant = this.niveauSuivant();
    if (!suivant) return 100;

    const precedent = this.niveau().seuil;
    const intervalle = suivant.seuil - precedent;
    return intervalle === 0 ? 100 : ((this.points() - precedent) / intervalle) * 100;
  });

  /** Badges débloqués. */
  readonly badgesDebloques = computed(() => this.badges.filter((badge) => this.points() >= badge.seuil));

  /** Badges encore hors de portée. */
  readonly badgesRestants = computed(() => this.badges.filter((badge) => this.points() < badge.seuil));

  /** Récompenses accessibles avec le solde actuel. */
  readonly recompensesDisponibles = computed(() =>
    this.recompenses.filter((recompense) => !this.recompensesUtilisees().includes(recompense.id)),
  );

  /** La récompense peut-elle être activée ? */
  estDisponible(recompense: RecompenseFidelite): boolean {
    return (
      this.points() >= recompense.cout && !this.recompensesUtilisees().includes(recompense.id)
    );
  }

  /**
   * Active une récompense : débite les points acquis et mémorise l'échange.
   * Renvoie false si le solde est insuffisant ou si la récompense a déjà été
   * activée.
   */
  utiliser(recompense: RecompenseFidelite): boolean {
    if (!this.estDisponible(recompense)) return false;

    // Les points estimés (panier) ne sont pas débitables : on puise dans le
    // solde validé, et le solde ne descend jamais sous zéro.
    const reste = Math.max(this.pointsAcquis() - recompense.cout, 0);
    this.pointsAcquis.set(reste);
    this.ecrirePoints(reste);
    this.recompensesUtilisees.update((liste) => [...liste, recompense.id]);
    this.ecrireRecompenses(this.recompensesUtilisees());
    return true;
  }

  private lirePoints(): number {
    try {
      const stocke = localStorage.getItem(CLE_POINTS);
      const valeur = stocke === null ? SOLDE_INITIAL_DEMO : Number.parseInt(stocke, 10);
      return Number.isFinite(valeur) && valeur >= 0 ? valeur : SOLDE_INITIAL_DEMO;
    } catch {
      return SOLDE_INITIAL_DEMO;
    }
  }

  private ecrirePoints(points: number): void {
    try {
      localStorage.setItem(CLE_POINTS, String(points));
    } catch {
      console.warn('Solde de fidélité non enregistré (stockage indisponible).');
    }
  }

  private lireRecompenses(): string[] {
    try {
      const stocke = localStorage.getItem(CLE_RECOMPENSES);
      const liste = stocke ? (JSON.parse(stocke) as string[]) : [];
      return Array.isArray(liste) ? liste : [];
    } catch {
      return [];
    }
  }

  private ecrireRecompenses(liste: string[]): void {
    try {
      localStorage.setItem(CLE_RECOMPENSES, JSON.stringify(liste));
    } catch {
      console.warn('Récompenses utilisées non enregistrées (stockage indisponible).');
    }
  }
}