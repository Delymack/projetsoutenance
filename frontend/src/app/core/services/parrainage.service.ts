import { Injectable, computed, signal } from '@angular/core';

const CLE_FILLEULS = 'lb.filleuls';
const CLE_CODE = 'lb.codeParrainage';
const CLE_CODE_UTILISE = 'lb.codeUtilise';

/** Avancement d'une invitation de parrainage. */
export type StatutFilleul = 'en attente' | 'commande' | 'recompense';

/** Filleul invité par le client. */
export interface Filleul {
  /** Identifiant local. */
  id: string;
  /** Prénom ou pseudonyme du filleul. */
  nom: string;
  /** Adresse de contact utilisée pour l'invitation. */
  contact: string;
  /** Canal d'invitation. */
  canal: 'email' | 'sms';
  /** Date de l'invitation (ISO). */
  date: string;
  /** Avancement de la relation. */
  statut: StatutFilleul;
}

/** Réduction offerte au filleul, en Ariary. */
export const REMISE_FILLEUL = 1000;

/**
 * Parrainage.
 *
 * Chaque client dispose d'un code de parrainage personnel, à 8 caractères,
 * qui ouvre droit à une réduction au filleul. Les invitations envoyées sont
 * mémorisées dans le navigateur pour que la page « Vos filleuls » soit
 * renseignée en mode mock.
 */
@Injectable({ providedIn: 'root' })
export class ParrainageService {
  readonly remise = REMISE_FILLEUL;

  /** Code de parrainage du client, persisté entre deux visites. */
  readonly code = signal<string>(this.lireCode());

  /** Filleuls invités, du plus récent au plus ancien. */
  readonly filleuls = signal<Filleul[]>(this.listerFilleuls());

  /** Nombre d'invitations en cours (n'ayant pas encore commandé). */
  readonly enAttente = computed(() => this.filleuls().filter((filleul) => filleul.statut === 'en attente').length);

  /** Récompenses déjà acquises (filleul ayant passé une commande). */
  readonly recompensesObtenues = computed(
    () => this.filleuls().filter((filleul) => filleul.statut === 'recompense').length * REMISE_FILLEUL,
  );

  /** Lien d'invitation complet, à copier dans un mail ou un SMS. */
  readonly lienInvitation = computed(() => `${location.origin}/catalogue?code=${this.code()}`);

  /** Enregistre une invitation envoyée à un nouveau filleul. */
  inviter(nom: string, contact: string, canal: Filleul['canal']): Filleul {
    const filleul: Filleul = {
      id: `fil-${Date.now().toString(36)}`,
      nom: nom.trim() || contact.trim(),
      contact: contact.trim(),
      canal,
      date: new Date().toISOString(),
      statut: 'en attente',
    };

    this.filleuls.update((liste) => [filleul, ...liste]);
    this.ecrireFilleuls(this.filleuls());
    return filleul;
  }

  /** Fait progresser un filleul (simulation du suivi de commande). */
  changerStatut(id: string, statut: StatutFilleul): void {
    this.filleuls.update((liste) =>
      liste.map((filleul) => (filleul.id === id ? { ...filleul, statut } : filleul)),
    );
    this.ecrireFilleuls(this.filleuls());
  }

  /** Change le canal d'invitation d'un filleul. */
  changerCanal(id: string, canal: Filleul['canal']): void {
    this.filleuls.update((liste) =>
      liste.map((filleul) => (filleul.id === id ? { ...filleul, canal } : filleul)),
    );
    this.ecrireFilleuls(this.filleuls());
  }

  /** Supprime un filleul de la liste. */
  retirer(id: string): void {
    this.filleuls.update((liste) => liste.filter((filleul) => filleul.id !== id));
    this.ecrireFilleuls(this.filleuls());
  }

  /**
   * Enregistre le code de parrainage saisi par le client.
   *
   * La remise n'est plus appliquée localement : elle relève du backend, qui
   * est le seul à calculer les totaux. Le code sert ici à la traçabilité et à
   * l'affichage (« code utilisé »).
   */
  utiliserCode(code: string): void {
    const normalise = code.trim().toUpperCase();
    if (!normalise || normalise === this.code()) return;
    try {
      localStorage.setItem(CLE_CODE_UTILISE, normalise);
    } catch {
      // Stockage indisponible : le code reste valable pour la session.
    }
  }

  /** Code de parrainage utilisé par le client, s'il en a saisi un. */
  get codeUtilise(): string | null {
    try {
      return localStorage.getItem(CLE_CODE_UTILISE);
    } catch {
      return null;
    }
  }

  // --- Persistance ---

  /** Code stable à 8 caractères, mémorisé au premier appel. */
  private lireCode(): string {
    try {
      const stocke = localStorage.getItem(CLE_CODE);
      if (stocke) return stocke;
      const genere = this.genererCode();
      localStorage.setItem(CLE_CODE, genere);
      return genere;
    } catch {
      return this.genererCode();
    }
  }

  private ecrireFilleuls(filleuls: Filleul[]): void {
    try {
      localStorage.setItem(CLE_FILLEULS, JSON.stringify(filleuls));
    } catch {
      console.warn('Liste des filleuls non enregistrée (stockage indisponible).');
    }
  }

  private listerFilleuls(): Filleul[] {
    try {
      const brut = localStorage.getItem(CLE_FILLEULS);
      if (!brut) return this.filleulsDemo();
      const parse: unknown = JSON.parse(brut);
      return Array.isArray(parse) ? (parse as Filleul[]) : this.filleulsDemo();
    } catch {
      return this.filleulsDemo();
    }
  }

  /** Deux filleuls de démonstration, injectés une seule fois. */
  private filleulsDemo(): Filleul[] {
    const filleuls: Filleul[] = [
      {
        id: 'fil-demo-1',
        nom: 'Miora',
        contact: 'miora@lazani-betsileo.mg',
        canal: 'email',
        date: '2026-09-15T08:00:00.000Z',
        statut: 'recompense',
      },
      {
        id: 'fil-demo-2',
        nom: 'Tojo',
        contact: '+261 34 00 000 00',
        canal: 'sms',
        date: '2026-09-30T16:20:00.000Z',
        statut: 'en attente',
      },
    ];

    this.ecrireFilleuls(filleuls);
    return filleuls;
  }

  /** Code alphanumérique court, sans caractère ambigu (0/O, 1/I). */
  private genererCode(): string {
    const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    let code = '';
    for (let i = 0; i < 8; i += 1) {
      code += alphabet[Math.floor(Math.random() * alphabet.length)];
    }
    return code;
  }
}