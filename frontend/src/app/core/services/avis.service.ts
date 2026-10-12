import { Injectable, computed, inject, signal } from '@angular/core';
import { catchError, of, tap } from 'rxjs';

import { Avis } from '../models/product.model';
import { VinService } from './vin.service';

/** Nombre d'avis affichés par page (pagination côté client). */
export const AVIS_PAR_PAGE = 3;

/** Repartition des notes : index 0 = une étoile, index 4 = cinq étoiles. */
export interface RepartitionNote {
  /** Nombre d'étoiles (1 à 5). */
  note: number;
  /** Nombre d'avis ayant donné cette note. */
  total: number;
  /** Part des avis (0 à 1) ayant donné cette note. */
  proportion: number;
}

/**
 * Avis clients.
 *
 * Le composant `<app-review>` n'a aucun état propre : il lit les signaux de ce
 * service. Cette centralisation permet d'afficher la même liste dans la fiche
 * vin, sur la page catalogue ou dans un comparateur sans dupliquer la logique de
 * moyenne, de distribution et de pagination.
 *
 * Pagination : elle est faite côté client (mode mock) via `page`. En mode API,
 * `VinService.listerAvis` renvoie déjà la page demandée par le serveur Django
 * (pagination DRF) ; il suffira alors de remplacer `avisPage` par la tranche
 * reçue — l'interface du composant ne change pas.
 */
@Injectable({ providedIn: 'root' })
export class AvisService {
  private readonly vins = inject(VinService);

  /** Avis du vin consulté, du plus récent au plus ancien. */
  private readonly avisParVin = signal<Record<string, Avis[]>>({});

  /** Vin actuellement chargé. */
  readonly vinActif = signal<string | null>(null);

  readonly chargement = signal(false);
  readonly erreur = signal(false);

  /** Page courante (1-based) de la pagination. */
  readonly page = signal(1);

  /** Avis du vin actif, sans pagination. */
  readonly avis = computed<Avis[]>(() => {
    const id = this.vinActif();
    return id ? (this.avisParVin()[id] ?? []) : [];
  });

  /** Note moyenne du vin actif, arrondie au dixième. */
  readonly moyenne = computed(() => {
    const avis = this.avis();
    if (avis.length === 0) return 0;
    const total = avis.reduce((somme, avis_) => somme + avis_.note, 0);
    return Math.round((total / avis.length) * 10) / 10;
  });

  /** Répartition des notes 5 → 1, pour le diagramme en barres. */
  readonly repartition = computed<RepartitionNote[]>(() => {
    const avis = this.avis();
    const total = avis.length || 1;
    return [5, 4, 3, 2, 1].map((note) => {
      const occurrences = avis.filter((avis_) => avis_.note === note).length;
      return { note, total: occurrences, proportion: occurrences / total };
    });
  });

  /** Nombre de pages de la pagination (toujours ≥ 1 pour éviter un état vide). */
  readonly nbPages = computed(() => Math.max(1, Math.ceil(this.avis().length / AVIS_PAR_PAGE)));

  /** Avis de la page courante. */
  readonly avisPage = computed(() => {
    const debut = (this.page() - 1) * AVIS_PAR_PAGE;
    return this.avis().slice(debut, debut + AVIS_PAR_PAGE);
  });

  /** Peut-on afficher la page précédente / suivante ? */
  readonly pagePrecedente = computed(() => this.page() > 1);
  readonly pageSuivante = computed(() => this.page() < this.nbPages());

  /** Indice de la page courante, pour le rendu « 1 / 3 ». */
  readonly pagination = computed(() => ({
    page: this.page(),
    total: this.nbPages(),
    premier: (this.page() - 1) * AVIS_PAR_PAGE + 1,
    dernier: Math.min(this.page() * AVIS_PAR_PAGE, this.avis().length),
    totalAvis: this.avis().length,
  }));

  /** Charge (ou recharge) les avis d'un vin. Sans effet si c'est déjà chargé. */
  charger(vinId: string, force = false): void {
    if (!force && this.avisParVin()[vinId]) return;

    this.vinActif.set(vinId);
    this.page.set(1);
    this.chargement.set(true);
    this.erreur.set(false);

    this.vins
      .listerAvis(vinId)
      .pipe(
        catchError(() => {
          this.erreur.set(true);
          return of([] as Avis[]);
        }),
        tap(() => this.chargement.set(false)),
      )
      .subscribe((avis) => {
        this.avisParVin.update((cache) => ({
          ...cache,
          [vinId]: [...avis].sort((a, b) => b.date.localeCompare(a.date)),
        }));
      });
  }

  /** Publie un avis : il apparaît immédiatement en tête de liste. */
  ajouter(avis: Omit<Avis, 'id' | 'date' | 'likes'>): void {
    this.vins.ajouterAvis(avis).subscribe((nouvelAvis) => {
      const vinId = nouvelAvis.vinId;
      this.avisParVin.update((cache) => ({
        ...cache,
        [vinId]: [nouvelAvis, ...(cache[vinId] ?? [])],
      }));
      // On revient en première page : l'avis vient d'y être inséré.
      this.page.set(1);
    });
  }

  /** Ajoute un « j'aime » — incrément optimiste, sans appel réseau en mode mock. */
  aimer(avisId: string): void {
    const vinId = this.vinActif();
    if (!vinId) return;

    this.avisParVin.update((cache) => ({
      ...cache,
      [vinId]: (cache[vinId] ?? []).map((avis) =>
        avis.id === avisId ? { ...avis, likes: avis.likes + 1 } : avis,
      ),
    }));
  }

  /** Page suivante. */
  suivant(): void {
    if (this.pageSuivante()) this.page.update((page) => page + 1);
  }

  /** Page précédente. */
  precedent(): void {
    if (this.pagePrecedente()) this.page.update((page) => page - 1);
  }
}