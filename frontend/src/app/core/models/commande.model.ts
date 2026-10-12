/**
 * Modèle de commande — Lazan'i Betsileo
 *
 * L'historique est construit à partir des ventes enregistrées par la caisse et
 * synchronisées par `SyncService`. En mode mock, un jeu de commandes de
 * démonstration est injecté au premier lancement (cf. `CommandesService`).
 */

/** Statut d'une commande, du plus ancien au plus récent. */
export type StatutCommande = 'livree' | 'enPreparation' | 'annulee';

/** Ligne d'une commande : le vin est résolu à la lecture via le catalogue. */
export interface LigneCommande {
  /** Identifiant du vin commandé. */
  vinId: string;
  /** Quantité de bouteilles. */
  quantite: number;
  /** Prix unitaire figé au moment de la commande. */
  prixUnitaire: number;
  /** Remise appliquée sur la ligne (%). */
  remisePct: number;
}

/** Commande du client. */
export interface Commande {
  /** Référence courte affichée à l'utilisateur (ex. `CMD-4821`). */
  reference: string;
  /** Date de la commande (ISO). */
  date: string;
  /** Lignes commandées. */
  lignes: LigneCommande[];
  /** Frais de livraison facturés. */
  fraisLivraison: number;
  /** Statut d'avancement. */
  statut: StatutCommande;
  /** Étape de validation réservée aux commandes passées depuis le site. */
  validationStatut?: 'A_VALIDER' | 'VALIDEE' | 'REFUSEE';
  /** Motif communiqué par l'équipe lorsqu'une commande est refusée. */
  motifRefus?: string;
  /** Lien public signé vers la facture, présent dès que la commande est validée. */
  factureUrl?: string;
  /** Points de fidélité générés par la commande. */
  points: number;
  /** Total calculé par le backend pour les ventes API. */
  totalBackend?: number;
}