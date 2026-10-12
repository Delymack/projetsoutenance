/**
 * Modèles d'analyse — tableau de bord, rapports, heatmap, frise.
 *
 * Ces types décrivent des **agrégats déjà calculés côté frontend** : l'application
 * doit fonctionner sans backend, et le passage à l'API Django consistera à
 * remplacer le service `VentesService` par des appels REST renvoyant les mêmes
 * formes — la signature des composants, elle, ne changera pas.
 */

import { WineCategory } from './product.model';

/** Agrégation temporelle demandée par les rapports. */
export type PeriodeRapport = 'jour' | 'semaine' | 'mois' | 'annee';

/** Case de la heatmap des ventes : un jour de la semaine × une heure. */
export interface CaseVente {
  /** Jour de la semaine : 0 = lundi … 6 = dimanche (convention ISO française). */
  jour: number;
  /** Heure de la journée, 0 → 23. */
  heure: number;
  /** Nombre de bouteilles vendues sur cette case. */
  ventes: number;
  /** Chiffre d'affaires correspondant, en Ariary. */
  ca: number;
}

/** Point d'un graphique simple (`ngx-charts` attend `{ name, value }`). */
export interface SerieGraphique {
  /** Libellé de l'abscisse : jour, semaine, mois, vin ou catégorie. */
  name: string;
  /** Valeur : CA en Ariary, volume vendu ou pourcentage. */
  value: number;
}

/** Ligne d'efficacité d'une promotion. */
export interface LigneEfficacite {
  /** Identifiant de la campagne. */
  id: string;
  /** Libellé de la campagne. */
  libelle: string;
  /** Nombre de bouteilles écoulées pendant la campagne. */
  ventes: number;
  /** Chiffre d'affaires généré pendant la campagne. */
  ca: number;
  /** Part des ventes réalisées avec la campagne (en %). */
  volume: number;
}

/** Indicateurs clés d'une période, avec l'évolution par rapport à la précédente. */
export interface IndicateursPeriode {
  /** Chiffre d'affaires de la période, en Ariary. */
  ca: number;
  /** Nombre de tickets encaissés. */
  tickets: number;
  /** Nombre de bouteilles vendues. */
  bouteilles: number;
  /** Panier moyen, en Ariary (0 si aucun ticket). */
  panierMoyen: number;
  /** Évolution du CA en pourcentage par rapport à la période précédente. */
  evolutionCa: number;
  /** Évolution du volume en pourcentage. */
  evolutionVolume: number;
}

/** Vente affichée dans le flux « en direct » du tableau de bord. */
export interface VenteLive {
  /** Identifiant unique de la ligne (pour l'animation d'apparition). */
  id: string;
  /** Vin vendu. */
  vinId: string;
  /** Nom du vin (dénormalisé pour l'affichage). */
  nom: string;
  /** Image du vin. */
  image: string;
  /** Nombre de bouteilles. */
  quantite: number;
  /** Montant de la vente, en Ariary. */
  total: number;
  /** Instant de la vente. */
  date: Date;
}

/** Répartition des ventes par catégorie de vin. */
export interface VenteCategorie extends SerieGraphique {
  /** Catégorie technique, pour le lien vers le catalogue filtré. */
  categorie: WineCategory;
}