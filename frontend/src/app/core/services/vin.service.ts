import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { EMPTY, Observable, delay, expand, map, of, reduce } from 'rxjs';
import { environment } from '../../../environments/environment';
import { MOCK_AVIS, MOCK_DELAY_MS, MOCK_PROMOS, MOCK_VINS } from '../data/mock-vins';
import { Avis, Promotion, Vin, WineCategory } from '../models/product.model';

interface ProduitApi {
  id: number;
  nom: string;
  type_vin?: string;
  marque?: string;
  millesime?: number | null;
  volume?: string | null;
  description?: string | null;
  cepage?: string | null;
  appellation?: string | null;
  degre_alcool?: string | number | null;
  prix_vente?: string | number;
  prix_unitaire_vente?: string | number;
  image_url?: string | null;
  image?: string | null;
  code_barre?: string | null;
  stock_quantite?: number;
  unite_vente?: string | null;
  categorie?: { id?: number; nom?: string } | null;
  promotion_active?: { prix_final?: string | number } | null;
}

/** Promotion telle que renvoyée par `GET /api/promotions/`. */
interface PromotionApi {
  id: number;
  nom: string;
  type_promotion: 'POURCENTAGE' | 'MONTANT_FIXE' | 'PRIX_PROMO' | 'LOT';
  valeur?: string | number | null;
  prix_promotionnel?: string | number | null;
  date_debut: string;
  date_fin: string;
  statut: boolean;
  est_active: boolean;
  produits?: { id: number }[];
  categories?: { id: number; nom?: string }[];
}

interface PaginatedResponse<T> {
  count?: number;
  /** URL de la page suivante (DRF `PageNumberPagination`), `null` à la fin. */
  next?: string | null;
  previous?: string | null;
  results: T[];
}

interface ProduitScannerResponse {
  trouve: boolean;
  produit?: ProduitApi;
}

function lireListe<T>(response: T[] | PaginatedResponse<T>): T[] {
  return Array.isArray(response) ? response : response.results;
}

/**
 * Visuel de repli des cartes produit.
 *
 * Le catalogue Django n'impose pas d'image (`image_url` vaut `null` tant
 * qu'aucun fichier n'est téléversé) : sans ce repli, la carte afficherait une
 * image cassée.
 */
const IMAGE_PRODUIT_DEFAUT = 'assets/images/produits/produit-placeholder.png';
const IMAGES_PRODUITS_PAR_NOM: Record<string, string> = {
  "tsiky dia loatra": 'assets/images/vins/v-001.svg',
  'gris de betsileo': 'assets/images/vins/v-002.svg',
  "rosé d'ihosy": 'assets/images/vins/v-003.svg',
  'pétillant de tsarasaotra': 'assets/images/vins/v-004.svg',
  'malbec ambatondrazaka': 'assets/images/vins/v-005.svg',
  'vermentino antsirabe': 'assets/images/vins/v-006.svg',
  'cuvée des rogations': 'assets/images/vins/v-007.svg',
  'pinot noir androy': 'assets/images/vins/v-008.svg',
  'liqueur de moussafely': 'assets/images/vins/v-009.svg',
  'sauvignon blanc vakio': 'assets/images/vins/v-010.svg',
  'cabernet fianarantsoa': 'assets/images/vins/v-011.svg',
  "vendange d'or": 'assets/images/vins/v-012.svg',
};

function nombre(valeur: string | number | null | undefined, defaut = 0): number {
  const resultat = Number(valeur);
  return Number.isFinite(resultat) ? resultat : defaut;
}

function categorieVin(produit: ProduitApi): WineCategory {
  const texte = (produit.categorie?.nom || produit.type_vin || '').toLowerCase();
  if (texte.includes('blanc')) return 'blanc';
  if (texte.includes('ros')) return 'rose';
  if (texte.includes('liqueur') || texte.includes('apéritif') || texte.includes('eau-de-vie')) return 'liqueur';
  if (texte.includes('mousseux') || texte.includes('pétillant')) return 'mousseux';
  return 'rouge';
}

function versVin(produit: ProduitApi): Vin {
  const prixCatalogue = nombre(produit.prix_unitaire_vente ?? produit.prix_vente);
  const prixPromotionnel = nombre(produit.promotion_active?.prix_final, prixCatalogue);
  const imageDeRepli = IMAGES_PRODUITS_PAR_NOM[produit.nom.trim().toLocaleLowerCase('fr')];
  const volumeBrut = produit.volume ?? '';
  const volumeNombre = Number.parseFloat(volumeBrut.replace(',', '.'));
  const volume = Number.isFinite(volumeNombre)
    ? (/ml/i.test(volumeBrut) ? volumeNombre / 10 : volumeNombre)
    : 75;

  return {
    id: String(produit.id),
    codeBarres: produit.code_barre ?? '',
    nom: produit.nom,
    cuvee: produit.appellation || produit.marque || produit.nom,
    categorie: categorieVin(produit),
    millesime: produit.millesime ?? 0,
    cepage: produit.cepage || produit.type_vin || '',
    prix: prixPromotionnel,
    prixBarre: prixPromotionnel < prixCatalogue ? prixCatalogue : null,
    stock: produit.stock_quantite ?? 0,
    volume,
    alcool: nombre(produit.degre_alcool),
    region: produit.appellation || '',
    description: produit.description || '',
    notesDegustation: [],
    profil: { fruite: 0, tanin: 0, sucre: 0, acide: 0, bois: 0 },
    accords: [],
    image: produit.image_url || produit.image || imageDeRepli || IMAGE_PRODUIT_DEFAUT,
    noteMoyenne: 0,
    nombreAvis: 0,
    producteur: produit.marque || '',
  };
}

/**
 * Adapte une promotion Django au modèle d'affichage de la boutique.
 *
 * Seuls les remises en pourcentage sont affichables en badge (« -15 % ») :
 * un prix promo ou un lot est signalé par `remisePct === null` — le badge
 * se contente alors d'afficher l'intitulé de la campagne.
 */
function versPromotion(promo: PromotionApi): Promotion {
  const valeur = nombre(promo.valeur);
  return {
    id: String(promo.id),
    libelle: promo.nom,
    remisePct: promo.type_promotion === 'POURCENTAGE' && valeur > 0 ? valeur : null,
    dateDebut: promo.date_debut,
    dateFin: promo.date_fin,
    vinsIds: (promo.produits ?? []).map((produit) => String(produit.id)),
    actif: promo.statut && promo.est_active,
  };
}

/** Critères de filtrage du catalogue. */
export interface FiltreVins {
  recherche?: string;
  categorie?: WineCategory | 'toutes';
  prixMax?: number;
  enStock?: boolean;
  /** Tri demandé. */
  tri?: 'nom' | 'prixAsc' | 'prixDesc' | 'note' | 'millesime';
}

/**
 * Service catalogue (vins, promotions, avis).
 *
 * Deux modes :
 *  - `environment.useMock === true`  → données locales + latence simulée ;
 *  - sinon → API Django REST Framework.
 *
 * Ce double mode permet de développer et de démontrer toute l'application
 * sans backend, puis de basculer via un seul changement d'environnement.
 */
@Injectable({ providedIn: 'root' })
export class VinService {
  private readonly http = inject(HttpClient);
  private readonly api = environment.apiUrl;

  // --- Lecture du catalogue ---

  /** Catalogue complet, toutes pages confondues. */
  listerTous(): Observable<Vin[]> {
    if (environment.useMock) return of(MOCK_VINS).pipe(delay(MOCK_DELAY_MS));
    const params = new HttpParams().set('statut', 'true');
    return this.toutesLesPages<ProduitApi>(`${this.api}/produits/`, params).pipe(
      map((produits) => produits.map(versVin)),
    );
  }

  /** Catalogue filtré et trié (côté client en mode mock, côté serveur sinon). */
  lister(filtre: FiltreVins = {}): Observable<Vin[]> {
    if (!environment.useMock) {
      let params = new HttpParams();
      if (filtre.recherche) params = params.set('search', filtre.recherche);
      if (filtre.prixMax) params = params.set('prix_max', filtre.prixMax);
      if (filtre.enStock) params = params.set('en_stock', 'true');
      return this.toutesLesPages<ProduitApi>(`${this.api}/produits/`, params).pipe(
        map((produits) => this.appliquerFiltres(produits.map(versVin), filtre)),
      );
    }

    return of(MOCK_VINS).pipe(
      delay(MOCK_DELAY_MS),
      map((vins) => this.appliquerFiltres(vins, filtre)),
    );
  }

  /** Un vin par identifiant. */
  obtenirParId(id: string): Observable<Vin | undefined> {
    if (environment.useMock) {
      return of(MOCK_VINS.find((v) => v.id === id)).pipe(delay(200));
    }
    return this.http.get<ProduitApi>(`${this.api}/produits/${id}/`).pipe(map(versVin));
  }

  /** Recherche « Cleveland » : par nom, cépage, région ou producteur. */
  rechercher(terme: string): Observable<Vin[]> {
    const t = terme.trim().toLowerCase();
    if (!t) return of([]);
    if (!environment.useMock) return this.lister({ recherche: t });
    return of(MOCK_VINS).pipe(
      delay(250),
      map((vins) =>
        vins.filter((v) =>
          [v.nom, v.cepage, v.region, v.producteur, v.cuvee, v.categorie]
            .join(' ')
            .toLowerCase()
            .includes(t),
        ),
      ),
    );
  }

  /**
 * Retrouve un vin à partir du code-barres lu par le scanner.
   *
   * En mode API, le code est envoyé au serveur ; en mode mock on compare au
   * catalogue local. L'identifiant interne est aussi accepté : les étiquettes
   * de démonstration portent parfois `v-001` plutôt qu'un EAN-13.
   */
  parCodeBarres(code: string): Observable<Vin | undefined> {
    const lu = code.trim();
    if (!environment.useMock) {
      return this.http
        .get<ProduitScannerResponse>(`${this.api}/produits/scanner/`, { params: { code: lu } })
        .pipe(map((response) => response.trouve && response.produit ? versVin(response.produit) : undefined));
    }
    return of(MOCK_VINS.find((v) => v.codeBarres === lu || v.id === lu)).pipe(delay(350));
  }

  // --- Promotions ---

  /**
   * Campagnes visibles dans la boutique (badge de prix, fiche vin).
   *
   * Le filtre `active=true` est appliqué côté serveur (fenêtre + statut +
   * happy hour), la fenêtre de dates étant recontrôlée ici pour que le mode
   * mock et le mode API restent strictement équivalents.
   */
  listerPromotions(): Observable<Promotion[]> {
    if (environment.useMock) {
      const now = Date.now();
      return of(MOCK_PROMOS.filter((p) => p.actif && this.dansFenetre(p, now))).pipe(delay(MOCK_DELAY_MS));
    }
    const params = new HttpParams().set('active', 'true');
    return this.toutesLesPages<PromotionApi>(`${this.api}/promotions/`, params).pipe(
      map((promotions) => {
        const now = Date.now();
        return promotions
          .map(versPromotion)
          .filter((promo) => promo.actif && this.dansFenetre(promo, now));
      }),
    );
  }

  // --- Avis ---
  // Les avis n'ont pas encore d'endpoint : ils sont conservés localement
  // pour que le formulaire de la fiche vin reste utilisable sans erreur.

  listerAvis(vinId: string): Observable<Avis[]> {
    const catalogue = environment.useMock ? MOCK_AVIS : [];
    return of([...catalogue, ...this.avisStockes()].filter((a) => a.vinId === vinId)).pipe(delay(300));
  }

  /** Ajoute un avis (stockage local). */
  ajouterAvis(avis: Omit<Avis, 'id' | 'date' | 'likes'>): Observable<Avis> {
    const nouveau: Avis = {
      ...avis,
      id: `a-${Date.now()}`,
      date: new Date().toISOString(),
      likes: 0,
    };
    const stock = this.avisStockes();
    localStorage.setItem('lb.avis', JSON.stringify([...stock, nouveau]));
    return of(nouveau).pipe(delay(250));
  }

  // --- Interne ---

  /**
   * Concatène toutes les pages d'un endpoint DRF paginé.
   *
   * `PAGE_SIZE` vaut 20 côté Django : sans ce suivi du champ `next`, la
   * boutique n'afficherait que les 20 premiers produits du catalogue.
   */
  private toutesLesPages<T>(url: string, params?: HttpParams): Observable<T[]> {
    return this.http.get<T[] | PaginatedResponse<T>>(url, params ? { params } : {}).pipe(
      expand((page) => {
        const suivante = Array.isArray(page) ? null : page.next;
        return suivante ? this.http.get<T[] | PaginatedResponse<T>>(suivante) : EMPTY;
      }),
      reduce((tous, page) => tous.concat(lireListe(page)), [] as T[]),
    );
  }

  // --- Interne : filtrage/tri côté client (mode mock) ---

  private appliquerFiltres(vins: Vin[], f: FiltreVins): Vin[] {
    let resultat = [...vins];

    if (f.recherche) {
      const t = f.recherche.trim().toLowerCase();
      resultat = resultat.filter((v) =>
        [v.nom, v.cepage, v.region, v.producteur, v.cuvee, v.categorie]
          .join(' ')
          .toLowerCase()
          .includes(t),
      );
    }
    if (f.categorie && f.categorie !== 'toutes') {
      resultat = resultat.filter((v) => v.categorie === f.categorie);
    }
    if (f.prixMax) resultat = resultat.filter((v) => v.prix <= f.prixMax!);
    if (f.enStock) resultat = resultat.filter((v) => v.stock > 0);

    switch (f.tri) {
      case 'prixAsc':
        resultat.sort((a, b) => a.prix - b.prix);
        break;
      case 'prixDesc':
        resultat.sort((a, b) => b.prix - a.prix);
        break;
      case 'note':
        resultat.sort((a, b) => b.noteMoyenne - a.noteMoyenne);
        break;
      case 'millesime':
        resultat.sort((a, b) => b.millesime - a.millesime);
        break;
      default:
        resultat.sort((a, b) => a.nom.localeCompare(b.nom, 'fr'));
    }
    return resultat;
  }

  private dansFenetre(p: Promotion, now: number): boolean {
    return new Date(p.dateDebut).getTime() <= now && new Date(p.dateFin).getTime() >= now;
  }

  private avisStockes(): Avis[] {
    try {
      const stock = JSON.parse(localStorage.getItem('lb.avis') ?? '[]') as unknown;
      return Array.isArray(stock) ? (stock as Avis[]) : [];
    } catch {
      return [];
    }
  }
}
