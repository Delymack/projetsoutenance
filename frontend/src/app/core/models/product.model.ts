/**
 * Modèles de domaine — Lazan'i Betsileo
 * Application de gestion de vente et promotion du vin.
 */

/** Catégorie de vin (utilisée par le sommelier, les accords et les filtres). */
export type WineCategory =
  | 'rouge'
  | 'blanc'
  | 'rose'
  | 'mousseux'
  | 'petit-lait' // Vin de table traditionnel malgache
  | 'liqueur';

/** Intensité d'un caractéristique gustatif, de 0 à 1. */
export type Intensite = number;

/** Profil sensoriel d'un vin — base du sommelier virtuel et du quiz. */
export interface WineProfile {
  /** Fruité (0 = sec, 1 = très fruité). */
  fruite: Intensite;
  /** Tannique (structure taninique). */
  tanin: Intensite;
  /** Sucrosité (sec -> sucré). */
  sucre: Intensite;
  /** Acidité (fraîche -> vive). */
  acide: Intensite;
  /** Boisé (élevage en fût). */
  bois: Intensite;
}

/** Millésime : année de récolte. */
export type Millesime = number;

/** Vin du catalogue. */
export interface Vin {
  id: string;
  /** Code-barres EAN-13 imprimé sur l'étiquette — clé utilisée par le scanner. */
  codeBarres: string;
  /** Nom commercial, ex. « Gris de Betsileo ». */
  nom: string;
  /** Nom de la cuvée / château. */
  cuvee: string;
  categorie: WineCategory;
  /** Millésime (année). */
  millesime: Millesime;
  /** Cépage principal, ex. « Syrah ». */
  cepage: string;
  /** Prix unitaire en Ariary (Madagascar). */
  prix: number;
  /** Prix barré (avant promotion), sinon null. */
  prixBarre?: number | null;
  /** Stock disponible en bouteilles. */
  stock: number;
  /** Volume en cl. */
  volume: number;
  /** Degré d'alcool. */
  alcool: number;
  /** Description commerciale. */
  description: string;
  /** Notes de dégustation. */
  notesDegustation: string[];
  /** Profil sensoriel. */
  profil: WineProfile;
  /** Plats avec lesquels le vin s'accorde. */
  accords: string[];
  /** URL de l'image (mockée dans assets/images). */
  image: string;
  /** Moyenne des avis clients (0 à 5). */
  noteMoyenne: number;
  /** Nombre d'avis. */
  nombreAvis: number;
  /** Vendeur / domaine producteur. */
  producteur: string;
}

/** Élément du panier. */
export interface PanierLigne {
  vin: Vin;
  /** Quantité. */
  quantite: number;
  /** Prix unitaire figé au moment de l'ajout. */
  prixUnitaire: number;
  /** Remise appliquée en pourcentage sur la ligne. */
  remisePct: number;
}

/** Rôles applicatifs. */
export type UserRole = 'admin' | 'gestionnaire' | 'vendeur' | 'client';

/** Utilisateur connecté (données décodées du JWT). */
export interface Utilisateur {
  id: string;
  nom: string;
  email: string;
  role: UserRole;
  /** JWT brut, stocké dans localStorage. */
  token?: string;
 /** profil client. */
  telephone?: string;
  ville?: string;
  /** Photo du compte, renvoyée par l'API (vide si aucune). */
  avatarUrl?: string;
  /** Initiales affichées dans la navbar et le profil. */
  initiales?: string;
}

/** formulaire d'inscription. */
export interface InscriptionDonnees {
  nom: string;
  email: string;
  motDePasse: string;
  telephone?: string;
  ville?: string;
}

/** adresse de livraison du client. */
export interface AdresseClient {
  libelle: string;
  destinataire: string;
  telephone: string;
  ligne: string;
  ville: string;
  notes?: string;
  parDefaut?: boolean;
}

/** Promotion. */
export interface Promotion {
  id: string;
  libelle: string;
  /** Pourcentage de remise (0 à 100), ou null si lot / cadeau. */
  remisePct: number | null;
  dateDebut: string; // ISO
  dateFin: string; // ISO
  /** Vins concernés (ids). */
  vinsIds: string[];
  actif: boolean;
}

/**avis client. */
export interface Avis {
  id: string;
  vinId: string;
  auteur: string;
  /** Note de 1 à 5. */
  note: number;
  commentaire: string;
  date: string; // ISO
  /** Nombre de « j'aime ». */
  likes: number;
}

/** Jeu promotionnel accessible depuis /promotions. */
export type TypeJeuPromo = 'roue' | 'carte';

/** Nature du lot gagné — détermine le message affiché. */
export type NatureLot = 'perdu' | 'remise' | 'vinOffert';

/** Lot d'un jeu promotionnel (roue de la fortune, carte à gratter). */
export interface LotPromo {
  id: string;
  /** Nature du gain. */
  nature: NatureLot;
  /** Remise en pourcentage (0 si le lot n'est pas une remise). */
  remisePct: number;
  /** Vin offert (null si le lot n'est pas une bouteille). */
  vinOffertId: string | null;
}

/** Profils proposés par le quiz gustatif. */
export type CleProfilGustatif = 'equilibre' | 'fruite' | 'tanin' | 'doux' | 'vif' | 'boise';

/** Réponse du quiz gustatif. */
export interface ProfilGustatif {
  fruite: number;
  tanin: number;
  sucre: number;
  acide: number;
  bois: number;
  /**
   * Clé i18n du profil gustatif : permet de retraduire l'affichage
   * (conservée telle quelle, le profil reste porté par le modèle vin).
   */
  cleProfil: CleProfilGustatif;
  /** Label lisible du profil. */
  label: string;
  dateCalcul: string;
}