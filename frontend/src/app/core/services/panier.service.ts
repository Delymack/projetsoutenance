import { Injectable, computed, inject, signal } from '@angular/core';
import { BehaviorSubject, map } from 'rxjs';
import { MOCK_VINS } from '../data/mock-vins';
import { PanierLigne, Vin } from '../models/product.model';
import { AuthService } from './auth.service';

/** Mode de fonctionnement du panier (normal, multi-écrans). */
export interface EtatPanier {
  lignes: PanierLigne[];
}

/**
 * Service d'état du panier.
 *
 * Choix : BehaviorSubject plutôt que NgRx car l'état du panier est local,
 * partagé entre le catalogue, la caisse, l'écran client et le chatbot.
 * On expose :
 *  - un `BehaviorSubject<EtatPanier>` pour les subscribers RxJS ;
 *  - des `signal`s dérivés pour les templates (lecture synchrone, pas de pipe async).
 *
 * Persistance : localStorage, pour ne pas perdre le panier au rechargement
 * (et pour rester utilisable hors ligne ).
 *
 * Synchronisation multi-fenêtres : l'écran client ouvert avec
 * `window.open` vit dans un autre document JavaScript, donc il ne partage pas
 * le BehaviorSubject. Chaque mutation locale est donc diffusée sur un
 * `BroadcastChannel` ; à la réception, l'état est appliqué sans être rediffusé
 * (pas de boucle). Un écouteur `storage` prend le relais sur les navigateurs
 * sans BroadcastChannel.
 */
@Injectable({ providedIn: 'root' })
export class PanierService {
  private readonly CLE = 'lb.panier';
 /** ajout mis en attente le temps de l'inscription. */
  private readonly CLE_ATTENTE = 'lb.panier.attente';

  private readonly auth = inject(AuthService);

  /** Canal de diffusion entre onglets/fenêtres de la même application. */
  private readonly canal = this.ouvrirCanal();

  /** Identifiant de cette fenêtre, pour ignorer nos propres messages. */
  private readonly origine = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

  /** Source de vérité (BehaviorSubject). */
  private readonly etat$ = new BehaviorSubject<EtatPanier>(this.reprendre());

  /** Observable public du panier complet. */
  readonly panier$ = this.etat$.asObservable();

  /** Nombre total d'articles (toutes lignes confondues). */
  readonly nbArticles$ = this.panier$.pipe(
    map((e) => e.lignes.reduce((s, l) => s + l.quantite, 0)),
  );

  // --- Signaux dérivés (lecture directe dans les templates) ---

  /** Lignes du panier. */
  readonly lignes = signal<PanierLigne[]>(this.etat$.value.lignes);

  /** Nombre d'articles. */
  readonly nbArticles = computed(() => this.lignes().reduce((s, l) => s + l.quantite, 0));

  /** Sous-total (avant remise et livraison). */
  readonly sousTotal = computed(() =>
    this.lignes().reduce((s, l) => s + l.prixUnitaire * l.quantite * (1 - l.remisePct / 100), 0),
  );

  /** Total calculé à partir des lignes; le backend reste la source de vérité. */
  readonly total = computed(() => this.sousTotal());

  /** Le panier est-il vide ? */
  readonly estVide = computed(() => this.lignes().length === 0);

 /** vin refusé faute de compte, déclenche la redirection. */
  readonly ajoutBloque = signal<Vin | null>(null);

 /** vin retenu, rejoué automatiquement une fois le compte créé. */
  readonly ajoutEnAttente = signal<Vin | null>(this.reprendreAttente());

  constructor() {
    // Synchronise signal ← BehaviorSubject à chaque émission.
    this.panier$.subscribe((etat) => {
      this.lignes.set(etat.lignes);
      this.persist(etat);
    });

    this.ecouterLesAutresFenetres();
  }

  /**
   * Ouvre le canal de diffusion s'il est disponible (navigateur récent).
   * Aucun crash si l'API est absente : la synchronisation ne se fait alors
   * que via l'événement `storage`.
   */
  private ouvrirCanal(): BroadcastChannel | null {
    try {
      return typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('lb.panier');
    } catch {
      return null;
    }
  }

  /** Reçoit les états émis par les autres fenêtres et les applique sans rediffusion. */
  private ecouterLesAutresFenetres(): void {
    this.canal?.addEventListener('message', (evenement: MessageEvent) => {
      const message = evenement.data as { origine?: string; etat?: EtatPanier } | null;
      if (!message?.etat || message.origine === this.origine) return;
      this.appliquer(message.etat);
    });

    window.addEventListener('storage', (evenement) => {
      if (evenement.key !== this.CLE || !evenement.newValue) return;
      try {
        this.appliquer(JSON.parse(evenement.newValue) as EtatPanier);
      } catch {
        // Donnée illisible : on ignore et on garde l'état courant.
      }
    });
  }

  /** Applique un état reçu d'une autre fenêtre, sans le rediffuser. */
  private appliquer(etat: EtatPanier): void {
    if (JSON.stringify(etat) === JSON.stringify(this.etat$.value)) return;
    this.etat$.next(etat);
  }

  /** Émet un état local : mise à jour + diffusion aux autres fenêtres. */
  private emettre(etat: EtatPanier): void {
    this.etat$.next(etat);
    this.canal?.postMessage({ origine: this.origine, etat });
  }

  /**
   * Ajoute un vin au panier (ou incrémente la quantité si déjà présent).
   * Ne descend jamais sous 1 : pour retirer, utiliser `retirer`.
   *
 * compte obligatoire : un visiteur non inscrit est renvoyé vers
   * `/inscription`, le vin est mis en attente et ajouté dès la création du
   * compte (`rejouerAjoutEnAttente`). Retourne `false` si l'ajout est refusé.
   * Un prix unitaire explicite permet d'ajouter un article à prix promotionnel.
   */
  ajouter(vin: Vin, quantite = 1, prixUnitaire?: number): boolean {
    const vinAvecPrix = prixUnitaire === undefined ? vin : { ...vin, prix: prixUnitaire };
    if (!this.auth.connecte()) {
      this.ajoutEnAttente.set(vinAvecPrix);
      this.persistAttente(vinAvecPrix);
      this.ajoutBloque.set(vinAvecPrix);
      return false;
    }
    this.jouerAjout(vinAvecPrix, quantite, prixUnitaire);
    return true;
  }

 /** rejoue l'ajout retenu dès que le client est connecté. */
  rejouerAjoutEnAttente(): void {
    const vin = this.ajoutEnAttente();
    if (!vin || !this.auth.connecte()) return;
    this.persistAttente(null);
    this.jouerAjout(vin, 1);
  }

  private jouerAjout(vin: Vin, quantite: number, prixUnitaire?: number): void {
    const lignes = [...this.etat$.value.lignes];
    const index = lignes.findIndex((l) => l.vin.id === vin.id);

    if (index >= 0) {
      const existante = lignes[index];
      const nouvelle = {
        ...existante,
        ...(prixUnitaire === undefined ? {} : { vin, prixUnitaire }),
        // On ne vend pas au-delà du stock disponible.
        quantite: Math.min(existante.quantite + quantite, Math.max(1, vin.stock)),
      };
      lignes[index] = nouvelle;
    } else {
      if (vin.stock <= 0) return; // rupture de stock : on ignore
      lignes.push({
        vin,
        quantite: Math.min(quantite, vin.stock),
        prixUnitaire: prixUnitaire ?? vin.prix,
        remisePct: 0,
      });
    }
    this.emettre({ ...this.etat$.value, lignes });
  }

  /** Définit la quantité d'une ligne (0 = suppression). */
  majQuantite(vinId: string, quantite: number): void {
    if (quantite <= 0) return this.retirer(vinId);
    const lignes = this.etat$.value.lignes
      .map((l) =>
        l.vin.id === vinId
          ? { ...l, quantite: Math.min(quantite, Math.max(1, l.vin.stock)) }
          : l,
      )
      .filter((l) => l.quantite > 0);
    this.emettre({ ...this.etat$.value, lignes });
  }

  /** Retire une ligne du panier. */
  retirer(vinId: string): void {
    const lignes = this.etat$.value.lignes.filter((l) => l.vin.id !== vinId);
    this.emettre({ ...this.etat$.value, lignes });
  }

  /** Restaure un ensemble de lignes (reprise d'un ticket en attente). */
  restaurerLignes(lignes: PanierLigne[]): void {
    this.emettre({ ...this.etat$.value, lignes });
  }

  /** Vide entièrement le panier (raccourci clavier Échap). */
  vider(): void {
    this.emettre({ lignes: [] });
  }

  /** Prix total d'une ligne (quantité × prix unitaire). */
  totalLigne(ligne: PanierLigne): number {
    return Math.round(ligne.prixUnitaire * ligne.quantite);
  }

  /** Vide le panier après un paiement réussi et renvoie un récapitulatif. */
  encaisser(): { lignes: PanierLigne[]; total: number; horodatage: string } {
    const recu = {
      lignes: this.etat$.value.lignes,
      total: this.total(),
      horodatage: new Date().toISOString(),
    };
    this.vider();
    return recu;
  }

  /** Recherche un vin par id dans le catalogue mock (utile pour les tests). */
  static trouverVinMock(id: string): Vin | undefined {
    return MOCK_VINS.find((v) => v.id === id);
  }

  // --- Persistance ---

  private persist(etat: EtatPanier): void {
    // Les objets Vin du mock sont reconstruits par référence : on ne stocke
    // que les lignes, le catalogue restant la source de vérité.
    localStorage.setItem(this.CLE, JSON.stringify(etat));
  }

  private reprendre(): EtatPanier {
    try {
      const brut = localStorage.getItem(this.CLE);
      if (!brut) return { lignes: [] };
      const parse = JSON.parse(brut) as EtatPanier;
      return {
        lignes: Array.isArray(parse.lignes) ? parse.lignes : [],
      };
    } catch {
      return { lignes: [] };
    }
  }

 /** le vin retenu survit à un rechargement de la page. */
  private persistAttente(vin: Vin | null): void {
    if (!vin) {
      localStorage.removeItem(this.CLE_ATTENTE);
      this.ajoutEnAttente.set(null);
      return;
    }
    try {
      localStorage.setItem(this.CLE_ATTENTE, JSON.stringify({ id: vin.id }));
    } catch {
      this.ajoutEnAttente.set(vin);
    }
  }

  private reprendreAttente(): Vin | null {
    try {
      const brut = localStorage.getItem(this.CLE_ATTENTE);
      if (!brut) return null;
      const { id } = JSON.parse(brut) as { id?: string };
      if (!id) return null;
      return MOCK_VINS.find((v) => v.id === id) ?? null;
    } catch {
      return null;
    }
  }
}