import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { DecimalPipe } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { TranslateModule } from '@ngx-translate/core';
import { timer } from 'rxjs';

import { PanierService } from '../../core/services/panier.service';
import { VinService } from '../../core/services/vin.service';
import { Vin } from '../../core/models/product.model';
import { SkeletonComponent } from '../../shared/components/skeleton/skeleton.component';

/**
 * Page d'accueil.
 *
 *  - vitrine : titre de marque « Lazan'i Betsileo » ;
 *  - liste unique des produits, triée par note décroissante ;
 *  - squelettes pendant le chargement, apparition en cascade `lb-stagger`.
 */
@Component({
  selector: 'app-home',
  standalone: true,
  imports: [RouterLink, DecimalPipe, TranslateModule, SkeletonComponent, MatIconModule],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HomeComponent {
  private readonly vinService = inject(VinService);
  private readonly destroyRef = inject(DestroyRef);

  readonly panier = inject(PanierService);

  /** Catalogue complet. */
  readonly vins = signal<Vin[]>([]);

  /** Vrai tant que la requête HTTP (ou mock) est en vol. */
  readonly chargement = signal<boolean>(true);

  /** Vrai si le catalogue n'a pas pu être chargé. */
  readonly erreur = signal<boolean>(false);

  /** Identifiant du dernier vin ajouté au panier (feedback « ajouté »). */
  readonly ajoutConfirme = signal<string | null>(null);

  /** Fiche courte dépliée dans la grille. */
  readonly detailsOuverts = signal<string | null>(null);

  /** Texte de recherche de la vitrine. */
  readonly recherche = signal('');

  /** Produits de la sélection, triés par note décroissante. */
  readonly selection = computed<Vin[]>(() => {
    const terme = this.normaliser(this.recherche().trim());
    const vins = this.vins().filter((vin) => {
      if (!terme) return true;
      const contenu = this.normaliser(
        [vin.nom, vin.cuvee, vin.cepage, vin.categorie, vin.region, vin.producteur, vin.description].join(' '),
      );
      return contenu.includes(terme);
    });
    return vins.sort((a, b) => b.noteMoyenne - a.noteMoyenne);
  });

  constructor() {
    this.chargerSelection();
  }

  /** Défilement doux jusqu'à la liste des produits. */
  defilerVersProduits(): void {
    document.getElementById('produits')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  mettreAJourRecherche(event: Event): void {
    this.recherche.set((event.currentTarget as HTMLInputElement).value);
  }

  lancerRecherche(event: Event): void {
    event.preventDefault();
    this.defilerVersProduits();
  }

  effacerRecherche(): void {
    this.recherche.set('');
  }

  ajouterAuPanier(vin: Vin): void {
    if (vin.stock < 1) return;
    if (!this.panier.ajouter(vin)) return;
    this.ajoutConfirme.set(vin.id);
    timer(1800)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        if (this.ajoutConfirme() === vin.id) this.ajoutConfirme.set(null);
      });
  }

  basculerDetails(vinId: string): void {
    this.detailsOuverts.update((ouvert) => (ouvert === vinId ? null : vinId));
  }

  reessayer(): void {
    this.chargerSelection();
  }

  private chargerSelection(): void {
    this.chargement.set(true);
    this.erreur.set(false);
    this.vinService.listerTous().subscribe({
      next: (vins) => {
        this.vins.set(vins);
        this.chargement.set(false);
      },
      error: () => {
        this.erreur.set(true);
        this.chargement.set(false);
      },
    });
  }

  private normaliser(texte: string): string {
    return texte
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLocaleLowerCase();
  }
}
