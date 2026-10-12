/**
 * Modèles de cartographie et de visualisation.
 */

/** Caves, domaines et partenaires vinicoles de Madagascar. */
export interface Cave {
  id: string;
  nom: string;
  /** Type de point de vente. */
  type: 'cave' | 'domaine' | 'partenaire' | 'magasin';
  /** Ville où se trouve la cave. */
  ville: string;
  region: string;
  latitude: number;
  longitude: number;
  /** Adresse / repère. */
  adresse: string;
  telephone: string;
  /** Horaires d'ouverture, texte libre (« Lun–Sam 8h–18h »). */
  horaires: string;
  description: string;
  /** Ids des vins proposés à la cave (référence au catalogue). */
  vinsIds: string[];
}

/** Case d'une heatmap de ventes (jour de la semaine × heure). */
export interface CaseHeatmap {
  /** 0 = dimanche … 6 = samedi. */
  jour: number;
  /** 0 → 23. */
  heure: number;
  /** Nombre de bouteilles vendues. */
  quantite: number;
  /** Chiffre d'affaires en Ariary. */
  chiffreAffaires: number;
  /** Nombre de tickets. */
  tickets: number;
}

/** Position d'une case dans la grille. */
export interface PositionHeatmap {
  jour: number;
  heure: number;
  /** 0 → 1, pour l'opacité de la couleur. */
  intensite: number;
  /** 0 → 1, pour la teinte. */
  chaleur: number;
  case_: CaseHeatmap;
}

/** Bloc de la frise chronologique des promotions. */
export interface BlocPromo {
  promotionId: string;
  libelle: string;
  remisePct: number | null;
  dateDebut: string;
  dateFin: string;
  /** Nombre de vins concernés. */
  nbVins: number;
  /** Code couleur : indice de la palette du thème (0-5). */
  couleur: number;
  /** Intensité d'une promotion en cours (0 → 1). */
  progression: number;
  /** Vrai si la promotion est active à l'instant présent. */
  active: boolean;
}
