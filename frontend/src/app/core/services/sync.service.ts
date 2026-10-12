import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ModePaiementApi, VenteApi, VenteApiEnvelope } from '../models/vente-api.model';
import { PanierLigne } from '../models/product.model';
import { ConnectivityService } from './connectivity.service';
import { environment } from '../../../environments/environment';

const CLE_FILE = 'lb.sync.file';

/** Ligne envoyée à `POST /api/ventes/`. */
interface LigneApi {
  produit_id: number;
  quantite: number;
  unite: string;
}

/** Vente mise en file le temps du retour du réseau. */
interface VenteEnFile {
  mode_paiement: ModePaiementApi;
  lignes: LigneApi[];
  client_libelle: string;
  reference_paiement?: string;
  horodatage: string;
}

/** Réponse de la dernière synchronisation, affichée par le bandeau. */
export interface ResultatSync {
  succes: boolean;
  nombre: number;
}

function versLignes(lignes: PanierLigne[]): LigneApi[] {
  const produitsVus = new Set<number>();
  return lignes.map((ligne) => {
    const produitId = Number(ligne.vin.id);
    if (!Number.isSafeInteger(produitId) || produitId <= 0) {
      throw new Error(`Identifiant produit invalide : ${ligne.vin.id}`);
    }
    if (produitsVus.has(produitId)) {
      throw new Error('Un produit ne peut apparaître qu’une seule fois dans la vente.');
    }
    produitsVus.add(produitId);
    return { produit_id: produitId, quantite: ligne.quantite, unite: 'BOUTEILLE' };
  });
}

function totalLignes(lignes: PanierLigne[]): number {
  return Math.round(lignes.reduce((somme, l) => somme + l.prixUnitaire * l.quantite, 0));
}

/**
 * Enregistrement des ventes côté serveur.
 *
 * Une vente est envoyée à `POST /api/ventes/` :
 *  - **en ligne** → la réponse du backend fait foi (référence, total) ;
 *  - **hors ligne** → la vente est mise en file locale et une référence
 *    provisoire est renvoyée, l'écran ne doit pas rester bloqué ;
 *  - **caisse fermée (409)** → la session est ouverte (`POST /api/caisse/ouvrir/`,
 *    opération idempotente) puis la vente est retentée une fois.
 *
 * La file alimente le bandeau « hors ligne » et est rejouée par `synchroniser()`
 * au retour du réseau.
 */
@Injectable({ providedIn: 'root' })
export class SyncService {
  private readonly http = inject(HttpClient);
  private readonly connectivite = inject(ConnectivityService);

  /** Ventes en attente d'envoi. */
  readonly enAttente = signal<number>(this.lireFile().length);

  /** Résultat de la dernière synchronisation (affiché 4 s par le bandeau). */
  readonly dernierSync = signal<ResultatSync | null>(null);

  constructor() {
    // Rejoue la file dès le retour du réseau, comme annoncé par le bandeau.
    this.connectivite.onChange((enLigne) => {
      if (enLigne && this.enAttente() > 0) void this.synchroniser();
    });
  }

  /**
   * Enregistre une vente et renvoie la référence du ticket.
   *
   * @param lignes lignes du panier
   * @param modePaiement mode d'encaissement (défaut : espèces)
   * @param clientLibelle nom libre saisi au comptoir (vente de passage)
   * @param referencePaiement référence de transaction (Mobile Money, chèque)
   */
  async enregistrerVente(
    lignes: PanierLigne[],
    modePaiement: ModePaiementApi = 'ESPECES',
    clientLibelle = '',
    referencePaiement = '',
  ): Promise<VenteApi> {
    if (environment.useMock) {
      throw new Error('Les ventes doivent être validées par le backend.');
    }
    if (!lignes.length) throw new Error('Le panier est vide.');

    const payload: VenteEnFile = {
      mode_paiement: modePaiement,
      lignes: versLignes(lignes),
      client_libelle: clientLibelle,
      ...(referencePaiement ? { reference_paiement: referencePaiement } : {}),
      horodatage: new Date().toISOString(),
    };

    if (!this.connectivite.enLigne()) {
      return this.mettreEnFile(payload, totalLignes(lignes));
    }

    try {
      return await this.poster(payload);
    } catch (erreur) {
      if (this.estReseau(erreur)) return this.mettreEnFile(payload, totalLignes(lignes));
      throw erreur;
    }
  }

  /** Envoie les ventes en file, dans l'ordre, et notifie le bandeau. */
  async synchroniser(): Promise<void> {
    const file = this.lireFile();
    if (!file.length || !this.connectivite.enLigne()) return;

    const reste: VenteEnFile[] = [];
    let envoyees = 0;
    let succes = true;

    for (const vente of file) {
      try {
        await this.poster(vente);
        envoyees += 1;
      } catch (erreur) {
        succes = false;
        if (this.estReseau(erreur)) {
          // Réseau toujours indisponible : on garde le reste pour plus tard.
          reste.push(vente, ...file.slice(file.indexOf(vente) + 1));
        }
        console.error('Synchronisation : vente non envoyée.', erreur);
        break;
      }
    }

    this.ecrireFile(reste);
    this.enAttente.set(reste.length);
    if (envoyees > 0) this.dernierSync.set({ succes, nombre: envoyees });
  }

  // --- Interne ---

  private async poster(vente: VenteEnFile): Promise<VenteApi> {
    try {
      return await this.appeler(vente);
    } catch (erreur) {
      // Caisse fermée (409) : on ouvre la session puis on retente une fois.
      if (!this.estCaisseFermee(erreur)) throw erreur;
      await firstValueFrom(
        this.http.post<{ success: boolean }>(`${environment.apiUrl}/caisse/ouvrir/`, {}),
      );
      return this.appeler(vente);
    }
  }

  private async appeler(vente: VenteEnFile): Promise<VenteApi> {
    const reponse = await firstValueFrom(
      this.http.post<VenteApiEnvelope>(`${environment.apiUrl}/ventes/`, vente),
    );
    if (!reponse.success || !reponse.data?.reference) {
      throw new Error(reponse.message || 'Le backend n’a pas confirmé la vente.');
    }
    return reponse.data;
  }

  private mettreEnFile(vente: VenteEnFile, total: number): VenteApi {
    const file = [...this.lireFile(), vente];
    this.ecrireFile(file);
    this.enAttente.set(file.length);
    return {
      id: 0,
      reference: `EN-ATTENTE-${file.length}`,
      date_vente: vente.horodatage,
      total,
      statut: 'PAYEE',
      lignes: [],
    };
  }

  private lireFile(): VenteEnFile[] {
    try {
      const brut = localStorage.getItem(CLE_FILE);
      const parse: unknown = brut ? JSON.parse(brut) : [];
      return Array.isArray(parse) ? (parse as VenteEnFile[]) : [];
    } catch {
      return [];
    }
  }

  private ecrireFile(file: VenteEnFile[]): void {
    try {
      if (file.length) localStorage.setItem(CLE_FILE, JSON.stringify(file));
      else localStorage.removeItem(CLE_FILE);
    } catch {
      console.warn('File de synchronisation non enregistrée (stockage indisponible).');
    }
  }

  private estReseau(erreur: unknown): boolean {
    return (
      erreur instanceof HttpErrorResponse &&
      [0, 502, 503, 504].includes(erreur.status)
    );
  }

  private estCaisseFermee(erreur: unknown): boolean {
    return (
      erreur instanceof HttpErrorResponse &&
      erreur.status === 409 &&
      erreur.error?.message === 'Caisse fermée.'
    );
  }
}
