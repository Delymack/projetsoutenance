export type ModePaiementApi =
  | 'ESPECES'
  | 'MVOLA'
  | 'ORANGE_MONEY'
  | 'AIRTEL_MONEY'
  | 'MOBILE_MONEY'
  | 'CARTE'
  | 'CHEQUE'
  | 'CREDIT';

export interface VenteApi {
  id: number;
  reference: string;
  date_vente: string;
  total: string | number;
  statut: 'PAYEE' | 'ANNULEE' | string;
  montant_retourne?: string | number;
  lignes: {
    id: number;
    produit: { id: number; nom: string } | number;
    quantite: number;
    prix_unitaire: string | number;
    remise: string | number;
    sous_total: string | number;
  }[];
}

export interface VenteApiList {
  count?: number;
  next?: string | null;
  results: VenteApi[];
}

export interface VenteApiEnvelope {
  success: boolean;
  message?: string;
  data: VenteApi;
}
