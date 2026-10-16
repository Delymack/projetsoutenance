import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { Commande, LigneCommande, StatutCommande } from '../models/commande.model';
import { VenteApi, VenteApiList } from '../models/vente-api.model';
import { environment } from '../../../environments/environment';
import { ReservationSite, ReservationsService } from './reservations.service';

const CLE_COMMANDES = 'lb.commandes';

/** Préfixe des références de réservation (commande du site, avant caisse). */
const PREFIXE_RESERVATION = 'RES-';

/** Statuts proposés dans le filtre de la page « Historique ». */
export const STATUTS_COMMANDE: StatutCommande[] = ['livree', 'enPreparation', 'annulee'];

function nombre(valeur: string | number | null | undefined): number {
  const resultat = Number(valeur);
  return Number.isFinite(resultat) ? resultat : 0;
}

/** Identifiant produit d'une ligne : objet enrichi ou simple clé étrangère. */
function idProduit(ligne: VenteApi['lignes'][number]): number {
  const produit = ligne.produit;
  if (typeof produit === 'number') return produit;
  return produit?.id ?? 0;
}

/** Traduit une vente du backend en commande affichable dans l'historique. */
function versCommande(vente: VenteApi): Commande {
  const lignes: LigneCommande[] = vente.lignes.map((ligne) => {
    const prixUnitaire = nombre(ligne.prix_unitaire);
    const brut = prixUnitaire * ligne.quantite;
    const remise = nombre(ligne.remise);
    return {
      vinId: String(idProduit(ligne)),
      quantite: ligne.quantite,
      prixUnitaire,
      remisePct: brut > 0 ? Math.round((remise / brut) * 100) : 0,
    };
  });

  return {
    reference: vente.reference,
    date: vente.date_vente,
    lignes,
    // Le backend ne facture pas de frais de livraison : le total fiable est
    // celui qu'il a calculé (`totalBackend`), affiché en priorité.
    fraisLivraison: 0,
    statut: vente.statut === 'ANNULEE' ? 'annulee' : 'enPreparation',
    totalBackend: nombre(vente.total),
  };
}

/** Statut de réservation backend → statut d'affichage de l'historique. */
function versStatutReservation(statut: string): StatutCommande {
  switch (statut) {
    case 'SOLDEE':
      return 'livree';
    case 'ANNULEE':
    case 'EXPIREE':
      return 'annulee';
    default:
      return 'enPreparation';
  }
}

/**
 * Traduit une réservation du site en commande affichable.
 *
 * Le total fait foi (`totalBackend`) : il inclut les remises automatiques des
 * campagnes en cours. Les lignes portent le tarif de base, d'où une remise
 * répartie au prorata pour que le détail retombe sur le total annoncé.
 */
function versReservation(reservation: ReservationSite): Commande {
  const lignes: LigneCommande[] = (reservation.lignes ?? []).map((ligne) => ({
    vinId: String(ligne.produit_id),
    quantite: ligne.quantite,
    prixUnitaire: nombre(ligne.prix_unitaire),
    remisePct: 0,
  }));

  const total = nombre(reservation.montant_total);
  const brut = lignes.reduce((somme, ligne) => somme + ligne.prixUnitaire * ligne.quantite, 0);
  const remisePct = brut > 0 && total < brut ? Math.round((1 - total / brut) * 100) : 0;
  const detail = lignes.map((ligne) => ({ ...ligne, remisePct }));

  return {
    reference: reservation.reference,
    date: reservation.date_creation ?? new Date().toISOString(),
    lignes: detail,
    fraisLivraison: 0,
    statut: versStatutReservation(reservation.statut),
    validationStatut: reservation.validation_statut ?? undefined,
    motifRefus: reservation.motif_refus,
    factureUrl: reservation.facture_url,
    totalBackend: total,
  };
}

/**
 * Historique des achats du client.
 *
 * Deux sources se complètent :
 *
 *  - les **réservations** passées sur le site (`POST /api/reservations/site/`),
 *    conservées dans le navigateur et rafraîchies par référence via
 *    `GET /api/reservations/suivi/<reference>/` — le client n'a pas de compte ;
 *  - les **ventes encaissées** par la caisse (`GET /api/ventes/`), lisibles
 *    avec un jeton d'équipe ; sans droit de caisse, la liste locale reste
 *    seule affichée au lieu d'effacer l'historique.
 *
 * En mode mock, un historique de démonstration reste stocké dans le navigateur
 * pour que les filtres et le partage aient du contenu sans backend.
 */
@Injectable({ providedIn: 'root' })
export class CommandesService {
  private readonly http = inject(HttpClient);
  private readonly reservations = inject(ReservationsService);

  /** Commandes du client, triées de la plus récente à la plus ancienne. */
  readonly commandes = signal<Commande[]>(this.chargerLocalement());

  /** Total dépensé, toutes commandes non annulées confondues. */
  readonly totalDepense = computed(() =>
    this.commandes().reduce(
      (somme, commande) => somme + (commande.statut === 'annulee' ? 0 : this.total(commande)),
      0,
    ),
  );

  /** Nombre de bouteilles commandées, tous statuts confondus. */
  readonly nbBouteilles = computed(() =>
    this.commandes().reduce((somme, commande) => somme + this.quantite(commande), 0),
  );

  /** Ajoute immédiatement à l'historique la vente confirmée par le backend. */
  enregistrerDepuisApi(vente: VenteApi): Commande {
    if (!Number.isSafeInteger(vente.id) || !vente.id || vente.id < 1) {
      throw new Error('La vente est en attente de synchronisation et ne figure pas encore dans l’historique.');
    }
    const commande = versCommande(vente);
    this.ajouter(commande);
    return commande;
  }

  /** Ajoute à l'historique la réservation confirmée par le site. */
  enregistrerReservation(reservation: ReservationSite): Commande {
    const commande = versReservation(reservation);
    this.ajouter(commande);
    return commande;
  }

  /** Charge l'historique depuis l'API (mode réel uniquement). */
  async rafraichir(): Promise<void> {
    if (environment.useMock) return;

    // 1) + 2) En parallèle : commandes du site suivies par référence (sans
    // compte) et ventes encaissées par la caisse (avec jeton, sinon []).
    const locales = this.chargerLocalement();
    const [suivies, ventes] = await Promise.all([
      Promise.all(locales.map((commande) => this.suivre(commande))),
      this.chargerVentes(),
    ]);

    const fusion = new Map<string, Commande>();
    for (const commande of [...suivies, ...ventes]) {
      fusion.set(commande.reference, commande);
    }
    this.commandes.set(this.trier([...fusion.values()]));
    this.ecrire(this.commandes());
  }

  /**
   * Ajoute les commandes retrouvées côté serveur pour le client connecté
   * (`GET /api/reservations/mes-commandes/`).
   *
   * À appeler **après** `rafraichir()` : ce dernier réécrit la liste à partir
   * des sources connues, les commandes serveur fusionnent ensuite (et sont
   * persistées, donc suivies par référence au prochain rafraîchissement).
   * Un refus (401/403) ou une coupure réseau laisse l'historique local tel quel.
   */
  async rafraichirMesCommandes(): Promise<void> {
    if (environment.useMock) return;
    try {
      const reservations = await this.reservations.mesCommandes();
      for (const reservation of reservations) {
        this.ajouter(versReservation(reservation));
      }
      this.commandes.set(this.trier(this.commandes()));
    } catch (erreur) {
      if (!this.estRefus(erreur)) {
        console.error('Historique : chargement de vos commandes impossible.', erreur);
      }
    }
  }

  /** Sous-total d'une commande (hors livraison). */
  sousTotal(commande: Commande): number {
    return commande.lignes.reduce((s, l) => s + l.prixUnitaire * l.quantite * (1 - l.remisePct / 100), 0);
  }

  /** Remise consentie sur une commande (en Ariary). */
  remise(commande: Commande): number {
    const plein = commande.lignes.reduce((s, l) => s + l.prixUnitaire * l.quantite, 0);
    return Math.max(Math.round(plein - this.sousTotal(commande)), 0);
  }

  /** Total payé : le montant du backend fait foi, sinon recalcul local. */
  total(commande: Commande): number {
    if (commande.totalBackend !== undefined) return commande.totalBackend;
    return Math.max(0, Math.round(this.sousTotal(commande)) + commande.fraisLivraison);
  }

  /** Nombre de bouteilles d'une commande. */
  quantite(commande: Commande): number {
    return commande.lignes.reduce((s, l) => s + l.quantite, 0);
  }

  // --- Sources distantes ---

  /**
   * Recharge l'état d'une réservation passée sur le site.
   *
   * Une référence introuvable ou une coupure réseau conserve l'entrée locale :
   * l'historique doit rester lisible même sans backend.
   */
  private async suivre(commande: Commande): Promise<Commande> {
    if (!commande.reference.startsWith(PREFIXE_RESERVATION)) return commande;
    try {
      return versReservation(await this.reservations.suivi(commande.reference));
    } catch {
      return commande;
    }
  }

  /** Ventes encaissées, toutes pages confondues ([] sans droit de caisse). */
  private async chargerVentes(): Promise<Commande[]> {
    const ventes: Commande[] = [];
    const urlsVisitees = new Set<string>();
    let url: string | null = `${environment.apiUrl}/ventes/?ordering=-date_vente`;

    try {
      while (url) {
        if (urlsVisitees.has(url)) {
          throw new Error(`Pagination des ventes répétée : ${url}`);
        }
        urlsVisitees.add(url);
        const reponse: VenteApi[] | VenteApiList = await firstValueFrom(
          this.http.get<VenteApi[] | VenteApiList>(url),
        );
        const liste: VenteApi[] = Array.isArray(reponse) ? reponse : (reponse.results ?? []);
        ventes.push(...liste.map(versCommande));
        url = Array.isArray(reponse) ? null : (reponse.next ?? null);
      }
      return ventes;
    } catch (erreur) {
      // 401/403 : visiteur sans droit de caisse — l'historique reste local.
      if (!this.estRefus(erreur)) {
        console.error('Historique : chargement des ventes impossible.', erreur);
      }
      return [];
    }
  }

  /** L'API a-t-elle refusé l'accès (jeton absent ou rôle insuffisant) ? */
  private estRefus(erreur: unknown): boolean {
    const status = (erreur as { status?: number } | null)?.status;
    return status === 401 || status === 403;
  }

  /** Ajoute une commande à l'historique et la persiste. */
  private ajouter(commande: Commande): void {
    this.commandes.update((liste) => [
      commande,
      ...liste.filter((existante) => existante.reference !== commande.reference),
    ]);
    this.ecrire(this.commandes());
  }

  // --- Persistance locale ---

  /** Commandes du stockage, triées de la plus récente à la plus ancienne. */
  private chargerLocalement(): Commande[] {
    try {
      const brut = localStorage.getItem(CLE_COMMANDES);
      if (brut) {
        const parse: unknown = JSON.parse(brut);
        if (Array.isArray(parse)) return this.trier(parse as Commande[]);
      }
    } catch {
      // Stockage illisible : on repart d'une base propre.
    }
    return environment.useMock ? this.commandesDemo() : [];
  }

  /** Historique fictif, injecté une seule fois en mode mock. */
  private commandesDemo(): Commande[] {
    const commandes: Commande[] = [
      {
        reference: 'CMD-4821',
        date: '2026-09-28T09:15:00.000Z',
        lignes: [
          { vinId: 'v-001', quantite: 2, prixUnitaire: 42000, remisePct: 0 },
          { vinId: 'v-007', quantite: 1, prixUnitaire: 38500, remisePct: 10 },
        ],
        fraisLivraison: 0,
        statut: 'livree',
      },
      {
        reference: 'CMD-4764',
        date: '2026-09-11T14:40:00.000Z',
        lignes: [{ vinId: 'v-004', quantite: 1, prixUnitaire: 51000, remisePct: 0 }],
        fraisLivraison: 15000,
        statut: 'livree',
      },
      {
        reference: 'CMD-4702',
        date: '2026-08-22T17:05:00.000Z',
        lignes: [
          { vinId: 'v-003', quantite: 3, prixUnitaire: 32000, remisePct: 5 },
          { vinId: 'v-010', quantite: 1, prixUnitaire: 44000, remisePct: 0 },
        ],
        fraisLivraison: 0,
        statut: 'annulee',
      },
      {
        reference: 'CMD-4655',
        date: '2026-08-05T10:20:00.000Z',
        lignes: [{ vinId: 'v-012', quantite: 2, prixUnitaire: 56000, remisePct: 0 }],
        fraisLivraison: 0,
        statut: 'enPreparation',
      },
    ];

    this.ecrire(commandes);
    return commandes;
  }

  private trier(commandes: Commande[]): Commande[] {
    return [...commandes].sort((a, b) => b.date.localeCompare(a.date));
  }

  private ecrire(commandes: Commande[]): void {
    try {
      localStorage.setItem(CLE_COMMANDES, JSON.stringify(commandes));
    } catch {
      console.warn('Historique des commandes non enregistré (stockage indisponible).');
    }
  }
}
