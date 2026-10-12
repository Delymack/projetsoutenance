import { Injectable, Signal, computed, signal } from '@angular/core';

/** clés */
const CLE_MESSAGES = 'lb.messages';

/** délai */
const DELAI_REPONSE_MS = 1200;

/** conseiller */
const CONSEILLER: { nom: string; fonction: string; enLigne: boolean } = {
  nom: 'Hanitra R.',
  fonction: 'Conseillère vin',
  enLigne: true,
};

/** message */
export interface MessageConversation {
  id: string;
 /** auteur */
  auteur: 'client' | 'conseiller';
 /** texte */
  texte: string;
 /** cle i18n */
  estCle: boolean;
 /** horodatage */
  horodatage: string;
 /** lu */
  lu: boolean;
}

/** routage */
const REGLES: readonly { mots: readonly string[]; cle: string }[] = [
  { mots: ['commande', 'suivi'], cle: 'MESSAGE.reponse.suivi' },
  { mots: ['livraison', 'livrer'], cle: 'MESSAGE.reponse.livraison' },
  { mots: ['prix', 'tarif', 'combien'], cle: 'MESSAGE.reponse.prix' },
  { mots: ['dégust', 'degust', 'visite', 'route'], cle: 'MESSAGE.reponse.degustation' },
  { mots: ['stock', 'dispo'], cle: 'MESSAGE.reponse.stock' },
  { mots: ['vin', 'conseil', 'recommande'], cle: 'MESSAGE.reponse.conseil' },
];

/** défaut */
const CLE_DEFAUT = 'MESSAGE.reponse.defaut';

/** garde */
function estMessage(valeur: unknown): valeur is MessageConversation {
  if (typeof valeur !== 'object' || valeur === null) return false;
  const m = valeur as Partial<MessageConversation>;
  return (
    typeof m.id === 'string' &&
    (m.auteur === 'client' || m.auteur === 'conseiller') &&
    typeof m.texte === 'string' &&
    typeof m.estCle === 'boolean' &&
    typeof m.horodatage === 'string' &&
    typeof m.lu === 'boolean'
  );
}

/** conversation */
@Injectable({ providedIn: 'root' })
export class MessageService {
 /** état */
  private readonly messagesSig = signal<MessageConversation[]>(this.lireMessages());
  private readonly conseillerSig = signal<{ nom: string; fonction: string; enLigne: boolean }>({
    ...CONSEILLER,
  });
  private jeton = 0;

 /** API */
  readonly messages: Signal<MessageConversation[]> = this.messagesSig.asReadonly();
  readonly conseiller: Signal<{ nom: string; fonction: string; enLigne: boolean }> =
    this.conseillerSig.asReadonly();

 /** non-lus */
  readonly nonLus: Signal<number> = computed(
    () => this.messagesSig().filter((message) => !message.lu).length,
  );

 /** dernier */
  readonly dernierMessage: Signal<MessageConversation | null> = computed(() => {
    const liste = this.messagesSig();
    return liste.length > 0 ? liste[liste.length - 1] : null;
  });

 /** envoi */
  envoyer(texte: string): void {
    const contenu = texte.trim();
    if (!contenu) return;

    this.ajouter({
      id: this.creerId(),
      auteur: 'client',
      texte: contenu,
      estCle: false,
      horodatage: new Date().toISOString(),
      lu: true,
    });

    this.reponseAuto();
  }

 /** lecture */
  marquerLus(): void {
    const liste = this.messagesSig();
    if (!liste.some((message) => !message.lu)) return;
    this.majMessages(liste.map((message) => (message.lu ? message : { ...message, lu: true })));
  }

 /** vidage */
  vider(): void {
    this.jeton += 1;
    this.majMessages([]);
    try {
      localStorage.removeItem(CLE_MESSAGES);
    } catch {
      console.warn('Conversation non purgée (stockage indisponible).');
    }
  }

 /** réponse automatique */
  reponseAuto(): void {
    const jeton = ++this.jeton;
    const dernier = this.dernierMessageClient();
    const cle = this.cleReponse(dernier?.texte ?? '');

    setTimeout(() => {
      if (jeton !== this.jeton) return;
      this.ajouter({
        id: this.creerId(),
        auteur: 'conseiller',
        texte: cle,
        estCle: true,
        horodatage: new Date().toISOString(),
        lu: false,
      });
    }, DELAI_REPONSE_MS);
  }

 /** interne */
  private ajouter(message: MessageConversation): void {
    this.majMessages([...this.messagesSig(), message]);
  }

  private majMessages(liste: MessageConversation[]): void {
    this.messagesSig.set(liste);
    try {
      localStorage.setItem(CLE_MESSAGES, JSON.stringify(liste));
    } catch {
      console.warn('Messages non enregistrés (stockage indisponible).');
    }
  }

  private dernierMessageClient(): MessageConversation | null {
    const liste = this.messagesSig();
    for (let i = liste.length - 1; i >= 0; i -= 1) {
      if (liste[i].auteur === 'client') return liste[i];
    }
    return null;
  }

  private cleReponse(texte: string): string {
    const minuscule = texte.toLowerCase();
    for (const regle of REGLES) {
      if (regle.mots.some((mot) => minuscule.includes(mot))) return regle.cle;
    }
    return CLE_DEFAUT;
  }

  private creerId(): string {
    return `m-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }

 /** lecture */
  private lireMessages(): MessageConversation[] {
    try {
      const brut = localStorage.getItem(CLE_MESSAGES);
      if (!brut) return [];
      const parse: unknown = JSON.parse(brut);
      return Array.isArray(parse) ? parse.filter(estMessage) : [];
    } catch {
      return [];
    }
  }
}
