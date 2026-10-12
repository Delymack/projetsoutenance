/** Nature d'une alerte : détermine l'icône et la couleur du panneau. */
export type CategorieNotification = 'promo' | 'stock' | 'commande';

/** Autorisation de l'API Notification du navigateur. */
export type AutorisationNotification = 'granted' | 'denied' | 'default' | 'inconnu';

/** Notification applicative (persistée, donc lisible même hors connexion). */
export interface Alerte {
  /** Identifiant unique, sert de clé de liste et de dédoublonnage. */
  id: string;
  /** Catégorie de l'alerte. */
  categorie: CategorieNotification;
  /** Titre court affiché en gras. */
  titre: string;
  /** Corps du message. */
  message: string;
  /** Date de déclenchement (ISO). */
  date: string;
  /** L'alerte a-t-elle été lue ? */
  lue: boolean;
  /** Route interne vers laquelle ledit « Voir » navigue (`null` sinon). */
  lien: string | null;
}