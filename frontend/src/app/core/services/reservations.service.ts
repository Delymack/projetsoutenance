import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { catchError, firstValueFrom, throwError } from 'rxjs';

import { PanierLigne } from '../models/product.model';
import { environment } from '../../../environments/environment';

/** Ligne de réservation renvoyée par le backend. */
export interface ReservationSiteLigne {
  produit_id: number;
  quantite: number;
  unite?: string;
  contenance?: number;
  /** Tarif de base, avant remises automatiques éventuelles. */
  prix_unitaire?: string | number;
  /** Libellé du produit (les réponses détaillées le fournissent). */
  produit_nom?: string;
}

/**
 * Commande passée sur le site, suivie par sa référence.
 *
 * Les champs `statut`, `montant_total` et `date_creation` suffisent à
 * l'historique ; `lignes` permet d'afficher le détail sans recharger le
 * panier, qui a été vidé à la validation.
 */
export interface ReservationSite {
  reference: string;
  statut: string;
  montant_total: string;
  validation_statut?: 'A_VALIDER' | 'VALIDEE' | 'REFUSEE' | null;
  validation_par?: number | null;
  validation_le?: string | null;
  motif_refus?: string;
  date_creation?: string;
  date_expiration?: string | null;
  mode_reception?: 'LIVRAISON' | 'RETRAIT';
  vente?: number | null;
  /** Lien public signé vers la facture, présent dès que la commande est validée. */
  facture_url?: string;
  lignes?: ReservationSiteLigne[];
}

interface ReservationSiteEnvelope {
  success: boolean;
  message?: string;
  data?: ReservationSite;
}

/** Enveloppe d'une liste de réservations (`{success, data}`). */
interface ReservationListeEnvelope {
  success: boolean;
  message?: string;
  data?: ReservationDetail[];
}

/** Client rattaché à une réservation (réponses détaillées). */
export interface ReservationClient {
  id?: number;
  nom?: string;
  prenom?: string;
  telephone?: string;
  email?: string;
  adresse?: string;
}

/**
 * Réservation détaillée : `ReservationSite` enrichie des champs réservés aux
 * réponses authentifiées (`mes-commandes`, liste d'équipe).
 */
export interface ReservationDetail extends ReservationSite {
  id?: number;
  source?: 'SITE' | 'INTERNE' | 'TELEPHONE' | string;
  client?: ReservationClient;
  montant_acompte?: string;
  solde_du?: string;
  adresse_livraison?: string;
  note?: string;
  date_expiration?: string | null;
}

interface ReservationActionEnvelope {
  success: boolean;
  message?: string;
  errors?: unknown;
  data?: ReservationDetail;
}

export interface ReservationSiteDonnees {
  nom: string;
  prenom: string;
  telephone: string;
  email: string;
  mode_reception: 'LIVRAISON' | 'RETRAIT';
  adresse_livraison: string;
  note: string;
  lignes: Array<{ produit_id: number; quantite: number; unite: 'BOUTEILLE' }>;
}

@Injectable({ providedIn: 'root' })
export class ReservationsService {
  private readonly http = inject(HttpClient);

  async creerDepuisSite(
    donnees: Omit<ReservationSiteDonnees, 'lignes'>,
    panier: PanierLigne[],
  ): Promise<ReservationSite> {
    if (environment.useMock) {
      throw new Error('Les commandes doivent être enregistrées par le backend.');
    }
    if (!panier.length) throw new Error('Le panier est vide.');

    const produitsVus = new Set<number>();
    const lignes = panier.map(({ vin, quantite }) => {
      const produitId = Number(vin.id);
      if (!Number.isSafeInteger(produitId) || produitId <= 0) {
        throw new Error(`Identifiant produit invalide : ${vin.id}`);
      }
      if (produitsVus.has(produitId)) {
        throw new Error('Un produit ne peut apparaître qu’une seule fois dans la commande.');
      }
      if (!Number.isSafeInteger(quantite) || quantite <= 0) {
        throw new Error(`Quantité invalide pour le produit ${vin.id}.`);
      }
      produitsVus.add(produitId);
      return { produit_id: produitId, quantite, unite: 'BOUTEILLE' as const };
    });

    const payload: ReservationSiteDonnees = { ...donnees, lignes };

    const reponse = await firstValueFrom(
      this.http
        .post<ReservationSiteEnvelope>(`${environment.apiUrl}/reservations/site/`, payload)
        .pipe(
          catchError((erreur: HttpErrorResponse) => {
            if (erreur.status === 400 && erreur.error?.errors) {
              const messages = this.formaterErreurs(erreur.error.errors);
              return throwError(() => new Error(messages.join('\n')));
            }
            return throwError(() => erreur);
          }),
        ),
    );
    if (!reponse.success || !reponse.data?.reference) {
      throw new Error(reponse.message || 'Le backend n’a pas confirmé la commande.');
    }
    return reponse.data;
  }

  /**
   * Commandes du client connecté (`GET /api/reservations/mes-commandes/`).
   *
   * Les nouvelles commandes sont rattachées au compte via le JWT ; les anciennes
   * commandes non rattachées restent retrouvables par leurs coordonnées.
   */
  async mesCommandes(): Promise<ReservationDetail[]> {
    const reponse = await firstValueFrom(
      this.http.get<ReservationListeEnvelope>(`${environment.apiUrl}/reservations/mes-commandes/`),
    );
    if (!reponse.success || !Array.isArray(reponse.data)) {
      throw new Error(reponse.message || 'Vos commandes sont indisponibles.');
    }
    return reponse.data;
  }

  /**
   * File des commandes reçues, côté équipe (`GET /api/reservations/`).
   *
   * Réservée aux rôles admin / gestionnaire / vendeur (CanManageVentes).
   * Toutes les pages sont parcourues : l'équipe voit la file complète,
   * archives comprises (`inclure_soldees=1`).
   */
  async listeEquipe(): Promise<ReservationDetail[]> {
    const reservations: ReservationDetail[] = [];
    const urlsVisitees = new Set<string>();
    let url: string | null = `${environment.apiUrl}/reservations/?inclure_soldees=1&ordering=-date_creation`;

    while (url) {
      if (urlsVisitees.has(url)) {
        throw new Error(`Pagination des réservations répétée : ${url}`);
      }
      urlsVisitees.add(url);
      const reponse: { count?: number; next?: string | null; results?: ReservationDetail[] } =
        await firstValueFrom(this.http.get(url));
      reservations.push(...(reponse.results ?? []));
      url = reponse.next ?? null;
    }
    return reservations;
  }

  async valider(id: number): Promise<ReservationDetail> {
    return this.executerActionEquipe(id, 'valider', {});
  }

  async refuser(id: number, motif: string): Promise<ReservationDetail> {
    const raison = motif.trim();
    if (raison.length < 5) {
      throw new Error('Expliquez le refus en 5 caractères minimum.');
    }
    return this.executerActionEquipe(id, 'refuser', { motif: raison });
  }

  /**
   * État d'une commande passée sur le site, identifiée par sa référence.
   *
   * `GET /api/reservations/suivi/<reference>/` est public : aucun compte ni
   * jeton n'est requis, la référence suffit. Une référence inconnue (commande
   * purgée) se traduit par une erreur — l'historique garde alors l'entrée locale.
   */
  async suivi(reference: string): Promise<ReservationSite> {
    const reponse = await firstValueFrom(
      this.http.get<ReservationSiteEnvelope>(
        `${environment.apiUrl}/reservations/suivi/${encodeURIComponent(reference)}/`,
      ),
    );
    if (!reponse.success || !reponse.data) {
      throw new Error(reponse.message || 'Le suivi de la commande est indisponible.');
    }
    return reponse.data;
  }

  // --- Interne ---

  private async executerActionEquipe(
    id: number,
    action: 'valider' | 'refuser',
    payload: Record<string, string>,
  ): Promise<ReservationDetail> {
    if (!Number.isSafeInteger(id) || id < 1) {
      throw new Error('Identifiant de commande invalide.');
    }
    const reponse = await firstValueFrom(
      this.http
        .post<ReservationActionEnvelope>(
          `${environment.apiUrl}/reservations/${id}/${action}/`,
          payload,
        )
        .pipe(
          catchError((erreur: HttpErrorResponse) => {
            if (erreur.status === 400 && erreur.error?.errors) {
              return throwError(() => new Error(
                this.formaterErreurs(erreur.error.errors).join('\n'),
              ));
            }
            return throwError(() => erreur);
          }),
        ),
    );
    if (!reponse.success || !reponse.data) {
      throw new Error(reponse.message || 'La commande n’a pas été mise à jour.');
    }
    return reponse.data;
  }

  /**
   * Aplatit les erreurs DRF ({ champ: ["msg"] } ou { champ: { nested: ["msg"] }})
   * en une liste de messages lisibles pour l'utilisateur.
   */
  private formaterErreurs(errors: unknown, prefix = ''): string[] {
    if (typeof errors === 'string') {
      return [prefix ? `${prefix}: ${errors}` : errors];
    }
    if (Array.isArray(errors)) {
      return errors.flatMap((err) => this.formaterErreurs(err, prefix));
    }
    if (errors && typeof errors === 'object') {
      return Object.entries(errors).flatMap(([cle, valeur]) => {
        const libelle = prefix ? `${prefix} › ${cle}` : cle;
        return this.formaterErreurs(valeur, libelle);
      });
    }
    return [prefix || 'Erreur inconnue.'];
  }
}
