/** Message échangé dans la conversation du chatbot. */
export interface MessageChat {
  /** Identifiant unique (clé de liste + animation d'arrivée). */
  id: string;
  /** Émetteur du message. */
  role: 'bot' | 'user';
  /** Texte affiché, déjà traduit. */
  texte: string;
  /** Instant d'envoi. */
  date: Date;
  /** Suggestions de relance affichées sous le message (facultatif). */
  suggestions: string[];
}

/** Règle de correspondance du moteur du chatbot. */
export interface RegleChatbot {
/**
   * Groupes de mots-clés. Un groupe est un ensemble de synonymes : si **au moins
   * un** mot du groupe est trouvé, la règle se déclenche. Plusieurs groupes
   * appliqués à un même mot-clé affinent la règle (« horaires » **et** « dimanche »).
   */
  groupes: string[][];
  /** Clé i18n de la réponse (`CHATBOT.reponses.*`). */
  reponse: string;
  /** Clés i18n des suggestions de relance proposées après la réponse. */
  suggestions?: string[];
}